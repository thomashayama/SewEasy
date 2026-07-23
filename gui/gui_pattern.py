from pathlib import Path
import time
import traceback
import yaml
import shutil
import string
import random
import trimesh
from copy import deepcopy
from typing import Optional

# Custom 
from assets.garment_programs.meta_garment import MetaGarment
from assets.bodies.body_params import BodyParameters
import seweasy as pyg
import seweasy.data_config as data_config
from seweasy.meshgen.sim_config import PathCofig
from seweasy.pattern.print_export import save_print_pdf

# NOTE: the simulation stack (seweasy.meshgen.boxmeshgen / .simulation)
# pulls in NVIDIA Warp, pyrender and libigl — seconds of import time and
# hundreds of MB of RAM. It is only needed when a design is draped without
# the Modal service, so it is imported lazily inside drape_3d().

verbose = False

def hex_to_rgba(hex_color):
    """'#rrggbb' -> RGBA list (0-255) for trimesh materials"""
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)] + [255]


def _point_in_svg_path(pt, path, n=240):
    """Ray-cast point-in-polygon test for a point (complex) against an
    svgpathtools Path, using a linearized outline. Bounding-box reject first."""
    xmin, xmax, ymin, ymax = path.bbox()
    if not (xmin <= pt.real <= xmax and ymin <= pt.imag <= ymax):
        return False
    poly = [path.point(t / n) for t in range(n + 1)]
    x, y = pt.real, pt.imag
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = poly[i].real, poly[i].imag, poly[j].real, poly[j].imag
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside

# The 3D stage's lights overdrive material colors: measured against the
# baked muslin body under the default lights, the displayed color is
# (in linear space) ~2.16x the glTF baseColorFactor on every channel
LIGHT_GAIN = 2.16

def display_to_base_rgba(hex_color):
    """Convert a picked (sRGB display) color to the glTF baseColorFactor
    that actually renders as that color on the 3D stage: sRGB -> linear,
    then compensated for the stage lighting"""
    rgb = hex_to_rgba(hex_color)[:3]
    base = [round(255 * min(1., (c / 255) ** 2.2 / LIGHT_GAIN)) for c in rgb]
    return base + [255]

def _id_generator(size=10, chars=string.ascii_uppercase + string.digits):
        """Generate a random string of a given size, see
        https://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits
        """
        return ''.join(random.choices(chars, k=size))

def sweep_stale_tmp(max_age_hours=24):
    """Remove per-session tmp_gui dirs left behind by unclean disconnects
    (release() only runs on graceful connection close)"""
    cutoff = time.time() - max_age_hours * 3600
    for parent in (Path.cwd() / 'tmp_gui' / 'display',
                   Path.cwd() / 'tmp_gui' / 'downloads',
                   Path.cwd() / 'tmp_gui' / 'garm_3d'):
        if not parent.is_dir():
            continue
        for entry in parent.iterdir():
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink(missing_ok=True)
            except OSError:
                pass


class GUIPattern:
    # Default fabric color -- matches the classic "washed denim" panel fill
    DEFAULT_FABRIC_COLOR = '#b7cde5'

    def __init__(self, draft=True) -> None:
        # Unique id to distiguish tab sessions correctly
        self.id = _id_generator(20)

        # Paths setup
        self.save_path_root = Path.cwd() / 'tmp_gui' / 'downloads'  
        self.tmp_path_root = Path.cwd() / 'tmp_gui' / 'display'
        self.save_path = self.save_path_root / self.id
        self.svg_filename = None
        self.saved_garment_archive = ''
        self.saved_garment_folder = ''
        self.tmp_path = self.tmp_path_root / self.id 
        self.paths_3d = None

        # create paths
        self.save_path.mkdir(parents=True, exist_ok=True)
        self.tmp_path.mkdir(parents=True, exist_ok=True)

        self.body_params = None
        self.design_params = {}
        self.fabric_color = self.DEFAULT_FABRIC_COLOR
        # Per-panel overrides of the fabric color (panel_name -> hex), set by
        # clicking a panel in the 2D view. Panels not listed use fabric_color.
        self.panel_colors = {}
        # Per-panel bending-stiffness multipliers (panel_name -> factor). User
        # overrides on top of any garment default; applied in the 3D drape.
        self.panel_stiffness = {}
        # panel_name -> svgpathtools Path (SVG coords), for 2D click hit-tests
        self.panel_svg_paths = {}
        self.design_sampler = pyg.DesignSampler()
        self.sew_pattern = None

        self.body_file = None
        self.design_file = None
        self._load_body_file(
            Path.cwd() / 'assets/bodies/mean_all.yaml'
        )
        self.default_body_params = deepcopy(self.body_params)
        self._load_design_file(
            Path.cwd() / 'assets/design_params/default.yaml'
        )

        # Status
        self.is_self_intersecting = False
        self.is_in_3D = False
        # A stored drape adopted from a saved outfit (GLB path); used as
        # the 3D result when no fresh simulation output exists
        self.loaded_drape_glb = None

        # draft=False defers the first (expensive) garment assembly so a
        # page can render immediately and draft off the event loop
        if draft:
            self.reload_garment()

    def release(self):
        """Clean up tmp files after the session"""
        self.clear_previous_download()
        shutil.rmtree(self.save_path)
        shutil.rmtree(self.tmp_path)

    def _load_body_file(self, path):
        self.body_file = path
        self.body_params = BodyParameters(path)

    def _load_design_file(self, path):
        self.design_file = path

        # Create values
        with open(path, 'r') as f:
            des = yaml.safe_load(f)['design']

        self.design_params.update(des)
        if 'left' in self.design_params and not self.design_params['left']['enable_asym']['v']:
            self.sync_left()

        # Update param sampler
        self.design_sampler.load(path)

    def svg_path(self):
        return self.tmp_path / self.svg_filename

    def set_new_design(self, design):
        self._nested_sync(design, self.design_params)

    def set_new_body_params(self, body_params):
        self.body_params.load_from_dict(body_params)

    def sample_design(self, reload=True):
        """Random design parameters"""

        new_design = self.design_sampler.randomize()
        # NOTE: re-assign the values instead up overwriting them
        self._nested_sync(new_design, self.design_params)

        if 'left' in self.design_params and not self.design_params['left']['enable_asym']['v']:
            self.sync_left()

        if reload:
            self.reload_garment()

    def restore_design(self, reload=True):
        """Restore design values to match the current loaded file"""
        new_design = self.design_sampler.default()
        # re-assign the values instead up overwriting them
        self._nested_sync(new_design, self.design_params)
        
        if reload:
            self.reload_garment()

    def reload_garment(self):
        """Reload sewing pattern with current body and design parameters
        
            NOTE: loading a pattern might be lagging, execute only when needed!
        """
        self.sew_pattern = MetaGarment(
            'Configured_design', self.body_params, self.design_params)
        self.is_self_intersecting = self.sew_pattern.is_self_intersecting()
        self._view_serialize()

    @staticmethod
    def _nested_sync(s_from, s_to):
        if 'v' in s_to:
            s_to['v'] = s_from['v']
        else:
            for key in s_to:
                if key in s_from:
                    GUIPattern._nested_sync(s_from[key], s_to[key])

    def set_fabric_color(self, color):
        """Change the fabric color and refresh the 2D pattern display"""
        self.fabric_color = color
        if self.sew_pattern is not None:
            self._view_serialize()

    # --- Per-panel coloring (2D view) ---
    def panel_at_svg_point(self, x, y):
        """Name of the top-most panel whose 2D outline contains (x, y) in SVG
        coordinates, or None. Iterates front-to-back so the visible (drawn on
        top) panel wins where panels overlap."""
        pt = complex(x, y)
        for name, path in reversed(list(self.panel_svg_paths.items())):
            if _point_in_svg_path(pt, path):
                return name
        return None

    def set_panel_color(self, panel, color):
        """Override one panel's fabric color and refresh the 2D display"""
        self.panel_colors[panel] = color
        if self.sew_pattern is not None:
            self._view_serialize()

    def panel_color(self, panel):
        """Effective color of a panel (its override or the fabric color)"""
        return self.panel_colors.get(panel, self.fabric_color)

    def reset_panel_colors(self):
        """Clear all per-panel overrides (back to a single fabric color)"""
        self.panel_colors = {}
        if self.sew_pattern is not None:
            self._view_serialize()

    def set_panel_stiffness(self, panel, factor):
        """Override one panel's bending-stiffness multiplier (applied on the
        next 3D drape; does not change the 2D view)"""
        self.panel_stiffness[panel] = float(factor)

    def panel_stiffness_of(self, panel):
        """The user's stiffness override for a panel (1.0 if unset)"""
        return self.panel_stiffness.get(panel, 1.0)

    def sync_left(self, with_check=False):
        """Synchronize left and right design parameters"""
        # Check if needed in the first place
        if with_check and self.design_params['left']['enable_asym']['v']:
            # Asymmetry enabled, the params should not syncronise 
            return  
        for k in self.design_params['left']:
            if k != 'enable_asym':
                # Use proper value assignment instead of deepcopy
                self._nested_sync(self.design_params[k], self.design_params['left'][k])

    def _view_serialize(self):
        """Save a sewing pattern svg representation to tmp folder be used
        for display"""

        # Get the flat representation
        pattern = self.sew_pattern.assembly()

        # Clear up the folder from previous version -- it's not needed any more
        self.clear_previous_svg()
        try:
            self.svg_filename = f'pattern_{time.time()}.svg'
            dwg = pattern.get_svg(self.tmp_path / self.svg_filename,
                                  with_text=False,
                                  view_ids=False,
                                  flat=False,
                                  panel_fill_color=self.fabric_color,
                                  panel_colors=self.panel_colors,
                                  margin=0
            )
            dwg.save()

            self.svg_bbox_size = pattern.svg_bbox_size
            self.svg_bbox = pattern.svg_bbox
            # Panel paths (SVG coords) for click hit-testing in the 2D view
            self.panel_svg_paths = pattern.last_panel_svg_paths
        except pyg.EmptyPatternError:
            self.svg_filename = ''
    
    # Cleaning
    def clear_previous_svg(self):
        """Clear previous svg display file"""
        if self.svg_filename:
            (self.tmp_path / self.svg_filename).unlink()
            self.svg_filename = ''
    
    def clear_previous_download(self):
        """Clear previous download package display file"""
        if self.saved_garment_folder:
            shutil.rmtree(self.saved_garment_folder)
            self.saved_garment_folder = ''
        if self.saved_garment_archive:
            self.saved_garment_archive.unlink()
            self.saved_garment_archive = ''

    def clear_3d(self):
        if self.paths_3d is not None:
            shutil.rmtree(self.paths_3d.out_el)
            self.paths_3d = None

    # 3D
    def drape_3d(self):
        """Run the draping of the current frame"""

        # Config setup 
        props = data_config.Properties('./assets/Sim_props/gui_sim_props.yaml')   # TODOLOW Parameter?
        props.set_section_stats('sim', fails={}, sim_time={}, spf={}, fin_frame={}, body_collisions={}, self_collisions={})
        props.set_section_stats('render', render_time={})

        # Force the design to be fitted to mean body shape 
        # TODOLOW Support body shape estimation from measurements

        def_sew_pattern = MetaGarment(
            'Configured_design', self.default_body_params, self.design_params)

        # Save the pattern
        pattern_folder = self.save(False, save_pattern=def_sew_pattern)

        # Paths
        paths = PathCofig(
            in_element_path=pattern_folder, 
            out_path=self.save_path,
            in_name=def_sew_pattern.name,
            out_name=f'{self.sew_pattern.name}_3D',
            body_name='mean_all',  
            smpl_body=False,   # NOTE: depends on chosen body model
            add_timestamp=False
        )

        if not self._drape_remote(pattern_folder, paths):
            # Local (CPU on most setups) simulation
            from seweasy.meshgen.boxmeshgen import BoxMesh
            from seweasy.meshgen.simulation import run_sim

            # Generate and save garment box mesh (if not existent)
            garment_box_mesh = BoxMesh(paths.in_g_spec, props['sim']['config']['resolution_scale'])
            garment_box_mesh.load()
            garment_box_mesh.serialize(
                paths, store_panels=False, uv_config=props['render']['config']['uv_texture'])

            # TODOLOW Don't print progress to console with so many lines
            run_sim(
                garment_box_mesh.name,
                props,
                paths,
                save_v_norms=False,
                store_usd=False,  # NOTE: False for fast simulation!,
                optimize_storage=False,
                verbose=False
            )

        # Convert to displayable element
        self._export_display_glb(paths)

        self.paths_3d = paths
        self.loaded_drape_glb = None   # fresh sim supersedes any adopted drape
        self.is_in_3D = True

        return paths.out_el, paths.g_sim_glb.name

    def current_drape_bytes(self):
        """GLB bytes of the current, in-sync 3D result (None if there is
        no drape or the design changed since it was made)"""
        if not self.is_in_3D:
            return None
        for path in (self.paths_3d.g_sim_glb if self.paths_3d else None,
                     self.loaded_drape_glb):
            if path is not None and path.exists():
                return path.read_bytes()
        return None

    def adopt_drape_glb(self, glb_bytes):
        """Adopt a stored drape (from a saved outfit) as the 3D result"""
        self.clear_3d()   # previous sim output belongs to another design
        path = self.save_path / 'adopted_drape.glb'
        path.write_bytes(glb_bytes)
        self.loaded_drape_glb = path
        self.is_in_3D = True
        return self.save_path, path.name

    @staticmethod
    def _drape_remote(pattern_folder, paths) -> bool:
        """Try draping on the Modal GPU service (see modal_drape.py).
        Returns True if the sim outputs were produced remotely"""
        try:
            import modal_drape
        except ImportError:
            return False
        if not modal_drape.is_enabled():
            return False

        try:
            print('INFO::Draping on Modal GPU...')
            modal_drape.remote_drape(pattern_folder, paths)
            return True
        except KeyboardInterrupt as e:
            raise e
        except BaseException:
            traceback.print_exc()
            print('WARNING::Modal drape failed, falling back to local simulation')
            return False

    def _export_display_glb(self, paths):
        """Export the simulated garment as a GLB for the 3D viewer,
        tinted with the current fabric color, with button hardware if the
        design configures it"""
        mesh = trimesh.load_mesh(paths.g_sim)

        # enable double-sided material for nice viewing
        pbr_material = mesh.visual.material.to_pbr()
        pbr_material.doubleSided = True
        # The baked UV texture uses neutral white panels (see gui_sim_props),
        # so the base color factor acts as the fabric color
        pbr_material.baseColorFactor = display_to_base_rgba(self.fabric_color)
        mesh.visual.material = pbr_material

        # Button hardware: placed onto the draped surface (not simulated)
        discs = self._button_discs(mesh)
        if discs is not None:
            trimesh.Scene({'garment': mesh, 'buttons': discs}).export(
                paths.g_sim_glb)
        else:
            mesh.export(paths.g_sim_glb)

    def _button_discs(self, garment_mesh):
        """Trimesh of button discs for the current design, or None"""
        btn = self.design_params.get('buttons')
        if not btn or int(btn['count']['v']) <= 0:
            return None
        from seweasy.pattern.buttons import sample_seats, build_discs
        seats = sample_seats(
            garment_mesh.vertices, int(btn['count']['v']),
            float(btn['diameter']['v']))
        return build_discs(seats)

    def recolor_3d(self):
        """Re-export the last draped garment with the current fabric color
        (no re-simulation)"""
        if self.paths_3d is not None:
            self._export_display_glb(self.paths_3d)
            return self.paths_3d.out_el, self.paths_3d.g_sim_glb.name

        if self.loaded_drape_glb is not None and self.loaded_drape_glb.exists():
            # Adopted drape: re-tint the GLB in place (its texture is
            # neutral, the base color factor is the fabric color)
            garment = trimesh.load(self.loaded_drape_glb)
            geometries = garment.geometry.values() \
                if hasattr(garment, 'geometry') else [garment]
            for geom in geometries:
                geom.visual.material.baseColorFactor = \
                    display_to_base_rgba(self.fabric_color)
            garment.export(self.loaded_drape_glb)
            return self.save_path, self.loaded_drape_glb.name

        return None

    # Current state
    def is_design_sectioned(self):
        """Check if design parameters are grouped by sections: 
            the top level of design dictionary does not contain actual parameters    
        """
        for param in self.design_params:
            if 'v' in self.design_params[param]:
                return False
        return True

    def is_slow_design(self) -> bool:
        """Check is parameters that result in slow pattern generation are enabled

            E.g. curved armhole evaluation
        """
        # Pants
        if (self.design_params['meta']['bottom']['v'] == 'Pants'):
            return True

        # Upper garment
        is_not_upper = self.design_params['meta']['upper']['v'] is None
        if is_not_upper:
            return False
        
        # Upper + fitted + strapless
        is_asymm = self.design_params['left']['enable_asym']['v']
        is_fitted = 'Fitted' in self.design_params['meta']['upper']['v']
        is_strapless = self.design_params['shirt']['strapless']['v']
        is_asymm_strapless = self.design_params['left']['shirt']['strapless']['v']

        is_strapless = is_fitted and is_strapless
        is_asymm_strapless = is_fitted and is_asymm_strapless

        # Has a hoody
        collar_component = self.design_params['collar']['component']['style']['v']
        has_hoody = collar_component is not None and 'Hood' in collar_component

        # Sleeve potential setup
        sleeves = self.design_params['sleeve']        
        is_sleeveless = sleeves['sleeveless']['v']
        is_curve = sleeves['armhole_shape']['v'] == 'ArmholeCurve'
        is_curve = not is_sleeveless and is_curve
        
        is_asym_sleeveless = self.design_params['left']['sleeve']['sleeveless']['v']
        is_asymm_curve = self.design_params['left']['sleeve']['armhole_shape']['v'] == 'ArmholeCurve'
        is_asymm_curve = not is_asym_sleeveless and is_asymm_curve

        if is_asymm:
            right_check = (not is_strapless) and is_curve
            left_check = (not is_asymm_strapless) and is_asymm_curve
            return right_check or left_check
        else:
            return (not is_strapless) and is_curve or has_hoody

    def save(self, pack=True, save_pattern: Optional[MetaGarment]=None):
        """Save current garment design to self.save_path

            * pack=True (user download): a single true-scale, tiled,
              print-ready PDF
            * pack=False (internal, e.g. the 3D pipeline): serialized
              pattern spec folder
        """
        # Save current pattern
        if save_pattern is None:
            if self.sew_pattern is None:   # deferred initial draft not run yet
                self.reload_garment()
            save_pattern = self.sew_pattern

        pattern = save_pattern.assembly()

        # Merge the user's per-panel stiffness overrides on top of any garment
        # default, so the 3D drape uses them
        if self.panel_stiffness:
            pattern.pattern.setdefault('panel_stiffness', {}).update(
                self.panel_stiffness)

        if pack:
            # Single user deliverable: print-at-home PDF
            # (raises EmptyPatternError if there is nothing to print)
            self.saved_garment_archive = save_print_pdf(
                pattern,
                self.save_path / f'{pattern.name}_print.pdf'
            )
            print(f'Success! {self.sew_pattern.name} print PDF saved to {self.saved_garment_archive}')
            return self.saved_garment_archive

        # Internal spec serialization (JSON + parameter files)
        self.saved_garment_folder = Path(pattern.serialize(
            self.save_path,
            to_subfolder=True,
            with_3d=False, with_text=False, view_ids=False,
            empty_ok=True
        ))
        self.body_params.save(self.saved_garment_folder)

        with open(self.saved_garment_folder / 'design_params.yaml', 'w') as f:
            yaml.dump(
                {'design': self.design_params},
                f,
                default_flow_style=False,
                sort_keys=False
            )

        print(f'Success! {self.sew_pattern.name} saved to {self.saved_garment_folder}')
        return self.saved_garment_folder

