"""NiceGUI bridge for the browser cloth solver and CPU-only scene preparation."""
import json
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


def prepare_scene(pattern_state, target, resolution=1.5):
    """Triangulate the current design; all draping and rendering happens in JS.

    Both garment drafting and mannequin fitting use the selected measurements.
    The fitted surface supplies the renderer, normals, BVH and collision field.
    """
    from seweasy.meshgen.body_fit import fit_body
    from seweasy.meshgen.boxmeshgen import BoxMesh
    from seweasy.meshgen.webgpu import build_scene, panel_mesh_data
    from seweasy.pattern.core import BasicPattern

    pattern = pattern_state.sew_pattern.assembly()
    if not getattr(pattern_state, 'outfit_items', []):
        pattern.pattern.setdefault('panel_stiffness', {}).update(pattern_state.panel_stiffness)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='mesh-', dir=target.parent) as work:
        BasicPattern.serialize(pattern, work, to_subfolder=False)
        box = BoxMesh(Path(work) / f'{pattern.name}_specification.json', resolution)
        box.load()
        body, fit = fit_body(pattern_state.body_params.params)
        data = panel_mesh_data(box, body)
        from seweasy.meshgen.browser_hardware import button_attachments
        buttons = button_attachments(box, pattern.pattern, data)
        upper = pattern_state.design_params['meta']['upper']['v']
        garment_type = ('outfit' if getattr(pattern_state, 'outfit_items', []) else
                        'element-top' if upper == 'ElementTubeTop' else 'current-design')
        meta = dict(garment=garment_type,
                    resolution_cm=resolution, panels=len(box.panelNames),
                    panel_stiffness=pattern.pattern.get('panel_stiffness', {}))
        scene = build_scene(data, meta, target.stem)
        scene['buttons'] = buttons
        scene['body_fit'] = fit
        scene['body_note'] = fit['note']
        scene['panel_colors'] = pattern_state.display_panel_colors()
        scene['garment_types'] = {f'g{i}__': item['params']['meta']['upper']['v']
                                  for i, item in enumerate(getattr(pattern_state, 'outfit_items', []))}
        scene['panel_fabrics'] = pattern.pattern.get('panel_fabrics', {})
        if pattern.pattern.get('fabric'):
            scene['panel_fabrics'].update({p: pattern.pattern['fabric'] for p in box.panelNames
                                          if p not in pattern_state.panel_colors})
        target.write_text(json.dumps(scene, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    return target
