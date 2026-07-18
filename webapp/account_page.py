"""Account area: sidebar-navigated pages for identity, measurements,
garments, and settings.

Registered by webapp.setup(); requires a signed-in user (redirects home
otherwise). Uses the same visual theme as the studio (gui/theme.py).
Sections are rebuilt on every sidebar switch so they always reflect the
current database state (e.g. a units change in Settings shows up in the
Measurements editor immediately).
"""

import numpy as np
from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import run, ui

from assets.bodies.body_params import BodyParameters
from gui import theme
from webapp import auth, designs, profiles, sharing
from webapp import measurement_guide as guide
# body_display registers the /body and /body_tones static mounts and owns
# the tone-tinted mannequin cache (shared with the studio 3D view)
from webapp.body_display import tinted_body_glb_url
from webapp.gui_widgets import (confirm_delete, open_share_dialog,
                                preview_data_uri)

BODY_DEFAULT_FILE = './assets/bodies/mean_all.yaml'


def _mannequin_scene():
    """A small 3D stage matching the studio's lighting (the skin-tone
    calibration in display_to_base_rgba assumes these lights)"""
    camera = ui.scene.perspective_camera(fov=30)
    camera.x, camera.y, camera.z = 0, -4.15, 1.25
    camera.look_at_x = camera.look_at_y = 0
    camera.look_at_z = 1.25 * 2 / 3
    with ui.scene(
        width=260, height=400, camera=camera, grid=False,
        background_color='#f7f5f0',
    ).classes('rounded') as scene:
        light_positions = np.array([
            [1.60614, 1.23701, 1.5341],
            [1.31844, -2.52238, 1.92831],
            [-2.80522, 2.34624, 1.2594],
            [0.160261, 3.52215, 1.81789],
            [-2.65752, -1.26328, 1.41194],
        ])
        z_dirs = np.arctan2(light_positions[:, 1], light_positions[:, 0])
        for pos, z_dir in zip(light_positions, z_dirs):
            scene.spot_light(color='#ffffff', intensity=10., angle=np.pi) \
                .rotate(0., 0., -z_dir).move(*pos)
    return scene

SECTIONS = {
    'account': ('person', 'Account'),
    'measurements': ('straighten', 'Measurements'),
    'garments': ('checkroom', 'Garments'),
    'shared': ('folder_shared', 'Shared with me'),
    'settings': ('settings', 'Settings'),
}


def _default_measurements() -> dict:
    return profiles.measurements_from_body(BodyParameters(BODY_DEFAULT_FILE))


@ui.page('/account')
async def account_page(request: Request):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse('/')
    email = user['email']

    ui.add_head_html(theme.HEAD_HTML)
    ui.colors(
        primary=theme.colors.primary,
        secondary=theme.colors.secondary,
        accent=theme.colors.accent,
        dark=theme.colors.dark,
        positive=theme.colors.positive,
        negative=theme.colors.negative,
        info=theme.colors.info,
        warning=theme.colors.warning,
    )

    # --- Header ---
    with ui.header(elevated=False, fixed=False).classes('flex-col p-0 m-0 gap-0'):
        with ui.row(wrap=False).classes('w-full items-center justify-between py-2 px-5 m-0'):
            with ui.row(wrap=False).classes('items-center gap-2.5 cursor-pointer') \
                    .on('click', lambda: ui.navigate.to('/')):
                ui.icon('content_cut').classes('text-2xl rotate-[-90deg] opacity-90')
                with ui.column().classes('gap-0.5'):
                    ui.label('SewEasy').classes('se-wordmark')
                    ui.label('account').classes('se-eyebrow')
            ui.button('Back to studio', on_click=lambda: ui.navigate.to('/')) \
                .props('flat color=white no-caps icon=arrow_back')
        ui.element('div').classes('se-selvedge w-full')

    # --- Sidebar navigation ---
    nav_buttons = {}
    with ui.left_drawer(value=True, bordered=True) \
            .classes('bg-[#fcfcfa] px-2 py-3').props('width=220 breakpoint=640'):
        for key, (icon, label) in SECTIONS.items():
            nav_buttons[key] = ui.button(
                label, icon=icon,
                on_click=lambda _, k=key: show(k)
            ).props('flat no-caps align=left color=grey-9') \
                .classes('w-full justify-start rounded-lg')

    content = ui.column().classes('w-full max-w-3xl mx-auto gap-4 p-4')

    # Unsaved measurement edits: set by the editor, checked before anything
    # rebuilds a section (rebuilding re-reads the DB and discards edits)
    unsaved = {'dirty': False}

    async def confirm_discard() -> bool:
        with ui.dialog() as dialog, ui.card().classes('items-center'):
            ui.label('You have unsaved measurement edits — discard them?') \
                .classes('max-w-xs')
            with ui.row():
                ui.button('Discard', on_click=lambda: dialog.submit(True)) \
                    .props('unelevated color=negative')
                ui.button('Keep editing', on_click=lambda: dialog.submit(False)) \
                    .props('flat')
        result = await dialog
        dialog.delete()
        return result is True

    async def show(section):
        if unsaved['dirty'] and not await confirm_discard():
            return
        unsaved['dirty'] = False
        for key, btn in nav_buttons.items():
            btn.classes(replace='w-full justify-start rounded-lg'
                        + (' bg-[#e5ebf4] text-[#35558a] font-medium'
                           if key == section else ''))
        content.clear()
        with content:
            await builders[section]()

    # ------------------------------------------------------------------
    # SECTION Account

    async def build_account():
        # Counts only — no reason to pull every design's preview SVG out
        # of the database for three numbers
        n_profiles = len(await run.io_bound(profiles.list_profiles, email))
        kind_counts = await run.io_bound(designs.count_designs, email)
        n_outfits = kind_counts.get('outfit', 0)
        n_garments = sum(kind_counts.values()) - n_outfits

        with ui.card().classes('se-stitch-card w-full'):
            with ui.row(wrap=False).classes('items-center gap-4 w-full'):
                if user.get('picture'):
                    ui.image(user['picture']) \
                        .props('alt="Your account picture"') \
                        .classes('w-14 h-14 rounded-full')
                else:
                    ui.icon('account_circle').classes('text-6xl text-gray-400')
                with ui.column().classes('gap-0.5'):
                    ui.label(user.get('name') or email).classes('se-section-label text-lg')
                    ui.label(email).classes('se-param-label')
                ui.space()
                ui.button('Log out', on_click=lambda: ui.navigate.to('/auth/logout')) \
                    .props('outline size=sm icon=logout')
        with ui.card().classes('se-stitch-card w-full'):
            ui.label('At a glance').classes('se-section-label')
            ui.label(f'{n_profiles} measurement profile(s) · '
                     f'{n_outfits} outfit(s) · {n_garments} garment(s)') \
                .classes('text-sm text-stone-600')

    # ------------------------------------------------------------------
    # SECTION Measurements

    async def build_measurements():
        with ui.card().classes('se-stitch-card w-full'):
            NEW_PROFILE = '__new__'

            with ui.row(wrap=False).classes('items-center w-full justify-between'):
                ui.label('Body measurements').classes('se-section-label text-lg')
                with ui.row(wrap=False).classes('gap-2'):
                    share_btn = ui.button('Share',
                                          on_click=lambda: share_current()) \
                        .props('outline size=sm icon=share') \
                        .tooltip('Share this profile with another user')
                    delete_btn = ui.button('Delete',
                                           on_click=lambda: delete_current()) \
                        .props('outline size=sm icon=delete color=negative')

            last_selected = {'id': None}

            async def on_profile_change(e=None):
                # Programmatic reverts re-fire this handler with the old
                # value — a no-op change is always ignored
                if profile_select.value == last_selected['id']:
                    return
                if profile_select.value == NEW_PROFILE:
                    # Creating happens in the dialog; restore the selection
                    profile_select.value = last_selected['id']
                    new_dialog.open()
                    return
                if unsaved['dirty'] and not await confirm_discard():
                    profile_select.value = last_selected['id']
                    return
                unsaved['dirty'] = False
                last_selected['id'] = profile_select.value
                load_editor()

            profile_select = ui.select(
                {}, label='Profile',
                on_change=on_profile_change,
            ).classes('w-64').props('outlined dense')

            hint = ui.label('No saved measurements yet — choose '
                            '"＋ New profile…" above to start') \
                .classes('text-gray-500')

            # --- How-to-measure guide ---
            with ui.expansion('How to measure').classes('w-full se-stitch-card'):
                ui.label(guide.GENERAL_TIPS).classes('text-sm text-stone-600')
                unit_note = ui.label('').classes('text-sm text-stone-600')
                ui.image(guide.OVERVIEW_DIAGRAM).classes('w-full max-w-md mx-auto mt-2')
                ui.label(guide.OVERVIEW_CREDIT).classes('se-param-label text-[0.65rem]')
                ui.label('Every field below has a ? button with a diagram '
                         'showing exactly where that measurement is taken.') \
                    .classes('text-sm text-stone-600 mt-1')

            # Shared per-measurement help dialog
            with ui.dialog() as guide_dialog, \
                    ui.card().classes('items-center max-w-sm'):
                guide_title = ui.label('').classes('se-section-label')
                guide_image = ui.image('').classes('w-56')
                guide_text = ui.label('').classes('text-sm text-stone-600')
                ui.button('Close', on_click=guide_dialog.close).props('flat')

            def show_guide(key):
                guide_title.set_text(guide.label_for(key))
                guide_image.set_source(f'{guide.DIAGRAM_URL}/{key}.svg')
                entry = guide.GUIDE.get(key)
                guide_text.set_text(entry['how'] if entry
                                    else 'No guide available yet.')
                guide_dialog.open()

            def change_units():
                # Converts the visible fields in place: switching units
                # mid-edit must never discard what was typed
                old, new = last_units['v'], units.value
                if old == new:
                    return
                last_units['v'] = new
                profiles.set_units(email, new)
                update_unit_note()
                was_dirty = unsaved['dirty']
                for key, field in fields.items():
                    try:
                        cm = guide.stored_value(key, field.value, old)
                        field.value = guide.display_value(key, cm, new)
                    except (TypeError, ValueError):
                        continue
                    field.props(f'label="{guide.label_for(key)}'
                                f'{guide.unit_suffix(key, new)}" '
                                f'step={0.25 if new == "in" else 0.5}')
                # Programmatic conversion is not a user edit
                unsaved['dirty'] = was_dirty

            def update_unit_note():
                unit_note.set_text(
                    'Lengths are shown in {} — switch above the fields.'
                    .format('inches' if units.value == 'in'
                            else 'centimeters'))

            last_mode = {'v': 'essential'}

            async def on_mode_change(e=None):
                if mode.value == last_mode['v']:
                    return
                if unsaved['dirty'] and not await confirm_discard():
                    mode.value = last_mode['v']
                    return
                last_mode['v'] = mode.value
                unsaved['dirty'] = False
                load_editor()

            with ui.row(wrap=False).classes('items-center gap-3 mt-1'):
                mode = ui.toggle(
                    {'essential': 'Essential', 'all': 'All measurements'},
                    value='essential',
                    on_change=on_mode_change,
                ).props('no-caps unelevated rounded toggle-color=primary '
                        'padding="1px 12px"')
                last_units = {'v': profiles.get_units(email)}
                units = ui.toggle(
                    {'in': 'inches', 'cm': 'cm'},
                    value=last_units['v'],
                    on_change=change_units,
                ).props('no-caps unelevated rounded toggle-color=primary '
                        'padding="1px 12px"').tooltip(
                    'Display units — values are stored in centimeters')
            update_unit_note()

            # Mannequin beside the editor: skin tone follows this profile
            # (the shape is the average body — measurements don't reshape it)
            with ui.row(wrap=False).classes('w-full gap-4 items-start'):
                with ui.column().classes('shrink-0 gap-1'):
                    scene = _mannequin_scene()
                    ui.label('Average body shape; skin tone follows '
                             'this profile').classes('se-param-label w-64')
                editor = ui.column().classes('grow min-w-0')

            fields = {}
            skin_ctl = {'slider': None, 'touched': False, 'stored': None}
            scene_ctl = {'body': None, 'url': None}

            def set_mannequin_url(url):
                if url == scene_ctl['url']:
                    return
                if scene_ctl['body'] is not None:
                    scene_ctl['body'].delete()
                with scene:
                    scene_ctl['body'] = scene.gltf(url).rotate(np.pi / 2, 0., 0.)
                scene_ctl['url'] = url

            def set_mannequin_tone(color):
                # Sync path (initial load): stored tones are almost always
                # already in the tint cache, so this is just a URL lookup
                set_mannequin_url(tinted_body_glb_url(color) if color
                                  else '/body/mean_all_display.glb')

            async def save_changes():
                data = await run.io_bound(
                    profiles.get_profile, email, profile_select.value)
                if data is None:
                    ui.notify('Profile not found', type='negative')
                    return
                # Merge: fields not shown (Essential mode) keep their values
                values = dict(data['measurements'])
                for key, field in fields.items():
                    try:
                        values[key] = guide.stored_value(
                            key, field.value, units.value,
                            previous_cm=data['measurements'].get(key))
                    except (TypeError, ValueError):
                        pass

                # In Essential mode the hidden measurements scale with the
                # essentials they depend on, staying anatomically consistent
                scaled = {}
                if mode.value == 'essential':
                    scaled = guide.scale_coupled(data['measurements'], values)
                    values.update(scaled)

                errors, warnings = guide.validate_measurements(values)
                if errors:
                    ui.notify('Not saved — impossible measurements:\n• '
                              + '\n• '.join(errors),
                              type='negative', multi_line=True,
                              close_button=True)
                    return

                # Skin tone: the slider hex when the user has set one,
                # otherwise whatever the profile already had
                if skin_ctl['touched'] and skin_ctl['slider'] is not None:
                    skin_color = guide.skin_tone_hex(skin_ctl['slider'].value)
                else:
                    skin_color = data.get('skin_color')
                await run.io_bound(profiles.save_profile,
                                   email, data['name'], values,
                                   skin_color=skin_color)
                unsaved['dirty'] = False
                message = f'Updated "{data["name"]}"'
                if scaled:
                    message += (f' — adjusted {len(scaled)} related '
                                'measurements to match')
                ui.notify(message, type='positive')
                if warnings:
                    ui.notify('Check these values:\n• ' + '\n• '.join(warnings),
                              type='warning', multi_line=True,
                              close_button=True)
                if scaled:
                    load_editor()  # Re-read so a mode switch shows new values

            def load_editor():
                editor.clear()
                fields.clear()
                unsaved['dirty'] = False
                if profile_select.value is None:
                    return
                data = profiles.get_profile(email, profile_select.value)
                if data is None:
                    return
                keys = sorted(data['measurements'])
                if mode.value == 'essential':
                    keys = [k for k in keys if guide.is_essential(k)]
                with editor:
                    # Skin tone: shown on the 3D mannequin when this
                    # profile is selected in the studio
                    stored_tone = data.get('skin_color')
                    skin_ctl.update(touched=False, stored=stored_tone)
                    set_mannequin_tone(stored_tone)
                    with ui.row(wrap=False).classes('items-center gap-3 mt-2 w-full'):
                        ui.label('Skin tone').classes('se-param-label w-24')

                        async def _touch_tone(e):
                            skin_ctl['touched'] = True
                            unsaved['dirty'] = True
                            tone = guide.skin_tone_hex(e.args)
                            skin_ctl['slider'].style(f'color: {tone}')
                            # A first-time tone tints the mesh: off-loop
                            url = await run.io_bound(tinted_body_glb_url, tone)
                            set_mannequin_url(url)

                        skin_ctl['slider'] = ui.slider(
                            value=guide.skin_tone_t(stored_tone)
                                if stored_tone else 0.3,
                            min=0., max=1., step=0.01,
                        ).props('dense aria-label="Skin tone"') \
                            .classes('se-skin-slider w-64') \
                            .style('color: {}'.format(
                                stored_tone or '#b9b2a6')) \
                            .on('update:model-value',   # live thumb color only
                                lambda e: skin_ctl['slider'].style(
                                    f'color: {guide.skin_tone_hex(e.args)}'),
                                throttle=0.1) \
                            .on('change', _touch_tone)  # mesh tint on release
                        if not stored_tone:
                            ui.label('not set — mannequin uses muslin') \
                                .classes('se-param-label')

                    with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-1 mt-2'):
                        for key in keys:
                            with ui.row(wrap=False).classes('items-center gap-0 w-full'):
                                fields[key] = ui.number(
                                    label=guide.label_for(key)
                                        + guide.unit_suffix(key, units.value),
                                    value=guide.display_value(
                                        key, data['measurements'][key],
                                        units.value),
                                    format='%.2f',
                                    step=0.25 if units.value == 'in' else 0.5,
                                    # Angles can be negative; lengths can't
                                    min=None if key in guide.ANGLE_KEYS else 0,
                                    on_change=lambda: unsaved.update(dirty=True),
                                ).classes('se-mono grow').props('outlined dense')
                                ui.button(
                                    icon='help_outline',
                                    on_click=lambda _, k=key: show_guide(k)
                                ).props('flat dense round size=sm color=grey-7 '
                                        'aria-label="How to take this measurement"') \
                                    .tooltip('How to take this measurement')
                    if mode.value == 'essential':
                        ui.label('Showing the essential measurements — the '
                                 'rest keep their current values. Switch to '
                                 '"All measurements" for fine-tuning.') \
                            .classes('se-param-label mt-1')
                    ui.button('Save changes', on_click=save_changes) \
                        .props('unelevated icon=save').classes('mt-3 self-end')

            def refresh_profiles(select_id=None):
                rows = profiles.list_profiles(email)
                options = {r['id']: r['name'] for r in rows}
                has_rows = bool(options)
                options[NEW_PROFILE] = '＋ New profile…'
                profile_select.set_options(options)
                hint.set_visibility(not has_rows)
                share_btn.set_visibility(has_rows)
                delete_btn.set_visibility(has_rows)
                if has_rows:
                    chosen = select_id if select_id in options \
                        else next(iter(options))
                    last_selected['id'] = chosen
                    profile_select.value = chosen
                    # The change handler ignores programmatic no-op updates,
                    # so (re)build the editor explicitly
                    load_editor()
                else:
                    last_selected['id'] = None
                    profile_select.value = None
                    editor.clear()
                    fields.clear()

            async def share_current():
                if profile_select.value in (None, NEW_PROFILE):
                    return
                data = await run.io_bound(
                    profiles.get_profile, email, profile_select.value)
                if data is None:
                    return
                await open_share_dialog(email, 'profile',
                                        data['id'], data['name'])

            async def delete_current():
                if profile_select.value in (None, NEW_PROFILE):
                    return
                data = profiles.get_profile(email, profile_select.value)
                name = data['name'] if data else 'this profile'
                if not await confirm_delete(
                        f'Delete the measurement profile "{name}"? '
                        'Its measurements and skin tone will be lost.'):
                    return
                profiles.delete_profile(email, profile_select.value)
                ui.notify('Profile deleted')
                refresh_profiles()

            # --- New-profile dialog ---
            def create_profile():
                name = (new_name.value or '').strip()
                if not name:
                    ui.notify('Give the profile a name', type='warning')
                    return
                profiles.save_profile(email, name, _default_measurements())
                new_dialog.close()
                new_name.value = ''
                rows = profiles.list_profiles(email)
                created = next((r for r in rows if r['name'] == name), None)
                refresh_profiles(created['id'] if created else None)
                ui.notify(f'Created "{name}" from the default body', type='positive')

            with ui.dialog() as new_dialog, ui.card().classes('items-center'):
                ui.label('New measurement profile')
                ui.label('Starts from the default body — adjust and save') \
                    .classes('se-param-label')
                new_name = ui.input(label='Name', placeholder='e.g. My measurements') \
                    .classes('w-64').props('outlined dense')
                with ui.row():
                    ui.button('Create', on_click=create_profile)
                    ui.button('Cancel', on_click=new_dialog.close).props('flat')

            refresh_profiles()

    # ------------------------------------------------------------------
    # SECTION Garments

    async def build_garments():
        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Outfits & garments').classes('se-section-label text-lg')
            ui.label('Saved from the studio design panel ("Save"); load '
                     'them onto a design there ("Library"). Manage them here.') \
                .classes('text-sm text-stone-600')

            listing = ui.column().classes('w-full mt-2')

            rename_state = {'id': None}
            with ui.dialog() as rename_dialog, ui.card().classes('items-center'):
                ui.label('Rename')
                rename_input = ui.input(label='New name') \
                    .classes('w-64').props('outlined dense')

                async def do_rename():
                    ok = designs.rename_design(
                        email, rename_state['id'], rename_input.value)
                    if ok:
                        rename_dialog.close()
                        await refresh()
                    else:
                        ui.notify('Name is empty or already taken',
                                  type='warning')

                with ui.row():
                    ui.button('Rename', on_click=do_rename)
                    ui.button('Cancel', on_click=rename_dialog.close).props('flat')

            def open_rename(item_id, current_name):
                rename_state['id'] = item_id
                rename_input.value = current_name
                rename_dialog.open()

            async def remove(item_id, name):
                if not await confirm_delete(
                        f'Delete "{name}" from your library?'):
                    return
                await run.io_bound(designs.delete_design, email, item_id)
                await refresh()

            async def refresh():
                # Preview SVGs make this the heaviest account query
                rows = await run.io_bound(designs.list_designs, email)
                listing.clear()
                with listing:
                    if not rows:
                        ui.label('Nothing saved yet').classes('text-gray-500')
                        return
                    with ui.grid(columns=2).classes('w-full gap-3'):
                        for row in rows:
                            with ui.card().classes(
                                    'se-stitch-card w-full p-2 gap-1'):
                                # The preview is the card: full design,
                                # fully contained, no cropping
                                thumb = preview_data_uri(row.get('preview'))
                                if thumb:
                                    ui.image(thumb).props('fit=contain') \
                                        .classes('w-full h-56 bg-white rounded')
                                else:
                                    with ui.element('div').classes(
                                            'w-full h-56 rounded bg-stone-50 '
                                            'flex items-center justify-center'):
                                        ui.icon('checkroom').classes(
                                            'text-6xl text-stone-300')
                                with ui.row(wrap=False).classes(
                                        'items-center w-full justify-between px-1'):
                                    with ui.row(wrap=False).classes(
                                            'items-center gap-2 min-w-0'):
                                        ui.badge(designs.KIND_LABELS.get(
                                            row['kind'], '?')) \
                                            .props('outline color=grey-7')
                                        ui.label(row['name']).classes('truncate')
                                    with ui.row(wrap=False).classes('gap-0'):
                                        ui.button(
                                            icon='share',
                                            on_click=lambda _, iid=row['id'],
                                                n=row['name']: open_share_dialog(
                                                    email, 'design', iid, n)
                                        ).props('flat dense round size=sm '
                                                'color=grey-7 aria-label="Share"') \
                                            .tooltip('Share with another user')
                                        ui.button(
                                            icon='edit',
                                            on_click=lambda _, iid=row['id'],
                                                n=row['name']: open_rename(iid, n)
                                        ).props('flat dense round size=sm '
                                                'color=grey-7 aria-label="Rename"') \
                                            .tooltip('Rename')
                                        ui.button(
                                            icon='delete',
                                            on_click=lambda _, iid=row['id'],
                                                n=row['name']: remove(iid, n)
                                        ).props('flat dense round size=sm '
                                                'color=negative aria-label="Delete"') \
                                            .tooltip('Delete')
                                ui.label(row['updated_at'].strftime('%b %d, %Y')) \
                                    .classes('se-param-label px-1')

            await refresh()

    # ------------------------------------------------------------------
    # SECTION Shared with me

    async def build_shared():
        prof_rows = await run.io_bound(sharing.shared_profiles_with_me, email)
        design_rows = await run.io_bound(sharing.shared_designs_with_me, email)

        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Shared with me').classes('se-section-label text-lg')
            ui.label('Measurement profiles and garments other users shared '
                     'with you. Use them directly in the studio (they follow '
                     'the owner\'s edits), or save your own editable copy.') \
                .classes('text-sm text-stone-600')

        async def copy_profile(profile_id):
            name = await run.io_bound(
                sharing.copy_shared_profile, email, profile_id)
            if name:
                ui.notify(f'Saved a copy as "{name}" in your measurements',
                          type='positive')
            else:
                ui.notify('This is no longer shared with you',
                          type='negative')

        async def copy_design(design_id):
            name = await run.io_bound(
                sharing.copy_shared_design, email, design_id)
            if name:
                ui.notify(f'Saved a copy as "{name}" in your garments',
                          type='positive')
            else:
                ui.notify('This is no longer shared with you',
                          type='negative')

        async def decline(kind, share_id, name, owner):
            if not await confirm_delete(
                    f'Remove "{name}" (shared by {owner}) from your list? '
                    'Their original is not affected.'):
                return
            fn = sharing.decline_profile_share if kind == 'profile' \
                else sharing.decline_design_share
            await run.io_bound(fn, email, share_id)
            await show('shared')

        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Measurement profiles').classes('se-section-label')
            if not prof_rows:
                ui.label('No one has shared measurements with you yet') \
                    .classes('text-gray-500')
            for row in prof_rows:
                with ui.row(wrap=False).classes(
                        'items-center w-full justify-between'):
                    with ui.row(wrap=False).classes('items-center gap-2 min-w-0'):
                        ui.icon('straighten').classes('text-stone-400')
                        with ui.column().classes('gap-0 min-w-0'):
                            ui.label(row['name']).classes('truncate')
                            ui.label(f'shared by {row["owner_name"]} · '
                                     f'updated {row["updated_at"]:%b %d, %Y}') \
                                .classes('se-param-label truncate')
                    with ui.row(wrap=False).classes('gap-1'):
                        ui.button(
                            'Save a copy',
                            on_click=lambda _, pid=row['profile_id']:
                                copy_profile(pid)
                        ).props('outline size=sm no-caps icon=content_copy')
                        ui.button(
                            icon='close',
                            on_click=lambda _, sid=row['share_id'],
                                n=row['name'], o=row['owner_name']:
                                decline('profile', sid, n, o)
                        ).props('flat dense round size=sm color=negative '
                                'aria-label="Remove from my list"') \
                            .tooltip('Remove from my list')

        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Outfits & garments').classes('se-section-label')
            if not design_rows:
                ui.label('No one has shared garments with you yet') \
                    .classes('text-gray-500')
            else:
                with ui.grid(columns=2).classes('w-full gap-3'):
                    for row in design_rows:
                        with ui.card().classes('se-stitch-card w-full p-2 gap-1'):
                            thumb = preview_data_uri(row.get('preview'))
                            if thumb:
                                ui.image(thumb).props('fit=contain') \
                                    .classes('w-full h-56 bg-white rounded')
                            else:
                                with ui.element('div').classes(
                                        'w-full h-56 rounded bg-stone-50 '
                                        'flex items-center justify-center'):
                                    ui.icon('checkroom').classes(
                                        'text-6xl text-stone-300')
                            with ui.row(wrap=False).classes(
                                    'items-center w-full justify-between px-1'):
                                with ui.row(wrap=False).classes(
                                        'items-center gap-2 min-w-0'):
                                    ui.badge(designs.KIND_LABELS.get(
                                        row['kind'], '?')) \
                                        .props('outline color=grey-7')
                                    ui.label(row['name']).classes('truncate')
                                with ui.row(wrap=False).classes('gap-0'):
                                    ui.button(
                                        icon='content_copy',
                                        on_click=lambda _, did=row['design_id']:
                                            copy_design(did)
                                    ).props('flat dense round size=sm '
                                            'color=grey-7 '
                                            'aria-label="Save a copy"') \
                                        .tooltip('Save a copy to your garments')
                                    ui.button(
                                        icon='close',
                                        on_click=lambda _, sid=row['share_id'],
                                            n=row['name'], o=row['owner_name']:
                                            decline('design', sid, n, o)
                                    ).props('flat dense round size=sm '
                                            'color=negative '
                                            'aria-label="Remove from my list"') \
                                        .tooltip('Remove from my list')
                            ui.label(f'shared by {row["owner_name"]} · '
                                     f'{row["updated_at"]:%b %d, %Y}') \
                                .classes('se-param-label px-1')

    # ------------------------------------------------------------------
    # SECTION Settings

    async def build_settings():
        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Preferences').classes('se-section-label text-lg')

            ui.label('Measurement units').classes('se-param-label mt-2')
            ui.toggle(
                {'in': 'inches', 'cm': 'centimeters'},
                value=profiles.get_units(email),
                on_change=lambda e: (
                    profiles.set_units(email, e.value),
                    ui.notify('Units updated', type='positive')),
            ).props('no-caps unelevated rounded toggle-color=primary '
                    'padding="1px 12px"')
            ui.label('Applies to how measurements are displayed and edited; '
                     'values are always stored in centimeters.') \
                .classes('text-sm text-stone-600')

    builders = {
        'account': build_account,
        'measurements': build_measurements,
        'garments': build_garments,
        'shared': build_shared,
        'settings': build_settings,
    }
    await show('account')
