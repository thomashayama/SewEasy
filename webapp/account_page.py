"""Account area: sidebar-navigated pages for identity, measurements,
garments, and settings.

Registered by webapp.setup(); requires a signed-in user (redirects home
otherwise). Uses the same visual theme as the studio (gui/theme.py).
Sections are rebuilt on every sidebar switch so they always reflect the
current database state (e.g. a units change in Settings shows up in the
Measurements editor immediately).
"""

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app, ui

from assets.bodies.body_params import BodyParameters
from gui import theme
from webapp import auth, designs, profiles
from webapp import measurement_guide as guide
from webapp.gui_widgets import preview_data_uri

BODY_DEFAULT_FILE = './assets/bodies/mean_all.yaml'

# Measurement diagrams and overview illustration
app.add_static_files('/img', './assets/img')

SECTIONS = {
    'account': ('person', 'Account'),
    'measurements': ('straighten', 'Measurements'),
    'garments': ('checkroom', 'Garments'),
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
            .classes('bg-[#fcfcfa] px-2 py-3').props('width=220 breakpoint=0'):
        for key, (icon, label) in SECTIONS.items():
            nav_buttons[key] = ui.button(
                label, icon=icon,
                on_click=lambda _, k=key: show(k)
            ).props('flat no-caps align=left color=grey-9') \
                .classes('w-full justify-start rounded-lg')

    content = ui.column().classes('w-full max-w-3xl mx-auto gap-4 p-4')

    def show(section):
        for key, btn in nav_buttons.items():
            btn.classes(replace='w-full justify-start rounded-lg'
                        + (' bg-[#e5ebf4] text-[#35558a] font-medium'
                           if key == section else ''))
        content.clear()
        with content:
            builders[section]()

    # ------------------------------------------------------------------
    # SECTION Account

    def build_account():
        with ui.card().classes('se-stitch-card w-full'):
            with ui.row(wrap=False).classes('items-center gap-4 w-full'):
                if user.get('picture'):
                    ui.image(user['picture']).classes('w-14 h-14 rounded-full')
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
            n_profiles = len(profiles.list_profiles(email))
            rows = designs.list_designs(email)
            n_outfits = sum(1 for r in rows if r['kind'] == 'outfit')
            n_garments = len(rows) - n_outfits
            ui.label(f'{n_profiles} measurement profile(s) · '
                     f'{n_outfits} outfit(s) · {n_garments} garment(s)') \
                .classes('text-sm text-stone-600')

    # ------------------------------------------------------------------
    # SECTION Measurements

    def build_measurements():
        with ui.card().classes('se-stitch-card w-full'):
            with ui.row(wrap=False).classes('items-center w-full justify-between'):
                ui.label('Body measurements').classes('se-section-label text-lg')
                with ui.row().classes('gap-2'):
                    ui.button('New profile', on_click=lambda: new_dialog.open()) \
                        .props('outline size=sm icon=add')
                    delete_btn = ui.button('Delete', on_click=lambda: delete_current()) \
                        .props('outline size=sm icon=delete color=negative')

            profile_select = ui.select(
                {}, label='Profile',
                on_change=lambda: load_editor(),
            ).classes('w-64').props('outlined dense')

            hint = ui.label('No saved measurements yet — create a profile to start') \
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
                profiles.set_units(email, units.value)
                update_unit_note()
                load_editor()

            def update_unit_note():
                unit_note.set_text(
                    'Lengths are shown in {} — switch above the fields.'
                    .format('inches' if units.value == 'in'
                            else 'centimeters'))

            with ui.row(wrap=False).classes('items-center gap-3 mt-1'):
                mode = ui.toggle(
                    {'essential': 'Essential', 'all': 'All measurements'},
                    value='essential',
                    on_change=lambda: load_editor(),
                ).props('no-caps unelevated rounded toggle-color=primary '
                        'padding="1px 12px"')
                units = ui.toggle(
                    {'in': 'inches', 'cm': 'cm'},
                    value=profiles.get_units(email),
                    on_change=change_units,
                ).props('no-caps unelevated rounded toggle-color=primary '
                        'padding="1px 12px"').tooltip(
                    'Display units — values are stored in centimeters')
            update_unit_note()

            editor = ui.column().classes('w-full')
            fields = {}
            skin_ctl = {'slider': None, 'touched': False, 'stored': None}

            def save_changes():
                data = profiles.get_profile(email, profile_select.value)
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
                profiles.save_profile(email, data['name'], values,
                                      skin_color=skin_color)
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
                    with ui.row(wrap=False).classes('items-center gap-3 mt-2 w-full'):
                        ui.label('Skin tone').classes('se-param-label w-24')

                        def _touch_tone(e):
                            skin_ctl['touched'] = True
                            skin_ctl['slider'].style(
                                f'color: {guide.skin_tone_hex(e.args)}')

                        skin_ctl['slider'] = ui.slider(
                            value=guide.skin_tone_t(stored_tone)
                                if stored_tone else 0.3,
                            min=0., max=1., step=0.01,
                        ).props('dense').classes('se-skin-slider w-64') \
                            .style('color: {}'.format(
                                stored_tone or '#b9b2a6')) \
                            .on('update:model-value', _touch_tone,
                                throttle=0.2, leading_events=False)
                        if not stored_tone:
                            ui.label('not set — mannequin uses muslin') \
                                .classes('se-param-label')

                    with ui.grid(columns=3).classes('w-full gap-x-4 gap-y-1 mt-2'):
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
                                ).classes('se-mono grow').props('outlined dense')
                                ui.button(
                                    icon='help_outline',
                                    on_click=lambda _, k=key: show_guide(k)
                                ).props('flat dense round size=sm color=grey-7') \
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
                profile_select.set_options(options)
                has_rows = bool(options)
                hint.set_visibility(not has_rows)
                profile_select.set_visibility(has_rows)
                delete_btn.set_visibility(has_rows)
                if has_rows:
                    profile_select.value = select_id if select_id in options \
                        else next(iter(options))
                else:
                    profile_select.value = None
                    editor.clear()
                    fields.clear()

            def delete_current():
                if profile_select.value is None:
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

    def build_garments():
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

                def do_rename():
                    ok = designs.rename_design(
                        email, rename_state['id'], rename_input.value)
                    if ok:
                        rename_dialog.close()
                        refresh()
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

            def remove(item_id):
                designs.delete_design(email, item_id)
                refresh()

            def refresh():
                listing.clear()
                with listing:
                    rows = designs.list_designs(email)
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
                                            icon='edit',
                                            on_click=lambda _, iid=row['id'],
                                                n=row['name']: open_rename(iid, n)
                                        ).props('flat dense round size=sm '
                                                'color=grey-7').tooltip('Rename')
                                        ui.button(
                                            icon='delete',
                                            on_click=lambda _, iid=row['id']:
                                                remove(iid)
                                        ).props('flat dense round size=sm '
                                                'color=negative').tooltip('Delete')
                                ui.label(row['updated_at'].strftime('%b %d, %Y')) \
                                    .classes('se-param-label px-1')

            refresh()

    # ------------------------------------------------------------------
    # SECTION Settings

    def build_settings():
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
        'settings': build_settings,
    }
    show('account')
