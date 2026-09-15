"""Garment-version library and outfit composer for signed-in and guest users."""
from copy import deepcopy
import json
import re
from pathlib import Path
import yaml
from nicegui import app, ui

from webapp.wardrobe import Wardrobe


def wardrobe_ui(state):
    store = Wardrobe(state.user['email'] if state.user else None, app.storage.user)
    pattern = state.pattern_state
    selected = []
    saved_signature = None
    state._outfit_name = getattr(state, '_outfit_name', 'Untitled outfit')

    def garment_title(params):
        names = {'DressShirt': 'Dress shirt', 'FittedShirt': 'Fitted shirt', 'Shirt': 'Shirt',
                 'ElementTubeTop': 'Tube top', 'Pants': 'Trousers', 'SkirtCircle': 'Circle skirt',
                 'PencilSkirt': 'Pencil skirt'}
        parts = [v.get('v') for k, v in params.get('meta', {}).items() if k != 'wb' and v.get('v')]
        return ' + '.join(names.get(v, re.sub(r'(?<!^)(?=[A-Z])', ' ', v)) for v in parts) or 'New garment'

    def current_items():
        pattern.sync_outfit_garment()
        return deepcopy(pattern.outfit_items) if pattern.outfit_items else [dict(
            id='draft', name=garment_title(pattern.design_params), version=0,
            params=deepcopy(pattern.design_params), appearance=pattern.garment_appearance())]

    def signature():
        return json.dumps(current_items(), sort_keys=True)

    def thumbnail(item):
        meta = item['params'].get('meta', {})
        color = item.get('appearance', {}).get('fabric_color') or '#b7cde5'
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            color = '#b7cde5'
        if meta.get('upper', {}).get('v'):
            outline = 'M24 12 15 16 5 37 16 42 22 31 21 68 51 68 50 31 56 42 67 37 57 16 48 12 42 20 36 24 30 20Z'
            detail = 'M30 13 36 24 42 13M36 24V68M23 61H49'
        elif meta.get('bottom', {}).get('v') == 'Pants':
            outline = 'M22 12H50L55 70H40L36 35 32 70H17Z'
            detail = 'M22 20H50M36 20V35'
        else:
            outline = 'M26 14H46L61 67Q36 74 11 67Z'
            detail = 'M25 21H47M29 24 23 66M43 24 49 66'
        return f'<svg viewBox="0 0 72 82" aria-hidden="true"><path d="{outline}" fill="{color}" stroke="#57728f" stroke-width="1.2"/><path d="{detail}" fill="none" stroke="#57728f" stroke-width=".8"/></svg>'

    async def edit_item(index):
        if pattern.outfit_items and index != pattern.active_garment:
            await apply(current_items(), index)
        state.ui_design_settings.open()

    async def remove_item(index):
        items = current_items()
        if len(items) > 1:
            items.pop(index)
            await apply(items, min(pattern.active_garment, len(items) - 1))

    def refresh_studio():
        if state.ui_outfit_list.client.id not in state.ui_outfit_list.client.instances:
            return
        items = current_items()
        state.ui_outfit_title.set_text(state._outfit_name)
        state.ui_draft_status.set_text('Saved' if saved_signature == signature() else 'Unsaved changes')
        state.ui_outfit_list.clear()
        with state.ui_outfit_list:
            for index, item in enumerate(items):
                active = index == pattern.active_garment
                with ui.element('div').classes('se-garment-row' + (' is-active' if active else '')):
                    with ui.button(on_click=lambda _, i=index: edit_item(i)).props(
                            f'flat no-caps aria-label="Edit garment {index + 1}"').classes('se-garment-card'):
                        ui.html(thumbnail(item)).classes('se-garment-thumb')
                        with ui.column().classes('se-garment-caption'):
                            ui.label(item['name']).classes('se-garment-name')
                            ui.label(f'Version {item["version"]}' if item.get('version') else 'Working draft').classes('se-garment-version')
                    with ui.button(icon='more_horiz').props(
                            f'flat round dense size=sm aria-label="Garment {index + 1} actions"').classes('se-garment-more'):
                        with ui.menu():
                            ui.menu_item('Edit design', lambda _, i=index: edit_item(i))
                            ui.menu_item('Save garment version', lambda _, i=index: save_item(i))
                            if len(items) > 1:
                                ui.menu_item('Remove from outfit', lambda _, i=index: remove_item(i))

    async def save_item(index):
        if pattern.outfit_items and index != pattern.active_garment:
            await apply(current_items(), index)
        show_save()

    def label(item):
        return f'{item["name"]} · v{item["version"]}'

    async def apply(items, active=0, solo=False):
        if not items:
            ui.notify('Add a saved garment first.', type='warning')
            return
        state.toggle_param_update_events(state.ui_design_refs)
        try:
            pattern.load_outfit(items, active)
            if solo:
                pattern.outfit_items = []
            state.update_design_params_ui_state(state.ui_design_refs, pattern.design_params)
            state.set_pattern_selection([], open_panel=False)
            await state.update_pattern_ui_state()
            refresh_studio()
        finally:
            state.toggle_param_update_events(state.ui_design_refs)

    async def save_garment():
        try:
            version = store.save_garment(garment_name.value, pattern.design_params, pattern.garment_appearance())
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return
        if pattern.outfit_items:
            pattern.outfit_items[pattern.active_garment] = deepcopy(version)
        else:
            await apply([version])
        refresh_studio()
        ui.notify(f'Saved {label(version)}', type='positive')
        save_dialog.close()

    with ui.dialog() as save_dialog, ui.card().classes('w-96 gap-3'):
        ui.label('Save garment version').classes('text-lg font-semibold')
        ui.label('Keeps this garment’s design, fabric print, colors and panel settings.').classes('text-sm text-stone-500')
        garment_name = ui.input('Garment name').props('outlined dense').classes('w-full')
        ui.label('Using an existing name creates a new version. Saved outfits keep their original versions.').classes('text-xs text-stone-500')
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=save_dialog.close).props('flat')
            ui.button('Save version', on_click=save_garment)

    def show_save():
        current = pattern.outfit_items[pattern.active_garment]['name'] if pattern.outfit_items else garment_title(pattern.design_params)
        garment_name.set_value(current)
        save_dialog.open()

    def refresh_composer():
        items_box.clear()
        with items_box:
            if not selected:
                ui.label('Add one or more saved garments.').classes('text-sm text-stone-500')
            for index, item in enumerate(selected):
                with ui.row().classes('w-full items-center justify-between gap-2'):
                    with ui.column().classes('gap-0'):
                        ui.label(label(item)).classes('font-medium')
                        kind = item['params'].get('fabric', {}).get('kind', {}).get('v', 'plain')
                        ui.label(f'{kind.replace("_", " ")} · {item.get("appearance", {}).get("fabric_color", "default color")}').classes('text-xs text-stone-500')
                    ui.button(icon='close', on_click=lambda _, i=index: remove(i)).props('flat dense size=sm').tooltip(f'Remove {item["name"]}')

    def remove(index):
        selected.pop(index)
        refresh_composer()

    def add():
        version = next((g for g in store.read()['garments'] if g['id'] == saved_garment.value), None)
        if version:
            selected.append(deepcopy(version))
            refresh_composer()
        else:
            ui.notify('Choose a saved garment version first.', type='warning')

    async def preview():
        if selected:
            await apply(selected)
            outfit_dialog.close()
        else:
            ui.notify('Add a saved garment first.', type='warning')

    async def save_outfit():
        nonlocal saved_signature
        try:
            if not (outfit_name.value or '').strip() or not selected:
                raise ValueError('An outfit needs a name and at least one garment.')
            versions = {g['id']: g for g in store.read()['garments']}
            for i, item in enumerate(selected):
                original = versions.get(item['id'])
                if not original or item['params'] != original['params'] or item['appearance'] != original['appearance']:
                    selected[i] = store.save_garment(item['name'], item['params'], item['appearance'])
            outfit = store.save_outfit(outfit_name.value, [g['id'] for g in selected])
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return False
        current = current_items()
        if pattern.outfit_items and len(current) == len(outfit['garments']) and all(
                a['params'] == b['params'] and a['appearance'] == b['appearance']
                for a, b in zip(current, outfit['garments'])):
            # Only version metadata changed. Keep the already warmed scene.
            pattern.outfit_items = deepcopy(outfit['garments'])
        else:
            await apply(outfit['garments'])
        state._outfit_name = outfit['name']
        saved_signature = signature()
        refresh_studio()
        ui.notify(f'Saved outfit “{outfit["name"]}”', type='positive')
        outfit_dialog.close()
        return True

    async def open_outfit(outfit):
        nonlocal saved_signature
        selected[:] = deepcopy(outfit['garments'])
        outfit_name.set_value(outfit['name'])
        refresh_composer()
        await preview()
        state._outfit_name = outfit['name']
        saved_signature = signature()
        refresh_studio()

    async def open_garment():
        item = next((g for g in store.read()['garments'] if g['id'] == saved_garment.value), None)
        if item:
            await apply([item], solo=True)
            outfit_dialog.close()

    with ui.dialog() as outfit_dialog, ui.card().classes('w-full max-w-xl gap-3'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Outfits & garments').classes('text-lg font-semibold')
            ui.button(icon='close', on_click=outfit_dialog.close).props('flat round dense aria-label="Close outfits"')
        if not state.user:
            ui.label('Saved for this browser on this installation.').classes('text-xs text-stone-500')
        saved_outfits = ui.column().classes('w-full gap-1')
        ui.separator()
        outfit_name = ui.input('Outfit name').props('outlined dense').classes('w-full')
        items_box = ui.column().classes('w-full gap-2')
        saved_garment = ui.select({}, label='Saved garment version', with_input=True).props('outlined dense options-dense').classes('w-full')
        with ui.row().classes('gap-2'):
            ui.button('Add to outfit', on_click=add).props('outline size=sm icon=add')
            ui.button('Open garment', on_click=open_garment).props('flat size=sm')
        with ui.row().classes('w-full justify-end'):
            ui.button('Preview outfit', on_click=preview).props('outline')
            ui.button('Save outfit', on_click=save_outfit)
        if state.user:
            with ui.expansion('Earlier saved designs').classes('w-full'):
                from webapp.gui_widgets import designs_ui
                designs_ui(state)

    def show_outfits():
        selected[:] = current_items()
        outfit_name.set_value('' if state._outfit_name == 'Untitled outfit' else state._outfit_name)
        library = store.read()
        saved_garment.set_options({g['id']: label(g) for g in reversed(library['garments'])})
        saved_outfits.clear()
        with saved_outfits:
            for outfit in reversed(library['outfits']):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label(f'{outfit["name"]} · {len(outfit["garments"])} garment(s)')
                    ui.button('Open', on_click=lambda _, o=outfit: open_outfit(o)).props('flat size=sm')
        refresh_composer()
        outfit_dialog.open()

    async def add_template(kind):
        params = yaml.safe_load((Path(__file__).resolve().parents[1] / 'assets/design_params/default.yaml').read_text())['design']
        for key in params['meta']:
            params['meta'][key]['v'] = None
        params['meta']['bottom' if kind in ('Pants', 'SkirtCircle') else 'upper']['v'] = kind
        if kind in ('Pants', 'SkirtCircle'):
            params['meta']['wb']['v'] = 'FittedWB'
        if kind == 'Pants':
            params['pants']['length']['v'] = .9
        items = current_items()
        if not any(v.get('v') for v in items[0]['params']['meta'].values()):
            items = []
        items.append(dict(id='draft', name=garment_title(params), version=0, params=params,
                          appearance=dict(fabric_color='#b7cde5' if kind != 'Pants' else '#414e62')))
        add_dialog.close()
        await apply(items, len(items) - 1)

    async def add_saved(item):
        items = current_items()
        items.append(deepcopy(item))
        add_dialog.close()
        await apply(items, len(items) - 1)

    with ui.dialog() as add_dialog, ui.card().classes('w-96 max-w-full gap-4'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Add garment').classes('text-lg font-semibold')
            ui.button(icon='close', on_click=add_dialog.close).props('flat round dense aria-label="Close add garment"')
        ui.label('Start with a garment').classes('se-param-label')
        with ui.element('div').classes('grid grid-cols-2 gap-2 w-full'):
            for kind, name in [('DressShirt', 'Dress shirt'), ('Shirt', 'Shirt'), ('Pants', 'Trousers'), ('SkirtCircle', 'Circle skirt')]:
                ui.button(name, on_click=lambda _, k=kind: add_template(k)).props('outline icon=add')
        ui.separator()
        ui.label('Your saved garments').classes('se-param-label')
        add_saved_box = ui.column().classes('w-full gap-1 max-h-72 overflow-auto')

    def show_add():
        add_saved_box.clear()
        with add_saved_box:
            garments = store.read()['garments']
            if not garments:
                ui.label('Saved versions will appear here.').classes('text-sm text-slate-500')
            for item in reversed(garments):
                ui.button(label(item), on_click=lambda _, g=item: add_saved(g)).props('flat icon=add').classes('w-full')
        add_dialog.open()

    # Header saving is deliberately a short dialog; the full library keeps the
    # existing version composer and access to older saved designs.
    with ui.dialog() as quick_save_dialog, ui.card().classes('w-96 max-w-full gap-3'):
        ui.label('Save outfit').classes('text-lg font-semibold')
        ui.label('Keeps each garment’s design, colors and fabric settings.').classes('text-sm text-slate-500')
        quick_name = ui.input('Outfit name').props('outlined dense').classes('w-full')
        if not state.user:
            ui.label('Saved in this browser. Sign in to keep outfits in your account.').classes('text-xs text-slate-500')
        async def quick_save():
            if not (quick_name.value or '').strip():
                ui.notify('Give the outfit a name.', type='warning')
                return
            selected[:] = current_items()
            outfit_name.set_value(quick_name.value)
            if await save_outfit():
                quick_save_dialog.close()
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=quick_save_dialog.close).props('flat')
            ui.button('Save', on_click=quick_save).props('unelevated')

    def show_quick_save():
        quick_name.set_value('' if state._outfit_name == 'Untitled outfit' else state._outfit_name)
        quick_save_dialog.open()

    state.show_outfits = show_outfits
    state.show_save_garment = show_save
    state.show_add_garment = show_add
    state.show_save_outfit = show_quick_save
    state.refresh_wardrobe = refresh_studio
    refresh_studio()
