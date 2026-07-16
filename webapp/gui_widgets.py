"""NiceGUI widgets for account features, kept out of gui/callbacks.py to
minimize the diff against upstream GarmentCode."""

from nicegui import ui

from webapp import config, profiles


def auth_header_ui(user):
    """Header controls: sign-in button, or user identity + logout"""
    if user:
        if user.get('picture'):
            ui.image(user['picture']).classes('w-8 h-8 rounded-full')
        ui.label(user.get('name') or user['email']).classes('text-white')
        ui.button('Log out',
                  on_click=lambda: ui.navigate.to('/auth/logout')) \
            .props('flat color=white')
    elif config.google_configured():
        ui.button('Sign in with Google',
                  on_click=lambda: ui.navigate.to('/auth/login')) \
            .props('flat color=white')


def body_profiles_ui(state):
    """Save/load body measurements to the signed-in user's account.

    Adds two buttons (call inside a ui.row in the body tab) plus their
    dialogs. `state` is the GUIState; requires state.user to be set.
    """
    email = state.user['email']

    # --- Save dialog ---
    def save_current():
        name = (name_input.value or '').strip()
        if not name:
            ui.notify('Give the measurements a name', type='warning')
            return
        data = profiles.measurements_from_body(state.pattern_state.body_params)
        created = profiles.save_profile(email, name, data)
        ui.notify(f'{"Saved" if created else "Updated"} "{name}"',
                  type='positive')
        save_dialog.close()

    with ui.dialog() as save_dialog, ui.card().classes('items-center'):
        ui.label('Save current measurements to your account')
        name_input = ui.input(
            label='Name', placeholder='e.g. My measurements'
        ).classes('w-64')
        with ui.row():
            ui.button('Save', on_click=save_current)
            ui.button('Cancel', on_click=save_dialog.close).props('flat')

    # --- Load dialog ---
    async def apply_profile(profile_id: int):
        data = profiles.get_profile(email, profile_id)
        if data is None:
            ui.notify('Profile not found', type='negative')
            return
        # Same flow as the body-file upload dialog in gui/callbacks.py
        state.toggle_param_update_events(state.ui_active_body_refs)
        state.pattern_state.set_new_body_params(data['measurements'])
        state.update_body_params_ui_state(state.ui_active_body_refs)
        await state.update_pattern_ui_state()
        state.toggle_param_update_events(state.ui_active_body_refs)
        ui.notify(f'Applied "{data["name"]}"', type='positive')
        load_dialog.close()

    def remove_profile(profile_id: int):
        profiles.delete_profile(email, profile_id)
        refresh_profile_list()

    def refresh_profile_list():
        profile_list.clear()
        with profile_list:
            rows = profiles.list_profiles(email)
            if not rows:
                ui.label('No saved measurements yet').classes('text-gray-500')
            for row in rows:
                with ui.row().classes('items-center w-full justify-between'):
                    ui.label(row['name'])
                    with ui.row():
                        ui.button(
                            'Load',
                            on_click=lambda _, pid=row['id']: apply_profile(pid))
                        ui.button(
                            icon='delete',
                            on_click=lambda _, pid=row['id']: remove_profile(pid)
                        ).props('flat color=negative')

    with ui.dialog() as load_dialog, ui.card().classes('items-center w-96'):
        ui.label('My measurements')
        profile_list = ui.column().classes('w-full')
        ui.button('Close', on_click=load_dialog.close).props('flat')

    def open_load_dialog():
        refresh_profile_list()
        load_dialog.open()

    # --- The buttons themselves ---
    ui.button('Save to account', on_click=save_dialog.open)
    ui.button('My measurements', on_click=open_load_dialog)
