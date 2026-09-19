"""Weight-only feasibility experiment using the production browser cloth solver.

Both stages use identical geometry, constraints and default mannequin. Only
areal density changes. This is deliberately not a calibrated fabric prediction.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from webapp import auth, fabrics
from webapp.fabric_formats import number

REFERENCE_GSM = 300.0
_cached_scene = None
_lock = Lock()


def default_scene():
    global _cached_scene
    with _lock:
        if _cached_scene is None:
            from assets.bodies.body_params import BodyParameters
            from assets.garment_programs.meta_garment import MetaGarment
            from gui.browser_drape import SceneDraft, prepare_scene
            from webapp.garment_catalog import starter_item
            root = Path(__file__).resolve().parents[1]
            body = BodyParameters(root / 'assets/bodies/mean_all.yaml')
            params = starter_item('Shirt')['params']
            pattern = MetaGarment('Fabric_test_tee', body, params).assembly()
            draft = SceneDraft(pattern, deepcopy(body.params), {}, {}, 'current-design', {})
            # One CPU triangulation shared by all tests; no personal measurements.
            with TemporaryDirectory(prefix='seweasy-fabric-test-') as folder:
                target = Path(folder) / 'reference.json'
                prepare_scene(draft, target, resolution=2.5)
                _cached_scene = json.loads(target.read_text(encoding='utf-8'))
    return _cached_scene


def with_weight(scene, gsm):
    """Scale lumped vertex masses, not gravity or animation speed."""
    gsm = number(gsm)
    if gsm <= 0:
        raise ValueError('Supply a fabric weight greater than zero to compare draping.')
    result = deepcopy(scene)
    original = result.get('mass_density_kg_m2', .3) * 1000
    result['inverse_mass'] = [value * original / gsm for value in scene['inverse_mass']]
    if any(not math.isfinite(value) or not 1.17549435e-38 <= value <= 3.4028235e38
           for value in result['inverse_mass']):
        raise ValueError('This weight exceeds the numeric range of the browser simulator.')
    result['mass_density_kg_m2'] = gsm / 1000
    result['fabric_test'] = dict(weight_gsm=gsm, scope='weight-only',
                               total_mass_kg=sum(1 / value for value in result['inverse_mass']))
    return result


def scene_for(email, identity, reference=False):
    record = fabrics.get_fabric(email, identity)
    weight = record['content']['properties']['weight']['value']
    if weight is None or weight <= 0:
        raise ValueError('Supply a fabric weight to compare draping.')
    scene = with_weight(default_scene(), REFERENCE_GSM if reference else weight)
    scene['name'] = f'fabric-{identity}-{"reference" if reference else "measured"}'
    return scene


def register(app):
    @app.get('/fabric-preview/{identity}')
    def preview(request: Request, identity: str, reference: bool = False):
        user = auth.current_user(request)
        if not user:
            raise HTTPException(404, 'Fabric unavailable.')
        try:
            scene = scene_for(user['email'], identity, reference)
        except ValueError:
            raise HTTPException(404, 'Fabric unavailable or missing its weight.') from None
        return JSONResponse(scene, headers={'Cache-Control': 'private, no-store',
                                           'X-Content-Type-Options': 'nosniff'})


async def comparison_dialog(email, identity):
    from nicegui import run, ui
    from gui.browser_drape import BrowserDrape
    record = await run.io_bound(fabrics.get_fabric, email, identity)
    weight = record['content']['properties']['weight']['value']
    if weight is None:
        ui.notify('Enter a fabric weight first.', type='warning')
        return
    with ui.context.client, ui.dialog().props('maximized') as dialog, ui.card().classes('w-full h-full gap-3'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Compare fabric weight').classes('se-section-label text-xl')
                ui.label(record['name']).classes('se-param-label')
            ui.button(icon='close', on_click=dialog.close).props('flat round aria-label="Close fabric comparison"')
        ui.label('Only weight changes. Bending, stretch and friction use the same defaults. '
                 'This is a weight experiment, not a calibrated prediction of this fabric.').classes('se-param-label')
        with ui.element('div').classes('grid grid-cols-1 md:grid-cols-2 w-full flex-1 min-h-0 gap-4 overflow-auto'):
            for reference, title in ((True, 'Current default · 300 g/m²'), (False, f'Your fabric · {weight:.5g} g/m²')):
                with ui.column().classes('w-full gap-1 min-h-0'):
                    ui.label(title).classes('font-medium')
                    with ui.element('div').classes('w-full flex-1 min-h-[400px]'):
                        stage = BrowserDrape('#b7cde5', '#d2c8b9')
                        stage.configure(scene_url=f'/fabric-preview/{identity}?reference={str(reference).lower()}',
                                        active=True, preparing=False)
        ui.label('Drag each mannequin to see the cloth respond. Pause or reset using the corner controls.').classes('se-param-label')
    dialog.open()
    await dialog
    dialog.delete()  # Unmount both stages and release their GPU resources.
