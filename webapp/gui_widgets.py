"""NiceGUI widgets for account features, kept out of gui/callbacks.py to
minimize the diff against upstream GarmentCode."""

from nicegui import ui

from webapp import config, designs, profiles


def auth_header_ui(user):
    """Header controls: sign-in button, or user identity (-> account page)"""
    if user:
        with ui.row(wrap=False).classes(
                'items-center gap-2 cursor-pointer rounded-md px-2 py-1 '
                'hover:bg-white/10') \
                .on('click', lambda: ui.navigate.to('/account')):
            if user.get('picture'):
                ui.image(user['picture']).classes('w-8 h-8 rounded-full')
            else:
                ui.icon('account_circle').classes('text-3xl')
            ui.label(user.get('name') or user['email']).classes('text-white')
    elif config.google_configured():
        ui.button('Sign in with Google',
                  on_click=lambda: ui.navigate.to('/auth/login')) \
            .props('outline color=white no-caps icon=login')


def body_source_ui(state):
    """Measurement source selector for the side panel: default body,
    saved profiles (signed in), or file upload. Editing happens on the
    account page. `state` is the GUIState."""
    email = state.user['email'] if state.user else None
    DEFAULT = '__default__'

    async def apply_measurements(measurements):
        state.pattern_state.set_new_body_params(measurements)
        await state.update_pattern_ui_state()

    async def on_select(e):
        if e.value == DEFAULT:
            base = {k: v for k, v in
                    state.pattern_state.default_body_params.params.items()
                    if not k.startswith('_')}
            await apply_measurements(base)
            await state.apply_skin_color(None)
        elif isinstance(e.value, int) and email:
            data = profiles.get_profile(email, e.value)
            if data is None:
                ui.notify('Saved measurements not found', type='negative')
                return
            await apply_measurements(data['measurements'])
            await state.apply_skin_color(data.get('skin_color'))

    def options():
        opts = {DEFAULT: 'Default body'}
        if email:
            for row in profiles.list_profiles(email):
                opts[row['id']] = row['name']
        return opts

    with ui.row(wrap=False).classes('w-full items-center gap-1'):
        select = ui.select(options(), value=DEFAULT, label='Measurements',
                           on_change=on_select) \
            .classes('grow').props('outlined dense options-dense')
        ui.button(icon='upload_file', on_click=state.ui_body_dialog.open) \
            .props('flat dense').tooltip('Upload a measurements file')

        if email:
            def save_current():
                name = (save_name.value or '').strip()
                if not name:
                    ui.notify('Give the measurements a name', type='warning')
                    return
                profiles.save_profile(
                    email, name,
                    profiles.measurements_from_body(state.pattern_state.body_params),
                    skin_color=state.body_color)
                select.set_options(options())
                save_dialog.close()
                ui.notify(f'Saved "{name}"', type='positive')

            with ui.dialog() as save_dialog, ui.card().classes('items-center'):
                ui.label('Save current measurements to your account')
                save_name = ui.input(label='Name', placeholder='e.g. My measurements') \
                    .classes('w-64').props('outlined dense')
                with ui.row():
                    ui.button('Save', on_click=save_current)
                    ui.button('Cancel', on_click=save_dialog.close).props('flat')

            ui.button(icon='save', on_click=save_dialog.open) \
                .props('flat dense').tooltip('Save current measurements to your account')

    if email:
        ui.button('Manage measurements', on_click=lambda: ui.navigate.to('/account')) \
            .props('flat dense no-caps size=sm icon=straighten')
    else:
        ui.label('Sign in to save measurement profiles').classes('se-param-label')


def designs_ui(state):
    """Save/load whole outfits and individual garments; call inside a
    ui.row in the design tab. `state` is the GUIState; requires
    state.user to be set."""
    email = state.user['email']
    design_params = state.pattern_state.design_params

    async def apply_params(params):
        # Same flow as the design-file upload dialog in gui/callbacks.py.
        # set_new_design merges: a full outfit replaces every section, a
        # partial garment snapshot only touches its own sections
        state.toggle_param_update_events(state.ui_design_refs)
        state.pattern_state.set_new_design(params)
        state.update_design_params_ui_state(
            state.ui_design_refs, state.pattern_state.design_params)
        await state.update_pattern_ui_state()
        state.toggle_param_update_events(state.ui_design_refs)

    # --- Save dialog: whole outfit or one piece ---
    def save_current():
        name = (name_input.value or '').strip()
        kind = kind_select.value
        if not name:
            ui.notify('Give it a name', type='warning')
            return
        if kind != 'outfit':
            meta_key = designs.GARMENT_SECTIONS[kind]['meta'][0]
            if design_params['meta'][meta_key]['v'] is None:
                ui.notify(
                    f'The current design has no '
                    f'{designs.KIND_LABELS[kind].lower()} to save',
                    type='warning')
                return
            params = designs.snapshot_garment(design_params, kind)
        else:
            params = designs.snapshot_design_params(design_params)
        created = designs.save_design(email, name, params, kind=kind)
        ui.notify(f'{"Saved" if created else "Updated"} "{name}"',
                  type='positive')
        save_dialog.close()

    with ui.dialog() as save_dialog, ui.card().classes('items-center'):
        ui.label('Save to your account')
        kind_select = ui.select(
            {'outfit': 'Whole outfit', 'top': 'Top only',
             'bottom': 'Bottom only', 'waistband': 'Waistband only'},
            value='outfit', label='What to save'
        ).classes('w-64').props('outlined dense options-dense')
        name_input = ui.input(
            label='Name', placeholder='e.g. Summer dress'
        ).classes('w-64').props('outlined dense')
        with ui.row():
            ui.button('Save', on_click=save_current)
            ui.button('Cancel', on_click=save_dialog.close).props('flat')

    # --- Load dialog: outfits replace, garments merge ---
    async def load_and_apply(item_id: int):
        data = designs.get_design(email, item_id)
        if data is None:
            ui.notify('Saved design not found', type='negative')
            return
        await apply_params(data['params'])
        if data['kind'] == 'outfit':
            ui.notify(f'Applied outfit "{data["name"]}"', type='positive')
        else:
            ui.notify(
                f'Merged {designs.KIND_LABELS[data["kind"]].lower()} '
                f'"{data["name"]}" into the current outfit',
                type='positive')
        load_dialog.close()

    def remove_item(item_id: int):
        designs.delete_design(email, item_id)
        refresh_list()

    def refresh_list():
        item_list.clear()
        with item_list:
            rows = designs.list_designs(email)
            if not rows:
                ui.label('Nothing saved yet').classes('text-gray-500')
            for row in rows:
                with ui.row().classes('items-center w-full justify-between'):
                    with ui.row(wrap=False).classes('items-center gap-2'):
                        ui.badge(designs.KIND_LABELS.get(row['kind'], '?')) \
                            .props('outline color=grey-7')
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
        ui.label('My outfits & garments')
        item_list = ui.column().classes('w-full')
        ui.button('Close', on_click=load_dialog.close).props('flat')

    def open_load_dialog():
        refresh_list()
        load_dialog.open()

    ui.button('Save', on_click=save_dialog.open) \
        .props('outline size=sm icon=cloud_upload') \
        .tooltip('Save the outfit or one garment to your account')
    ui.button('Library', on_click=open_load_dialog) \
        .props('outline size=sm icon=checkroom') \
        .tooltip('Load saved outfits and garments')
