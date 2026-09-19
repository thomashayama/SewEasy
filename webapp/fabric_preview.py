"""Private, weight-only swatch experiment using the browser cloth solver."""
from copy import deepcopy
import math

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from webapp import auth, fabrics
from webapp.fabric_formats import number

REFERENCE_GSM = 300.0


def default_scene():
    from webapp.fabric_swatch import swatch_scene
    return swatch_scene()


def with_weight(scene, gsm):
    """Scale lumped vertex masses, not gravity or animation speed."""
    gsm = number(gsm)
    if gsm <= 0:
        raise ValueError('Supply a fabric weight greater than zero to compare draping.')
    result = deepcopy(scene)
    original = result.get('mass_density_kg_m2', .3) * 1000
    result['inverse_mass'] = [value * original / gsm for value in scene['inverse_mass']]
    if any(not math.isfinite(value) or (source != 0 and not 1.17549435e-38 <= value <= 3.4028235e38)
           for source, value in zip(scene['inverse_mass'], result['inverse_mass'])):
        raise ValueError('This weight exceeds the numeric range of the browser simulator.')
    result['mass_density_kg_m2'] = gsm / 1000
    masses = scene.get('vertex_mass_kg', [1/w if w else 0 for w in scene['inverse_mass']])
    result['vertex_mass_kg'] = [mass * gsm / original for mass in masses]
    result['fabric_test'] = dict(weight_gsm=gsm, scope='weight-only',
                               total_mass_kg=sum(result['vertex_mass_kg']))
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
    from gui.fabric_swatch import FabricSwatch
    record = await run.io_bound(fabrics.get_fabric, email, identity)
    weight = record['content']['properties']['weight']['value']
    if weight is None:
        ui.notify('Enter a fabric weight first.', type='warning')
        return
    with ui.context.client, ui.dialog().props('maximized') as dialog, ui.card().classes('w-full h-full gap-3 overflow-auto'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-0'):
                ui.label('Fabric swatch test').classes('se-section-label text-xl')
                ui.label(record['name']).classes('se-param-label')
            ui.button(icon='close', on_click=dialog.close).props('flat round aria-label="Close fabric comparison"')
        ui.label('An 80 mm strip bends under its own weight. Both samples share the same assumed stiffness; '
                 'only their weight changes.').classes('se-param-label')
        FabricSwatch(identity, record['name'], weight).classes('w-full')
    dialog.open()
    await dialog
    dialog.delete()  # Unmount the test and release its GPU resources.
