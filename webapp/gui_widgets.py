"""NiceGUI widgets for account features, kept out of gui/callbacks.py to
minimize the diff against upstream GarmentCode."""

import asyncio
import base64
import traceback
from copy import deepcopy

from nicegui import run, ui

from webapp import config, designs, profiles, sharing


async def confirm_delete(message: str) -> bool:
    """Two-step deletion: a confirmation dialog; True when confirmed"""
    with ui.dialog() as dialog, ui.card().classes('items-center'):
        ui.label(message).classes('max-w-xs')
        with ui.row():
            ui.button('Delete', on_click=lambda: dialog.submit(True)) \
                .props('unelevated color=negative icon=delete')
            ui.button('Cancel', on_click=lambda: dialog.submit(False)) \
                .props('flat')
    result = await dialog
    dialog.delete()
    return result is True


SHARE_RESULT_MESSAGES = {
    'exists': ('Already shared with them', 'info'),
    'self': ("That's your own email — it's already yours", 'warning'),
    'bad_email': ('Enter a valid email address', 'warning'),
    'not_found': ('Item not found', 'negative'),
}


async def open_share_dialog(owner_email: str, kind: str, item_id: int,
                            item_name: str):
    """Dialog to share a legacy saved design with other users by email and
    to see/revoke who it is already shared with. `kind` is 'design'; every
    other item uses webapp.access_ui."""
    if kind != 'design':
        raise ValueError('Only earlier saved designs use this dialog.')
    share_fn = sharing.share_design
    recipients_fn = sharing.design_recipients
    revoke_fn = sharing.revoke_design_share

    with ui.dialog() as dialog, ui.card().classes('items-center'):
        ui.label(f'Share "{item_name}"').classes('font-medium')
        ui.label('Enter the Google account email of another SewEasy user. '
                 'They can use it in the studio and save their own copy; '
                 'your original stays yours.') \
            .classes('text-sm text-stone-600 max-w-xs')

        async def do_share():
            result = await run.io_bound(
                share_fn, owner_email, item_id, email_input.value)
            if result == 'shared':
                ui.notify(f'Shared with {email_input.value.strip()}',
                          type='positive')
                email_input.value = ''
                await refresh()
            else:
                message, level = SHARE_RESULT_MESSAGES[result]
                ui.notify(message, type=level)

        with ui.row(wrap=False).classes('items-center gap-2'):
            email_input = ui.input(
                label='Email', placeholder='friend@example.com'
            ).classes('w-64').props('outlined dense type=email') \
                .on('keydown.enter', do_share)
            ui.button('Share', on_click=do_share) \
                .props('unelevated icon=person_add')

        recipient_list = ui.column().classes('w-full gap-1')
        ui.button('Close', on_click=dialog.close).props('flat')

    async def revoke(share_id, recipient):
        if not await confirm_delete(
                f'Stop sharing "{item_name}" with {recipient}?'):
            return
        await run.io_bound(revoke_fn, owner_email, share_id)
        await refresh()

    async def refresh():
        rows = await run.io_bound(recipients_fn, owner_email, item_id)
        recipient_list.clear()
        with recipient_list:
            if not rows:
                ui.label('Not shared with anyone yet') \
                    .classes('text-sm text-gray-500')
                return
            for row in rows:
                with ui.row(wrap=False).classes(
                        'items-center w-full justify-between gap-2'):
                    with ui.row(wrap=False).classes('items-center gap-2 min-w-0'):
                        ui.icon('person').classes('text-stone-400')
                        ui.label(row['email']).classes('text-sm truncate')
                    ui.button(
                        icon='close',
                        on_click=lambda _, sid=row['share_id'],
                            r=row['email']: revoke(sid, r)
                    ).props('flat dense round size=sm color=negative '
                            'aria-label="Stop sharing"') \
                        .tooltip('Stop sharing')

    dialog.open()
    await refresh()
    await dialog
    dialog.delete()


def preview_data_uri(svg_text):
    """Pattern-SVG preview -> data URI for ui.image (None-safe)"""
    if not svg_text:
        return None
    encoded = base64.b64encode(svg_text.encode('utf-8')).decode()
    return f'data:image/svg+xml;base64,{encoded}'


def piece_preview_svg(pattern_state, kind):
    """Draft only the given piece of the current design and return its
    pattern SVG text (None when the piece can't be drafted)."""
    try:
        from assets.garment_programs.meta_garment import MetaGarment
        params = deepcopy(pattern_state.design_params)
        keep = designs.GARMENT_SECTIONS[kind]['meta']
        for meta_key in params['meta']:
            if meta_key not in keep:
                params['meta'][meta_key]['v'] = None
        piece = MetaGarment('Preview', pattern_state.body_params, params)
        pattern = piece.assembly()
        dwg = pattern.get_svg(
            'preview.svg',  # not written: get_svg returns the drawing
            with_text=False, view_ids=False,
            panel_fill_color=pattern_state.fabric_color,
            margin=0)
        return dwg.tostring()
    except KeyboardInterrupt:
        raise
    except BaseException as e:
        import seweasy as pyg
        if not isinstance(e, pyg.EmptyPatternError):  # empty piece: expected
            traceback.print_exc()
        return None


def outfit_preview_svg(pattern_state):
    """The studio's current (already drafted) pattern SVG, or None"""
    try:
        if pattern_state.svg_filename:
            return pattern_state.svg_path().read_text(encoding='utf-8')
    except OSError:
        pass
    return None


def auth_header_ui(state, compact=False):
    """Header controls: sign-in button, or user identity (-> account page).
    `state` is the GUIState — both navigations stash the working design
    first, so signing in or visiting the account never discards it."""
    user = state.user

    def go(url):
        state.stash_pending_design()
        ui.navigate.to(url)

    if user:
        with ui.row(wrap=False).classes(
                'items-center gap-2 cursor-pointer rounded-md px-2 py-1 '
                'hover:bg-white/10') \
                .on('click', lambda: go('/account')):
            if user.get('picture'):
                ui.image(user['picture']) \
                    .props('alt="Your account picture"') \
                    .classes('w-8 h-8 rounded-full')
            else:
                ui.icon('account_circle').classes('text-3xl')
            ui.label(user.get('name') or user['email']).classes('text-white')
    elif config.google_configured():
        ui.button('Sign in' if compact else 'Sign in with Google',
                  on_click=lambda: go('/auth/login')) \
            .props('outline color=white no-caps icon=login').tooltip('Sign in with Google')


def body_source_ui(state):
    """Measurement source selector for the side panel: default body,
    saved profiles (signed in), or file upload. Editing happens on the
    account page. `state` is the GUIState."""
    email = state.user['email'] if state.user else None
    DEFAULT = '__default__'
    CUSTOM = '__custom__'
    SHARED_PREFIX = 'shared:'  # shared-profile option keys: 'shared:<id>'
    # Three default mannequins. Each is drawn as its own mesh, unchanged.
    PRESETS = {DEFAULT: ('all', 'Default body'), '__woman__': ('female', 'Default woman'),
               '__man__': ('male', 'Default man')}

    def current_preset():
        """Which default mannequin the current measurements are, if any."""
        body = profiles.measurements_from_body(state.pattern_state.body_params)
        for key, (name, _) in PRESETS.items():
            preset = profiles.default_measurements(name)
            if all(isinstance(body.get(k), float) and abs(body[k] - v) < 1e-6 for k, v in preset.items()):
                return key
        return None

    async def apply_measurements(measurements):
        state.pattern_state.set_new_body_params(measurements)
        await state.update_pattern_ui_state()

    async def on_select(e):
        if e.value in PRESETS or (email and (isinstance(e.value, int) or str(e.value).startswith(SHARED_PREFIX))):
            state.body_choice = e.value     # remembered with the draft; profiles are reread
        refresh_default_button()
        if e.value in PRESETS:
            await apply_measurements(profiles.default_measurements(PRESETS[e.value][0]))
            await state.apply_skin_color(None)
            if select.value == e.value:
                select.set_options(options())
        elif email and (isinstance(e.value, int)
                        or str(e.value).startswith(SHARED_PREFIX)):
            # Yours or shared with you: either way the profile's own access decides.
            profile_id = e.value if isinstance(e.value, int) else int(e.value[len(SHARED_PREFIX):])
            data = await run.io_bound(profiles.get_profile, email, profile_id)
            if data is None:
                ui.notify('Saved measurements not found', type='negative')
                return
            await apply_measurements(data['measurements'])
            await state.apply_skin_color(data.get('skin_color'))
            if select.value == e.value:
                select.set_options(options())

    def default_id():
        default = profiles.get_default_profile(email) if email else None
        return default and default['id']

    def options():
        opts = {key: label for key, (_, label) in PRESETS.items()}
        if email:
            chosen = default_id()
            for row in profiles.list_profiles(email):
                opts[row['id']] = row['name'] + (' · default' if row['id'] == chosen else '')
            for row in profiles.shared_profiles(email):
                opts[f'{SHARED_PREFIX}{row["id"]}'] = \
                    f'{row["name"]} — shared by {row["owner_name"]}' + (' · default' if row['id'] == chosen else '')
        return opts

    def mark_custom():
        state.body_choice = CUSTOM
        select.set_options({**options(), CUSTOM: 'Custom measurements'})
        select.set_value(CUSTOM)
        refresh_default_button()

    def selected_profile():
        value = select.value
        if isinstance(value, int):
            return value
        if str(value).startswith(SHARED_PREFIX):
            return int(value[len(SHARED_PREFIX):])
        return None

    def toggle_default():
        profile_id = selected_profile()
        if profile_id is None:
            return
        try:
            profiles.set_default_profile(email, None if profile_id == default_id() else profile_id)
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return
        is_default = profile_id == default_id()
        select.set_options({**options(), **({CUSTOM: 'Custom measurements'} if select.value == CUSTOM else {})})
        refresh_default_button()
        ui.notify('New designs open with these measurements' if is_default else 'No default measurements',
                  type='positive' if is_default else 'info')

    def refresh_default_button():
        if not email or default_button is None:
            return
        profile_id = selected_profile()
        is_default = profile_id is not None and profile_id == default_id()
        default_button.set_visibility(profile_id is not None)
        default_button.props(f'icon={"star" if is_default else "star_outline"}')
        label = 'Stop opening new designs with these measurements' if is_default else 'Open new designs with these measurements'
        default_button._props['aria-label'] = label
        default_tooltip.set_text(label)
        default_button.update()

    state.mark_custom_measurements = mark_custom

    default_button = default_tooltip = None
    initial_options = options()
    # This draft's choice (a profile stays selected by name, not by numbers).
    initial = state.body_choice if state.body_choice in initial_options else current_preset()
    with ui.row(wrap=False).classes('w-full items-center gap-1'):
        select = ui.select(initial_options, value=initial or DEFAULT, label='Measurements',
                           on_change=on_select) \
            .classes('grow').props('outlined dense options-dense')
        if email:
            default_button = ui.button(on_click=toggle_default).props('flat dense')
            with default_button:
                default_tooltip = ui.tooltip('')
        ui.button(icon='upload_file', on_click=state.ui_body_dialog.open) \
            .props('flat dense aria-label="Upload a measurements file"') \
            .tooltip('Upload a measurements file')

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
                saved = next((r['id'] for r in profiles.list_profiles(email) if r['name'] == name), None)
                select.set_options(options())
                if saved is not None:
                    state.body_choice = saved
                    select.set_value(saved)     # the same numbers, now under their name
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
                .props('flat dense aria-label="Save current measurements to your account"') \
                .tooltip('Save current measurements to your account')

    if email:
        def go_account():
            state.stash_pending_design()   # keep the working design safe
            ui.navigate.to('/account')

        ui.button('Manage measurements', on_click=go_account) \
            .props('flat dense no-caps size=sm icon=straighten')
    else:
        ui.label('Sign in to save measurement profiles').classes('se-param-label')

    # Editing the current body should not require an account or a file upload.
    def edit_current():
        from webapp import measurement_guide as guide
        baseline = profiles.measurements_from_body(state.pattern_state.body_params)
        shown = guide.editor_values(baseline)
        fields = {}
        with ui.dialog() as dialog, ui.card().classes('w-[520px] max-w-full'):
            ui.label('Customize measurements').classes('text-lg font-semibold')
            ui.label('Centimeters. Related proportions adjust with your edits.').classes('se-param-label')
            with ui.element('div').classes('grid grid-cols-2 gap-3 w-full'):
                from webapp.measurement_help import help_button
                for key in guide.editor_keys(baseline, essential_only=True):
                    with ui.row(wrap=False).classes('items-center gap-0 w-full'):
                        fields[key] = ui.number(guide.label_for(key), value=round(shown[key], 2), min=1,
                            step=.5, format='%.2f').props('outlined dense').classes('grow')
                        help_button(key)

            async def apply():
                try:
                    values = {**baseline, **{k: float(f.value) for k, f in fields.items()}}
                    inseam = values.pop('inseam', None)
                    values.update(guide.scale_coupled(baseline, values))
                    if inseam is not None:
                        values = guide.apply_inseam(values, inseam)
                    errors, warnings = guide.validate_measurements(values)
                    if errors:
                        raise ValueError('\n'.join(errors))
                    # Validate the fitted shape before changing the current design.
                    from seweasy.meshgen.body_fit import fit_body
                    await run.io_bound(fit_body, values)
                except (TypeError, ValueError) as error:
                    ui.notify(str(error), type='negative', multi_line=True)
                    return
                dialog.close()
                mark_custom()
                await apply_measurements(values)
                if warnings:
                    ui.notify('\n'.join(warnings), type='warning', multi_line=True)
            with ui.row():
                ui.button('Apply measurements', on_click=apply)
                ui.button('Cancel', on_click=dialog.close).props('flat')
        dialog.on('hide', dialog.delete)
        dialog.open()

    ui.button('Customize measurements', on_click=edit_current) \
        .props('flat dense no-caps size=sm icon=straighten')
    if initial is None:
        mark_custom()
    refresh_default_button()


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
    async def save_current():
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
            # Draft the piece alone for its thumbnail (may take a moment)
            state.spin_dialog.open()
            loop = asyncio.get_event_loop()
            preview = await loop.run_in_executor(
                state._async_executor, piece_preview_svg,
                state.pattern_state, kind)
            state.spin_dialog.close()
        else:
            params = designs.snapshot_design_params(design_params)
            preview = outfit_preview_svg(state.pattern_state)
        # Outfits carry their look along: fabric color, and the draped 3D
        # result when one is in sync -- loading skips the simulation
        drape_glb = fabric_color = None
        if kind == 'outfit':
            fabric_color = state.pattern_state.fabric_color
            drape_glb = state.pattern_state.current_drape_bytes()
        # Off the event loop: the drape blob can be tens of MB
        created = await run.io_bound(
            designs.save_design, email, name, params, kind=kind,
            preview=preview, drape_glb=drape_glb, fabric_color=fabric_color)
        message = f'{"Saved" if created else "Updated"} "{name}"'
        if drape_glb:
            message += ' (with its 3D drape)'
        ui.notify(message, type='positive')
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
    async def load_and_apply(item_id: int, shared: bool = False):
        # Off the event loop: fetches the drape blob (can be tens of MB)
        fetch = sharing.get_shared_design if shared else designs.get_design
        data = await run.io_bound(fetch, email, item_id)
        if data is None:
            ui.notify('Saved design not found', type='negative')
            return
        if data['kind'] == 'outfit':
            # Restore the saved look before drafting: the 2D pattern
            # serializes in the outfit's fabric color right away
            state.apply_fabric_color_visuals(data.get('fabric_color'))
        await apply_params(data['params'])
        if data['kind'] == 'outfit':
            if data.get('drape_glb'):
                state.adopt_drape(data['drape_glb'])
                ui.notify(f'Applied outfit "{data["name"]}" — 3D drape '
                          'restored from your library', type='positive')
                load_dialog.close()
                return
            ui.notify(f'Applied outfit "{data["name"]}"', type='positive')
        else:
            ui.notify(
                f'Merged {designs.KIND_LABELS[data["kind"]].lower()} '
                f'"{data["name"]}" into the current outfit',
                type='positive')
        load_dialog.close()

    async def remove_item(item_id: int, name: str):
        if not await confirm_delete(f'Delete "{name}" from your library?'):
            return
        await run.io_bound(designs.delete_design, email, item_id)
        await refresh_list()

    def render_item(row, shared: bool):
        item_id = row['design_id'] if shared else row['id']
        with ui.row().classes('items-center w-full justify-between'):
            with ui.row(wrap=False).classes('items-center gap-2 min-w-0'):
                thumb = preview_data_uri(row.get('preview'))
                if thumb:
                    ui.image(thumb).props('fit=contain').classes(
                        'w-12 h-12 bg-white rounded '
                        'border border-stone-200')
                else:
                    ui.icon('checkroom').classes(
                        'text-3xl text-stone-300 w-12 text-center')
                ui.badge(designs.KIND_LABELS.get(row['kind'], '?')) \
                    .props('outline color=grey-7')
                with ui.column().classes('gap-0 min-w-0'):
                    ui.label(row['name']).classes('truncate')
                    if shared:
                        ui.label(f'shared by {row["owner_name"]}') \
                            .classes('se-param-label truncate')
            with ui.row():
                ui.button(
                    'Load',
                    on_click=lambda _, iid=item_id, s=shared:
                        load_and_apply(iid, shared=s))
                if not shared:
                    ui.button(
                        icon='delete',
                        on_click=lambda _, iid=item_id, n=row['name']:
                            remove_item(iid, n)
                    ).props('flat color=negative aria-label="Delete"')

    async def refresh_list():
        rows = await run.io_bound(designs.list_designs, email)
        shared_rows = await run.io_bound(sharing.shared_designs_with_me, email)
        item_list.clear()
        with item_list:
            if not rows and not shared_rows:
                ui.label('Nothing saved yet').classes('text-gray-500')
            for row in rows:
                render_item(row, shared=False)
            if shared_rows:
                ui.label('Shared with me') \
                    .classes('se-param-label mt-2')
                for row in shared_rows:
                    render_item(row, shared=True)

    with ui.dialog() as load_dialog, ui.card().classes('items-center w-96'):
        ui.label('My outfits & garments')
        item_list = ui.column().classes('w-full')
        ui.button('Close', on_click=load_dialog.close).props('flat')

    async def open_load_dialog():
        load_dialog.open()
        await refresh_list()

    ui.button('Save', on_click=save_dialog.open) \
        .props('outline size=sm icon=cloud_upload') \
        .tooltip('Save the outfit or one garment to your account')
    ui.button('Library', on_click=open_load_dialog) \
        .props('outline size=sm icon=checkroom') \
        .tooltip('Load saved outfits and garments')
