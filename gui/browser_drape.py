"""NiceGUI bridge for the browser cloth solver and CPU-only scene preparation."""
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from nicegui import app, ui
from nicegui.element import Element

ROOT = Path(__file__).resolve().parents[1]
app.add_static_files('/webgpu', ROOT / 'gui/webgpu', max_cache_age=0)


class BrowserDrape(Element, component='browser_drape.js'):
    def __init__(self, fabric_color, body_color):
        super().__init__()
        ui.add_css((Path(__file__).with_suffix('.css')).read_text())
        self._props.update(scene_url='', active=False, preparing=True, error='',
                           fabric_color=fabric_color, panel_colors={},
                           panel_fabrics=None,
                           body_color=body_color, show_body=True)

    def configure(self, **props):
        self._props.update(props)
        self.update()


@dataclass(frozen=True)
class SceneDraft:
    pattern: object
    measurements: dict
    colors: dict
    fabrics: dict
    garment: str
    garment_types: dict
    materials: dict = None


def snapshot_scene(pattern_state):
    """Copy a completed draft so meshing can run alongside subsequent 2D edits."""
    from seweasy.pattern.core import BasicPattern
    colors, fabrics = pattern_state.display_panel_colors(), pattern_state.display_panel_fabrics()
    assembled = pattern_state.sew_pattern.assembly()
    pattern = BasicPattern()
    pattern.name, pattern.spec = assembled.name, deepcopy(assembled.spec)
    pattern.pattern, pattern.properties = pattern.spec['pattern'], pattern.spec['properties']
    items = getattr(pattern_state, 'outfit_items', [])
    if not items:
        pattern.pattern.setdefault('panel_stiffness', {}).update(pattern_state.panel_stiffness)
    upper = pattern_state.design_params['meta']['upper']['v']
    garment = 'outfit' if items else 'element-top' if upper == 'ElementTubeTop' else 'current-design'
    return SceneDraft(pattern, deepcopy(pattern_state.body_params.params), deepcopy(colors), deepcopy(fabrics),
                      garment, {f'g{i}__': item['params']['meta']['upper']['v'] for i, item in enumerate(items)},
                      pattern_state.display_panel_materials())


def prepare_scene(pattern_state, target, resolution=1.5):
    """Triangulate the current design; all draping and rendering happens in JS.

    Both garment drafting and mannequin fitting use the selected measurements.
    The fitted surface supplies the renderer, normals, BVH and collision field.
    """
    from seweasy.meshgen.body_fit import fit_body
    from seweasy.meshgen.boxmeshgen import BoxMesh
    from seweasy.meshgen.webgpu import build_scene, panel_mesh_data
    from seweasy.pattern.core import BasicPattern

    draft = pattern_state if isinstance(pattern_state, SceneDraft) else snapshot_scene(pattern_state)
    pattern = draft.pattern
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='mesh-', dir=target.parent) as work:
        BasicPattern.serialize(pattern, work, to_subfolder=False)
        box = BoxMesh(Path(work) / f'{pattern.name}_specification.json', resolution)
        box.load()
        body, fit = fit_body(draft.measurements)
        data = panel_mesh_data(box, body)
        from seweasy.meshgen.browser_hardware import button_attachments
        buttons = button_attachments(box, pattern.pattern, data)
        from webapp.garment_materials import garment_settings, panel_weights
        materials = draft.materials or {}
        meta = dict(garment=draft.garment,
                    resolution_cm=resolution, panels=len(box.panelNames),
                    panel_stiffness=pattern.pattern.get('panel_stiffness', {}),
                    panel_weight_gsm=panel_weights(materials))
        scene = build_scene(data, meta, target.stem)
        # Damping, body friction and the contact margin are solver-wide, so they
        # are resolved from the assigned materials by rest area, not per piece.
        scene['material_settings'] = garment_settings(materials, scene['panel_area_m2'])
        scene['panel_materials'] = {panel: material.get('name', '')
                                    for panel, material in materials.items()}
        scene['buttons'] = buttons
        scene['body_fit'] = fit
        scene['body_note'] = fit['note']
        scene['panel_colors'] = draft.colors
        scene['garment_types'] = draft.garment_types
        scene['panel_fabrics'] = draft.fabrics
        target.write_text(json.dumps(scene, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    return target
