"""Garment-version library and outfit composer for signed-in and guest users."""
from copy import deepcopy
from nicegui import app, ui

from webapp.wardrobe import Wardrobe


def wardrobe_ui(state):
    store = Wardrobe(state.user['email'] if state.user else None, app.storage.user)
    pattern = state.pattern_state
    selected = []
    switching = False

    def label(item):
        return f'{item["name"]} · v{item["version"]}'

    async def apply(items, active=0, solo=False):
        nonlocal switching
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
            switching = True
            editing.set_options({i: label(g) for i, g in enumerate(items)}, value=active)
            editing.set_visibility(not solo)
            solo_button.set_visibility(not solo)
        finally:
            switching = False
            state.toggle_param_update_events(state.ui_design_refs)

    async def switch_item(e):
        if switching or e.value is None or not pattern.outfit_items:
            return
        pattern.sync_outfit_garment()
        await apply(pattern.outfit_items, int(e.value))

    async def solo():
        pattern.sync_outfit_garment()
        await apply([pattern.outfit_items[pattern.active_garment]], solo=True)

    async def save_garment():
        try:
            version = store.save_garment(garment_name.value, pattern.design_params, pattern.garment_appearance())
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return
        if pattern.outfit_items:
            pattern.outfit_items[pattern.active_garment] = deepcopy(version)
            editing.set_options({i: label(g) for i, g in enumerate(pattern.outfit_items)}, value=pattern.active_garment)
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
        current = pattern.outfit_items[pattern.active_garment]['name'] if pattern.outfit_items else ''
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
            return
        await apply(outfit['garments'])
        ui.notify(f'Saved outfit “{outfit["name"]}”', type='positive')
        outfit_dialog.close()

    async def open_outfit(outfit):
        selected[:] = deepcopy(outfit['garments'])
        outfit_name.set_value(outfit['name'])
        refresh_composer()
        await preview()

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
        if pattern.outfit_items:
            pattern.sync_outfit_garment()
            selected[:] = deepcopy(pattern.outfit_items)
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

    ui.button('Save garment', on_click=show_save).props('outline size=sm icon=bookmark_add')
    ui.button('Outfits', on_click=show_outfits).props('outline size=sm icon=checkroom')
    editing = ui.select({i: label(g) for i, g in enumerate(pattern.outfit_items)},
                        value=pattern.active_garment if pattern.outfit_items else None,
                        label='Editing garment', on_change=switch_item).props('outlined dense options-dense').classes('w-full')
    editing.set_visibility(bool(pattern.outfit_items))
    solo_button = ui.button('Edit this garment alone', on_click=solo).props('flat size=sm')
    solo_button.set_visibility(bool(pattern.outfit_items))
