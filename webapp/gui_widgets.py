"""NiceGUI widgets for account features, kept out of gui/callbacks.py to
minimize the diff against upstream GarmentCode."""

from nicegui import ui

from webapp import config, designs, profiles


def auth_header_ui(user):
    """Header controls: sign-in button, or user identity + logout"""
    if user:
        if user.get('picture'):
            ui.image(user['picture']).classes('w-8 h-8 rounded-full')
        ui.label(user.get('name') or user['email']).classes('text-white')
        ui.button('Log out',
                  on_click=lambda: ui.navigate.to('/auth/logout')) \
            .props('flat color=white no-caps')
    elif config.google_configured():
        ui.button('Sign in with Google',
                  on_click=lambda: ui.navigate.to('/auth/login')) \
            .props('outline color=white no-caps icon=login')


def _library_ui(email, *, noun, noun_plural, save_label, load_label,
                load_icon, snapshot, apply_item, list_items, save_item,
                get_item, delete_item):
    """Two buttons + dialogs for a user's library of named, saved items.

    * snapshot() -> dict payload of the current GUI state
    * apply_item(data) -> async, applies a loaded item to the GUI
    """

    # --- Save dialog ---
    def save_current():
        name = (name_input.value or '').strip()
        if not name:
            ui.notify(f'Give the {noun} a name', type='warning')
            return
        created = save_item(email, name, snapshot())
        ui.notify(f'{"Saved" if created else "Updated"} "{name}"',
                  type='positive')
        save_dialog.close()

    with ui.dialog() as save_dialog, ui.card().classes('items-center'):
        ui.label(f'Save current {noun} to your account')
        name_input = ui.input(
            label='Name', placeholder=f'e.g. My {noun}'
        ).classes('w-64').props('outlined dense')
        with ui.row():
            ui.button('Save', on_click=save_current)
            ui.button('Cancel', on_click=save_dialog.close).props('flat')

    # --- Load dialog ---
    async def load_and_apply(item_id: int):
        data = get_item(email, item_id)
        if data is None:
            ui.notify(f'Saved {noun} not found', type='negative')
            return
        await apply_item(data)
        ui.notify(f'Applied "{data["name"]}"', type='positive')
        load_dialog.close()

    def remove_item(item_id: int):
        delete_item(email, item_id)
        refresh_list()

    def refresh_list():
        item_list.clear()
        with item_list:
            rows = list_items(email)
            if not rows:
                ui.label(f'No saved {noun_plural} yet').classes('text-gray-500')
            for row in rows:
                with ui.row().classes('items-center w-full justify-between'):
                    ui.label(row['name'])
                    with ui.row():
                        ui.button(
                            'Load',
                            on_click=lambda _, iid=row['id']: load_and_apply(iid))
                        ui.button(
                            icon='delete',
                            on_click=lambda _, iid=row['id']: remove_item(iid)
                        ).props('flat color=negative')

    with ui.dialog() as load_dialog, ui.card().classes('items-center w-96'):
        ui.label(load_label)
        item_list = ui.column().classes('w-full')
        ui.button('Close', on_click=load_dialog.close).props('flat')

    def open_load_dialog():
        refresh_list()
        load_dialog.open()

    # --- The buttons themselves ---
    ui.button(save_label, on_click=save_dialog.open) \
        .props('outline size=sm icon=cloud_upload')
    ui.button(load_label, on_click=open_load_dialog) \
        .props(f'outline size=sm icon={load_icon}')


def body_profiles_ui(state):
    """Save/load body measurements; call inside a ui.row in the body tab.
    `state` is the GUIState; requires state.user to be set."""

    async def apply_item(data):
        # Same flow as the body-file upload dialog in gui/callbacks.py
        state.toggle_param_update_events(state.ui_active_body_refs)
        state.pattern_state.set_new_body_params(data['measurements'])
        state.update_body_params_ui_state(state.ui_active_body_refs)
        await state.update_pattern_ui_state()
        state.toggle_param_update_events(state.ui_active_body_refs)

    _library_ui(
        state.user['email'],
        noun='measurements',
        noun_plural='measurements',
        save_label='Save to account',
        load_label='My measurements',
        load_icon='straighten',
        snapshot=lambda: profiles.measurements_from_body(
            state.pattern_state.body_params),
        apply_item=apply_item,
        list_items=profiles.list_profiles,
        save_item=profiles.save_profile,
        get_item=profiles.get_profile,
        delete_item=profiles.delete_profile,
    )


def designs_ui(state):
    """Save/load garment designs; call inside a ui.row in the design tab.
    `state` is the GUIState; requires state.user to be set."""

    async def apply_item(data):
        # Same flow as the design-file upload dialog in gui/callbacks.py
        state.toggle_param_update_events(state.ui_design_refs)
        state.pattern_state.set_new_design(data['params'])
        state.update_design_params_ui_state(
            state.ui_design_refs, state.pattern_state.design_params)
        await state.update_pattern_ui_state()
        state.toggle_param_update_events(state.ui_design_refs)

    _library_ui(
        state.user['email'],
        noun='design',
        noun_plural='designs',
        save_label='Save design',
        load_label='My designs',
        load_icon='checkroom',
        snapshot=lambda: designs.snapshot_design_params(
            state.pattern_state.design_params),
        apply_item=apply_item,
        list_items=designs.list_designs,
        save_item=designs.save_design,
        get_item=designs.get_design,
        delete_item=designs.delete_design,
    )
