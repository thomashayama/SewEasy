"""Saved fabrics reach a drape: per-piece mass and bending, solver-wide contact."""
import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import yaml
from PIL import Image

from assets.bodies.body_params import BodyParameters
from assets.garment_programs.dress_shirt import DressShirt
from gui.gui_pattern import GUIPattern
from seweasy.pattern.core import BasicPattern
from webapp import fabrics, garment_materials as materials
from webapp.base_garments import appearance
from webapp.fabric_formats import properties
from webapp.wardrobe import Wardrobe

POPLIN = 'standard:catalog:light-cotton-poplin'      # 100 g/m², bending 8e-6/5e-6
DENIM = 'standard:catalog:cotton-denim'


def raster():
    from webapp.thumbnail_cache import SIZE
    out = BytesIO()
    Image.new('RGB', SIZE, '#a6bfd7').save(out, format='WEBP')
    return 'data:image/webp;base64,' + base64.b64encode(out.getvalue()).decode()


def material(name='Test fabric', **values):
    """A library snapshot with only the named properties supplied."""
    props = properties()
    for key, value in values.items():
        props[key].update(value=value, origin='user')
    return dict(source_fabric_id='fabric-' + name.lower().replace(' ', '-'), name=name,
                standard=False, properties=props, solver_tuning={})


class MappingTest(unittest.TestCase):
    def test_bending_becomes_the_existing_multiplier_within_its_range(self):
        self.assertAlmostEqual(materials.stiffness_for(material(bend_warp=2e-5, bend_weft=2e-5)), 2.)
        # One isotropic value: the garment solver has no warp/weft axis.
        self.assertAlmostEqual(materials.stiffness_for(material(bend_warp=3e-5, bend_weft=1e-5)), 2.)
        self.assertAlmostEqual(materials.stiffness_for(material(bend_warp=1e-5)), 1.)
        self.assertEqual(materials.stiffness_for(material(bend_warp=1e-9)), .5)
        self.assertEqual(materials.stiffness_for(material(bend_warp=1.)), 30.)
        self.assertIsNone(materials.stiffness_for(material(weight=120.)))
        preset = dict(material(), solver_tuning=dict(bend_multiplier=9., origin='estimated'))
        self.assertAlmostEqual(materials.stiffness_for(preset), 9.)

    def test_unsupported_measurements_are_carried_not_applied(self):
        applied = materials.applied(material(weight=120., stretch_warp=1600., shear=90., damping=3.))
        self.assertEqual(applied['weight_gsm'], 120.)
        self.assertEqual(applied['damping'], 3.)
        self.assertIsNone(applied['stiffness'])
        self.assertEqual(applied['stored_only'], ['shear', 'stretch_warp'])
        self.assertEqual(materials.SUPPORT['stretch_warp'][0], 'stored')
        self.assertEqual(materials.SUPPORT['weight'][0], 'piece')

    def test_solver_wide_controls_weigh_pieces_by_rest_area(self):
        assigned = {'skirt': material(damping=10., friction=.9, thickness=.2),
                    'lining': material(damping=2., friction=.1, thickness=.1)}
        settings = materials.garment_settings(assigned, {'skirt': .9, 'lining': .1})
        self.assertAlmostEqual(settings['damping'], 9.2)
        self.assertAlmostEqual(settings['friction'], .82)
        # A thin fabric cannot lower the solver's numerical contact margin.
        self.assertEqual(settings['thickness'], materials.MIN_CLEARANCE_M)
        thick = materials.garment_settings({'coat': material(thickness=9.)}, {'coat': 1.})
        self.assertAlmostEqual(thick['thickness'], .009)
        self.assertEqual(thick['damping'], materials.DEFAULT_DAMPING)
        self.assertEqual(materials.garment_settings({}, {}), {})
        # One slippery cuff on an otherwise unassigned shirt barely moves the garment.
        cuff = materials.garment_settings({'cuff': material(friction=0.)}, {'cuff': .02, 'body': .98})
        self.assertAlmostEqual(cuff['friction'], materials.DEFAULT_FRICTION * .98)


class AssignmentTest(unittest.TestCase):
    def setUp(self):
        self.pattern = GUIPattern(draft=False)
        self.pattern.reload_garment()
        self.panels = list(self.pattern.panel_svg_paths)[:2]

    def tearDown(self):
        self.pattern.release()

    def assign(self, panels, identity):
        self.pattern.edit_panel_fabrics(panels, 'material', identity,
                                        fabrics.library_snapshot(None, identity))

    def test_assignment_detaches_the_fabric_and_sets_its_drape(self):
        p = self.pattern
        self.assign(self.panels[:1], POPLIN)
        panel = self.panels[0]
        self.assertEqual(p.panel_materials[panel], POPLIN)
        saved = p.materials[POPLIN]
        self.assertEqual(saved['source_fabric_id'], POPLIN)
        self.assertEqual(saved['properties']['weight']['value'], 100.)
        # Measurement branches and textures stay in the library.
        self.assertNotIn('curves', saved)
        self.assertAlmostEqual(p.panel_stiffness[panel], .65)
        self.assertEqual(p.panel_fabric_settings([panel])[panel]['material'], POPLIN)
        self.assertEqual(p.panel_fabric_settings([panel])[panel]['material_name'], 'Lightweight cotton poplin')
        self.assertEqual(p.display_panel_materials()[panel]['name'], 'Lightweight cotton poplin')
        # A later library edit cannot reach a garment already cut from it.
        catalog = fabrics.library_snapshot(None, POPLIN)
        catalog['properties']['weight']['value'] = 999.
        self.assertEqual(p.materials[POPLIN]['properties']['weight']['value'], 100.)

    def test_a_second_fabric_replaces_only_the_pieces_it_is_applied_to(self):
        p = self.pattern
        self.assign(self.panels, POPLIN)
        self.assign(self.panels[1:], DENIM)
        self.assertEqual([p.panel_materials[n] for n in self.panels], [POPLIN, DENIM])
        self.assertEqual(set(p.materials), {POPLIN, DENIM})
        self.assertGreater(p.panel_stiffness[self.panels[1]], p.panel_stiffness[self.panels[0]])
        p.edit_panel_fabrics(self.panels[1:], 'reset')
        self.assertEqual(set(p.materials), {POPLIN})       # the unused copy is dropped
        self.assertNotIn(self.panels[1], p.display_panel_materials())

    def test_keeping_a_material_while_retuning_its_drape(self):
        p = self.pattern
        self.assign(self.panels[:1], POPLIN)
        p.edit_panel_fabrics(self.panels[:1], 'stiffness', 12.)
        settings = p.panel_fabric_settings(self.panels[:1])[self.panels[0]]
        self.assertEqual(settings['stiffness'], 12.)
        self.assertEqual(settings['material'], POPLIN)

    def test_a_fabric_with_a_display_color_tints_the_pieces_cut_from_it(self):
        p = self.pattern
        panel, other = self.panels
        p.edit_panel_fabrics([panel], 'kind', 'stripe')
        navy = dict(fabrics.library_snapshot(None, DENIM), display_color='#1f3a5f')
        p.edit_panel_fabrics([panel], 'material', DENIM, navy)
        self.assertEqual(p.panel_colors[panel], '#1f3a5f')
        self.assertEqual(p.panel_fabrics[panel]['bg'], '#1f3a5f')     # the print keeps its motif
        self.assertEqual(p.panel_fabrics[panel]['kind'], 'stripe')
        # A fabric without a colour leaves the piece's own colour alone.
        p.edit_panel_fabrics([other], 'bg', '#aa5500')
        plain = material('Undyed sample', weight=120.)
        p.edit_panel_fabrics([other], 'material', plain['source_fabric_id'], plain)
        self.assertEqual(p.panel_colors[other], '#aa5500')
        # Every common fabric brings a representative shade of its own.
        self.assign([other], POPLIN)
        self.assertEqual(p.panel_colors[other], '#f3f1ea')
        p.edit_panel_fabrics([panel], 'bg', '#ffffff')                # and stays recolourable
        self.assertEqual(p.panel_materials[panel], DENIM)

    def textured(self, back=False):
        """A library snapshot of an imported fabric that brings its own base-colour map."""
        from test_fabrics import appearance_package
        from webapp import fabric_formats as fmt
        content = fmt.import_fabric(appearance_package(back=back), 'lawn.u3ma')
        return dict(source_fabric_id='fabric-lawn', name='Printed cotton lawn', standard=False,
                    properties=content['properties'], solver_tuning={}, texture_maps=content['texture_maps'])

    def test_a_piece_shows_its_fabrics_own_map_until_it_is_given_a_look_of_its_own(self):
        p = self.pattern
        panel, other = self.panels
        p.edit_panel_fabrics([panel], 'bg', '#aa5500')          # an earlier colour would hide the map
        lawn = self.textured()
        p.edit_panel_fabrics([panel], 'material', 'fabric-lawn', lawn)
        self.assertNotIn(panel, p.panel_colors)
        self.assertNotIn(panel, p.panel_fabrics)                # the map is derived, never stored as a print
        specs = p.display_panel_fabrics()
        self.assertEqual(specs[panel]['kind'], 'texture')
        self.assertNotIn(other, specs)
        textures = p.display_fabric_textures(specs)
        self.assertEqual(list(textures), [specs[panel]['texture']])
        maps = textures[specs[panel]['texture']]
        self.assertEqual(maps['back'], maps['front'])            # U3M: no back of its own uses the front
        self.assertEqual(maps['front']['size_mm'], lawn['texture_maps']['front']['size_mm'])
        self.assertEqual(p.panel_fabric_settings([panel])[panel]['kind'], 'texture')
        # Two pieces cut from it still carry one copy of the map.
        p.edit_panel_fabrics([other], 'material', 'fabric-lawn', lawn)
        self.assertEqual(len(p.display_fabric_textures()), 1)
        # The 2D pattern tiles the map at its physical size: 256 px at 300 dpi is 2.1673 cm.
        svg = p.svg_path().read_text(encoding='utf-8')
        self.assertEqual(svg.count('data:image/webp;base64,'), 1)
        import re
        from seweasy.pattern.wrappers import VisPattern
        tile = re.search(r'<pattern height="([\d.]+)" id="seweasy_fabric_map_0"[^>]* width="([\d.]+)"', svg)
        for drawn in tile.groups():
            self.assertAlmostEqual(float(drawn), 256 / 300 * 2.54 * VisPattern().px_per_unit, places=6)
        self.assertEqual(svg.count('fill="url(#seweasy_fabric_map_0)"'), 2)
        # Recolouring the piece replaces the map but not what the piece is cut from.
        p.edit_panel_fabrics([panel], 'bg', '#123456')
        self.assertEqual(p.display_panel_fabrics()[panel]['kind'], 'plain')
        self.assertEqual(set(p.panel_fabrics[panel]), {'kind', 'fg', 'bg', 'scale'})
        self.assertEqual(p.panel_materials[panel], 'fabric-lawn')
        self.assertEqual(p.display_panel_fabrics()[other]['kind'], 'texture')

    def test_a_wrong_side_map_and_validation_travel_with_the_garment(self):
        p = self.pattern
        panel = self.panels[0]
        lawn = self.textured(back=True)
        p.edit_panel_fabrics([panel], 'material', 'fabric-lawn', lawn)
        maps = next(iter(p.display_fabric_textures().values()))
        self.assertNotEqual(maps['back']['image'], maps['front']['image'])
        self.assertEqual(maps['back']['pixels'], [64, 32])
        look = appearance(p.garment_appearance())
        self.assertEqual(set(look['materials']['fabric-lawn']['texture_maps']), {'front', 'back'})
        store = Wardrobe(storage={})
        saved = store.save_garment('Lawn shirt', p.design_params, look)
        p.load_outfit([saved])
        p.reload_garment()
        shown = p.display_panel_fabrics()
        self.assertEqual(shown['g0__' + panel]['kind'], 'texture')
        # A garment never fetches an image: only its own embedded copy is accepted.
        for image in ('https://example.test/cloth.webp', 'data:image/svg+xml;base64,PHN2Zy8+', 'data:image/webp;base64,' + 'A' * 300_000):
            remote = deepcopy(look)
            remote['materials']['fabric-lawn']['texture_maps']['front']['image'] = image
            with self.subTest(image=image[:30]), self.assertRaises(ValueError):
                appearance(remote)
        unsized = deepcopy(look)
        unsized['materials']['fabric-lawn']['texture_maps']['front']['size_mm'] = [0, 10]
        with self.assertRaises(ValueError):
            appearance(unsized)

    def test_a_library_edit_reaches_a_garment_only_when_reapplied(self):
        p = self.pattern
        panel = self.panels[0]
        self.assign([panel], POPLIN)
        revised = fabrics.library_snapshot(None, POPLIN)
        revised['properties']['weight'].update(value=140., origin='user')
        self.assertNotEqual(revised, p.display_panel_materials()[panel])    # what the panel flags
        self.assertEqual(p.materials[POPLIN]['properties']['weight']['value'], 100.)
        p.edit_panel_fabrics([panel], 'material', POPLIN, revised)          # "Apply current fabric"
        self.assertEqual(p.display_panel_materials()[panel], revised)
        self.assertEqual(set(p.materials), {POPLIN})

    def test_two_garments_in_one_outfit_keep_separate_fabrics(self):
        p = self.pattern
        item = dict(name='Shirt', params=deepcopy(p.design_params), appearance=p.garment_appearance())
        p.load_outfit([item, deepcopy(item)])
        p.reload_garment()
        first = next(n for n in p.panel_svg_paths if n.startswith('g0__'))
        second = first.replace('g0__', 'g1__', 1)
        self.assign([first], POPLIN)
        self.assign([second], DENIM)
        p.sync_outfit_garment()
        looks = [item['appearance'] for item in p.outfit_items]
        self.assertEqual(set(looks[0]['materials']), {POPLIN})
        self.assertEqual(set(looks[1]['materials']), {DENIM})
        assigned = p.display_panel_materials()
        self.assertEqual(assigned[first]['source_fabric_id'], POPLIN)
        self.assertEqual(assigned[second]['source_fabric_id'], DENIM)

    def test_changing_the_fabric_invalidates_the_saved_image_and_legacy_looks_load(self):
        p = self.pattern
        store = Wardrobe(storage={})
        legacy = store.save_garment('Legacy shirt', p.design_params,
                                    dict(fabric_color='#b7cde5', panel_colors={}, panel_fabrics={},
                                         panel_stiffness={}, panel_materials={}))
        p.load_outfit([legacy])
        self.assertEqual(p.materials, {})
        self.assertEqual(p.display_panel_materials(), {})
        store.save_thumbnail('garment', legacy['id'], raster(), items=[legacy])
        self.assertIn('garment:' + legacy['id'], store.read().get('thumbnails', {}))
        p.reload_garment()
        self.assign(list(p.panel_svg_paths)[:1], POPLIN)
        store.save_garment('Legacy shirt', p.design_params, p.garment_appearance(),
                           parent_id=legacy['id'], expected_updated_at=legacy['updated_at'])
        self.assertNotIn('garment:' + legacy['id'], store.read().get('thumbnails', {}))

    def test_saved_garments_and_validation_carry_the_assignment(self):
        p = self.pattern
        self.assign(self.panels[:1], POPLIN)
        look = p.garment_appearance()
        store = Wardrobe(storage={})
        version = store.save_garment('Poplin shirt', p.design_params, look)
        p.load_outfit([version])
        self.assertEqual(p.materials[POPLIN]['name'], 'Lightweight cotton poplin')
        checked = appearance(deepcopy(look))
        self.assertEqual(checked['materials'][POPLIN]['source_fabric_id'], POPLIN)
        self.assertAlmostEqual(checked['panel_stiffness'][self.panels[0]], .65)
        # An agent may name a material a previous update already saved.
        appearance(dict(panel_materials={'front': POPLIN}))
        with self.assertRaises(ValueError):
            appearance(dict(panel_materials={'front': 'nonsense id'}))
        with self.assertRaises(ValueError):
            appearance(dict(materials={POPLIN: dict(name='Poplin', properties={})},
                            panel_materials={'front': POPLIN}))
        with self.assertRaises(ValueError):
            appearance(dict(materials={POPLIN: look['materials'][POPLIN]},
                            panel_materials={'front': 'standard:catalog:missing'}))


class SceneMassTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:                            # Meshing needs the simulation extras (see docs/Installation.md).
            import trimesh
            from seweasy.meshgen.boxmeshgen import BoxMesh
            from seweasy.meshgen.webgpu import build_scene, panel_mesh_data
        except ImportError as missing:
            raise unittest.SkipTest(f'Mesh preparation is unavailable here: {missing}')
        cls.build_scene, cls.panel_mesh_data = staticmethod(build_scene), staticmethod(panel_mesh_data)
        body = BodyParameters('assets/bodies/mean_all.yaml')
        design = yaml.safe_load(Path('assets/design_params/dress-shirt.yaml').read_text())['design']
        pattern = DressShirt(body, design).assembly()
        with TemporaryDirectory() as folder:
            BasicPattern.serialize(pattern, folder, to_subfolder=False)
            box = BoxMesh(Path(folder) / 'DressShirt_specification.json', 1.5)
            box.load()
            cls.data = panel_mesh_data(box, trimesh.load('assets/bodies/mean_all.obj', process=False))
            cls.meta = dict(garment='dress-shirt', resolution_cm=1.5, panels=len(box.panelNames),
                            panel_stiffness=pattern.pattern['panel_stiffness'])

    def scene(self, weights):
        return self.build_scene(self.data, dict(self.meta, panel_weight_gsm=weights), 'materials-test')

    def test_each_piece_weighs_its_own_material_times_its_rest_area(self):
        panel = str(self.data['face_panels'][0])
        plain = self.scene({})
        self.assertAlmostEqual(plain['mass_density_kg_m2'], .3)
        heavy = self.scene({panel: 600.})
        for index, (before, after) in enumerate(zip(plain['inverse_mass'], heavy['inverse_mass'])):
            ratio = before / after
            self.assertAlmostEqual(ratio, 2. if heavy['vertex_panels'][index] == panel else 1., places=6)
        area = heavy['panel_area_m2'][panel]
        mass = sum(1 / w for w, p in zip(heavy['inverse_mass'], heavy['vertex_panels']) if p == panel)
        self.assertAlmostEqual(mass, area * .6, places=9)
        total = sum(1 / w for w in heavy['inverse_mass'])
        self.assertAlmostEqual(heavy['mass_density_kg_m2'], total / sum(heavy['panel_area_m2'].values()))
        self.assertGreater(heavy['mass_density_kg_m2'], .3)
        self.assertEqual(heavy['panel_weight_gsm'], {panel: 600.})

    def test_a_seam_between_two_materials_keeps_both_masses(self):
        panels = sorted({str(p) for p in self.data['face_panels']})[:2]
        scene = self.scene({panels[0]: 120., panels[1]: 480.})
        masses = {}
        for weight, panel in zip(scene['inverse_mass'], scene['vertex_panels']):
            masses.setdefault(panel, []).append(1 / weight)
        for panel, gsm in zip(panels, (120., 480.)):
            self.assertAlmostEqual(sum(masses[panel]), scene['panel_area_m2'][panel] * gsm / 1000, places=9)
        self.assertTrue(all(np.isfinite(scene['inverse_mass'])))


if __name__ == '__main__':
    unittest.main()
