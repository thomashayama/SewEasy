"""Account area: sidebar-navigated pages for identity, measurements,
garments, and settings.

Registered by webapp.setup(); requires a signed-in user (redirects home
otherwise). Shares the wardrobe home shell and the application's theme.
Sections are rebuilt on every sidebar switch so they always reflect the
current database state (e.g. a units change in Settings shows up in the
Measurements editor immediately).
"""

from pathlib import Path

import numpy as np
from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app, run, ui
from sqlalchemy.exc import SQLAlchemyError

from gui import theme
from webapp import auth, designs, profiles, sharing
from webapp import measurement_guide as guide
from webapp.favorites import Favorites
from webapp.garment_catalog import studio_snapshot
from webapp.thumbnail_ui import ThumbnailQueue
from webapp.wardrobe import Wardrobe
# body_display registers the /body and /body_tones static mounts and owns
# the tone-tinted mannequin cache (shared with the studio 3D view)
from webapp.appearance_editor import HairEditor, SkinToneEditor
from webapp.body_display import profile_body_glb_url, profile_hair_glb_url
from webapp.access import Access
from webapp.access_ui import item_share_dialog
from webapp.measurement_help import measurement_overview, show_measurement_help
from webapp.gui_widgets import (confirm_delete, open_share_dialog,
                                preview_data_uri)


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
    'fabrics': ('texture', 'Fabrics'),
    'shared': ('folder_shared', 'Shared with me'),
    'friends': ('people_outline', 'Friends'),
    'settings': ('settings', 'Settings'),
    'agents': ('terminal', 'Agent connections'),
    'bases': ('architecture', 'Base garments'),
}


@ui.page('/account', title='SewEasy — Account')
async def account_page(request: Request):
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse('/')
    email = user['email']

    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    ui.add_css(Path(__file__).with_name('account.css').read_text(encoding='utf-8'))
    ui.colors(
        primary='#447cad',
        secondary=theme.colors.secondary,
        accent=theme.colors.accent,
        dark=theme.colors.dark,
        positive=theme.colors.positive,
        negative=theme.colors.negative,
        info=theme.colors.info,
        warning=theme.colors.warning,
    )

    nav_buttons = {}
    with ui.element('main').classes('se-home se-account'):
        with ui.element('header').classes('se-home-header'):
            ui.link('SewEasy', '/').classes('se-wordmark se-home-logo').props('aria-label="SewEasy home"')
            ui.label('Account').classes('se-home-location')
            ui.space()
            ui.button('Your wardrobe', icon='checkroom', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.button('Studio', icon='edit', on_click=lambda: ui.navigate.to('/studio')).props('flat')
        with ui.element('div').classes('se-home-content'):
            with ui.element('div').classes('se-home-heading'):
                with ui.column().classes('gap-1'):
                    ui.label('Your account').classes('se-home-title').props('role=heading aria-level=1')
                    ui.label('Manage your measurements, materials, sharing and preferences.').classes('se-home-subtitle')
            with ui.element('div').classes('se-account-layout'):
                with ui.element('nav').classes('se-account-nav').props('aria-label="Account sections"'):
                    for key, (icon, label) in SECTIONS.items():
                        nav_buttons[key] = ui.button(label, icon=icon, color=None,
                            on_click=lambda _, k=key: show(k)).props('flat no-caps align=left').classes('se-account-nav-item')
                content = ui.column().classes('se-account-content')

    # Unsaved measurement edits: set by the editor, checked before anything
    # rebuilds a section (rebuilding re-reads the DB and discards edits)
    unsaved = {'dirty': False}
    # A shared item's page links here to open it; used once, on arrival.
    arriving = {key: request.query_params.get(key) for key in ('profile', 'fabric')}

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
            btn.classes(replace='se-account-nav-item'
                        + (' se-account-nav-active'
                           if key == section else ''))
            btn.props('aria-current=page' if key == section else 'aria-current=false')
        content.clear()
        with content:
            await builders[section]()

    # ------------------------------------------------------------------
    # SECTION Account

    async def build_account():
        store = Wardrobe(email, app.storage.user)
        favorites = Favorites(store)
        entries = await run.io_bound(favorites.list)

        with ui.card().classes('se-stitch-card w-full'):
            with ui.row(wrap=False).classes('se-account-summary items-center gap-4 w-full'):
                if user.get('picture'):
                    ui.image(user['picture']) \
                        .props('alt="Your account picture"') \
                        .classes('w-14 h-14 rounded-full')
                else:
                    ui.icon('account_circle').classes('text-6xl text-gray-400')
                with ui.column().classes('se-account-identity gap-0.5 min-w-0'):
                    ui.label(user.get('name') or email).classes('se-section-label text-lg')
                    ui.label(email).classes('se-param-label')
                ui.space()
                ui.button('Log out', on_click=lambda: ui.navigate.to('/auth/logout')) \
                    .props('outline size=sm icon=logout').classes('se-nowrap-button')

        def open_favorite(entry):
            if entry['favorite_kind'] == 'share':
                ui.navigate.to(f'/shared/{entry["id"]}')
                return
            outfit = entry['kind'] == 'outfit'
            # Re-read: it may have been renamed, edited or deleted since this page opened
            item = next((x for x in store.read()['outfits' if outfit else 'garments']
                         if x['id'] == entry['id']), None)
            if item is None:
                ui.notify('This saved item is no longer available.', type='warning')
                return
            storage = app.storage.user
            storage['pending_design'] = studio_snapshot(
                item['garments'] if outfit else [item], item['name'], storage.get('pending_design'),
                outfit_revision_id=item.get('revision_id'), editor_mode=entry['kind'],
                outfit_updated_at=item.get('updated_at'))
            storage.pop('outfit_edit_return', None)
            ui.navigate.to('/studio')

        async def unfavorite(entry, button):
            button.disable()    # One removal per click, however fast the clicks
            try:
                await run.io_bound(favorites.set, entry['favorite_kind'], entry['id'], False)
            except (ValueError, SQLAlchemyError):
                button.enable()
                ui.notify('Could not update favorites. Please try again.', type='warning')
                return
            entries.remove(entry)
            render_favorites()

        def favorite_card(entry):
            snapshot, kind = entry['snapshot'], entry['kind']
            shared = entry['favorite_kind'] == 'share'
            if shared:
                detail = f'{kind.capitalize()} · {entry["owner_name"]}'
            elif kind == 'outfit':
                count = len(snapshot['garments'])
                detail = f'Outfit · {count} garment' + ('s' if count != 1 else '')
            else:
                detail = 'Garment'
            with ui.element('div').classes('se-library-entry'):
                with ui.button(on_click=lambda: open_favorite(entry)) \
                        .props('flat no-caps').classes('se-library-card') as card:
                    card._props['aria-label'] = f'Open {kind} {snapshot["name"]}'
                    with ui.element('div').classes('se-home-flats se-library-art'):
                        previews.visual(snapshot['garments'] if kind == 'outfit' else [snapshot],
                                        outfit_id=None if shared or kind != 'outfit' else snapshot['revision_id'],
                                        image=entry.get('thumbnail'))
                    with ui.column().classes('se-library-caption'):
                        ui.label(snapshot['name']).classes('se-library-name')
                        ui.label(detail).classes('se-home-muted')
                heart = ui.button(icon='favorite', color=None,
                                  on_click=lambda e: unfavorite(entry, e.sender)) \
                    .props('flat round dense :ripple=false aria-pressed=true') \
                    .classes('se-favorite is-favorite')
                heart._props['aria-label'] = f'Remove {snapshot["name"]} from favorites'
                heart.tooltip('Remove from favorites')

        def render_favorites():
            all_link.set_visibility(bool(entries))
            grid.clear()
            with grid:
                if not entries:
                    with ui.column().classes('se-library-empty w-full'):
                        ui.icon('favorite_border').classes('se-empty-icon')
                        ui.label('No favorites yet').classes('se-empty-title')
                        ui.label('Tap the heart on a garment or outfit in your wardrobe to keep it here.') \
                            .classes('se-home-muted')
                        ui.link('Go to your wardrobe', '/').classes('text-sm')
                    return
                with ui.element('div').classes('se-library-grid'):
                    for entry in entries:
                        favorite_card(entry)

        with ui.card().classes('se-stitch-card w-full'):
            with ui.row(wrap=False).classes('items-center w-full justify-between'):
                ui.label('Favorites').classes('se-section-label text-lg')
                all_link = ui.link('Open in your wardrobe', '/?tab=favorites').classes('text-sm')
            grid = ui.element('div').classes('w-full')
            previews = ThumbnailQueue(store)
            render_favorites()
        # Render any of your own favorites still missing a 3D thumbnail
        for entry in entries:
            if entry['favorite_kind'] == 'outfit':
                previews.enqueue('outfit', entry['snapshot']['revision_id'], entry['snapshot']['garments'])
            elif entry['favorite_kind'] == 'garment':
                previews.enqueue('garment', entry['id'], [entry['snapshot']])

    # ------------------------------------------------------------------
    # SECTION Measurements

    async def build_measurements():
        with ui.card().classes('se-stitch-card w-full'):
            NEW_PROFILE = '__new__'

            with ui.row(wrap=False).classes('se-measure-head items-center w-full justify-between'):
                ui.label('Body measurements').classes('se-section-label text-lg')
                with ui.row(wrap=False).classes('se-measure-actions gap-2'):
                    copy_btn = ui.button('Save a copy',
                                         on_click=lambda: copy_current()) \
                        .props('outline size=sm icon=content_copy no-caps')
                    leave_btn = ui.button('Remove from my list',
                                          on_click=lambda: leave_current()) \
                        .props('flat size=sm icon=close no-caps')
                    default_btn = ui.button('Make default', on_click=lambda: toggle_default()) \
                        .props('outline size=sm icon=star_outline no-caps')
                    with default_btn:
                        default_tip = ui.tooltip('Open new designs with these measurements')
                    share_btn = ui.button('Share',
                                          on_click=lambda: share_current()) \
                        .props('outline size=sm icon=share') \
                        .tooltip('Privacy & sharing')
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
                measurement_overview()
                ui.label('Every field below has a ? button with a diagram and a photo '
                         'showing exactly where that measurement is taken.') \
                    .classes('text-sm text-stone-600 mt-1')

            show_guide = show_measurement_help

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

            with ui.row(wrap=False).classes('se-measure-modes items-center gap-3 mt-1'):
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

            # Use the same fitted body as the studio, including the profile tone.
            with ui.row(wrap=False).classes('se-measure-body w-full gap-4 items-start'):
                with ui.column().classes('se-measure-figure shrink-0 gap-1'):
                    scene = _mannequin_scene()
                    mannequin_note = ui.label('Measurement-fitted body; approximate shape') \
                        .classes('se-param-label w-64')
                editor = ui.column().classes('se-measure-editor grow min-w-0')

            fields = {}
            # The profile's skin tone and hair editors, rebuilt with the editor
            appearance = {'skin': None, 'hair': None}
            scene_ctl = {'body': None, 'url': None, 'hair': None, 'hair_url': None, 'hair_request': 0}

            def set_mannequin_url(url):
                if url == scene_ctl['url']:
                    return
                if scene_ctl['body'] is not None:
                    scene_ctl['body'].delete()
                with scene:
                    scene_ctl['body'] = scene.gltf(url).rotate(np.pi / 2, 0., 0.)
                scene_ctl['url'] = url

            def set_hair_url(url):
                if url == scene_ctl['hair_url']:
                    return
                if scene_ctl['hair'] is not None:
                    scene_ctl['hair'].delete()
                    scene_ctl['hair'] = None
                if url:
                    with scene:
                        scene_ctl['hair'] = scene.gltf(url).rotate(np.pi / 2, 0., 0.)
                scene_ctl['hair_url'] = url

            async def show_hair(hair, measurements):
                # Off-loop, and only the newest request draws: sliders send many.
                scene_ctl['hair_request'] += 1
                request, selected = scene_ctl['hair_request'], profile_select.value
                try:
                    url = await run.io_bound(profile_hair_glb_url, measurements, hair)
                except ValueError:
                    return
                if request == scene_ctl['hair_request'] and profile_select.value == selected:
                    set_hair_url(url)

            def set_mannequin_tone(color):
                data = profiles.get_profile(email, profile_select.value)
                if not data:
                    return
                try:
                    set_mannequin_url(profile_body_glb_url(color, data['measurements']))
                    mannequin_note.set_text('Measurement-fitted body; approximate shape')
                except ValueError as error:
                    if scene_ctl['body'] is not None:
                        scene_ctl['body'].delete()
                    scene_ctl.update(body=None, url=None)
                    mannequin_note.set_text(str(error))

            async def save_changes():
                data = await run.io_bound(
                    profiles.get_profile, email, profile_select.value)
                if data is None:
                    ui.notify('Profile not found', type='negative')
                    return
                # Merge: fields not shown (Essential mode) keep their values
                values = dict(data['measurements'])
                shown = guide.editor_values(data['measurements'])
                for key, field in fields.items():
                    try:
                        values[key] = guide.stored_value(
                            key, field.value, units.value,
                            previous_cm=shown.get(key))
                    except (TypeError, ValueError):
                        pass
                inseam = values.pop('inseam', None)

                # In Essential mode the hidden measurements scale with the
                # essentials they depend on, staying anatomically consistent
                scaled = {}
                if mode.value == 'essential':
                    scaled = guide.scale_coupled(data['measurements'], values)
                    values.update(scaled)
                # The inseam is not stored: it sets how deep the crotch sits.
                if inseam is not None:
                    values = guide.apply_inseam(values, inseam)

                errors, warnings = guide.validate_measurements(values)
                if errors:
                    ui.notify('Not saved — impossible measurements:\n• '
                              + '\n• '.join(errors),
                              type='negative', multi_line=True,
                              close_button=True)
                    return

                # Skin tone and hair: as chosen here, otherwise as the profile had them
                skin, hair_editor = appearance['skin'], appearance['hair']
                skin_color = skin.value if skin is not None else data.get('skin_color')
                hair = hair_editor.value if hair_editor is not None and hair_editor.touched else None
                try:
                    await run.io_bound(profiles.update_profile, email,
                                       data['id'], values, skin_color, hair)
                except ValueError as error:
                    ui.notify(str(error), type='negative')
                    return
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
                load_editor()  # Update the fitted body and the saved measurement state.

            def load_editor():
                editor.clear()
                fields.clear()
                unsaved['dirty'] = False
                if profile_select.value is None:
                    return
                data = profiles.get_profile(email, profile_select.value)
                if data is None:
                    return
                # Viewers read a shared profile; its owner and admins edit it.
                role = data['role']
                shared = shared_rows.get(data['id'])
                is_default = data['id'] == default_profile['id']
                default_btn.set_text('Default' if is_default else 'Make default')
                default_btn.props(f'icon={"star" if is_default else "star_outline"}')
                default_tip.set_text('New designs open with these measurements. Click to stop.' if is_default
                                     else 'Open new designs with these measurements')
                default_btn.set_visibility(True)
                copy_btn.set_visibility(role != 'owner')
                leave_btn.set_visibility(bool(shared and shared['is_member']))
                share_btn.set_visibility(role in ('owner', 'admin'))
                delete_btn.set_visibility(role in ('owner', 'admin'))
                readonly = role == 'viewer'
                shown = guide.editor_values(data['measurements'])
                keys = guide.editor_keys(data['measurements'], mode.value == 'essential')
                with editor:
                    if role != 'owner':
                        ui.label(f'Shared by {data["owner_name"]} · '
                                 + ('As an admin, your saves update it for everyone.' if role == 'admin'
                                    else 'Save a copy to edit your own.')).classes('se-param-label')
                    stored_tone = data.get('skin_color')
                    set_mannequin_tone(stored_tone)
                    set_hair_url(profile_hair_glb_url(data['measurements'], data['hair']))

                    with ui.grid(columns=2).classes('se-measure-grid w-full gap-x-4 gap-y-1 mt-2'):
                        for key in keys:
                            with ui.row(wrap=False).classes('items-center gap-0 w-full'):
                                fields[key] = ui.number(
                                    label=guide.label_for(key)
                                        + guide.unit_suffix(key, units.value),
                                    value=guide.display_value(
                                        key, shown[key],
                                        units.value),
                                    format='%.2f',
                                    step=0.25 if units.value == 'in' else 0.5,
                                    # Angles can be negative; lengths can't
                                    min=None if key in guide.ANGLE_KEYS else 0,
                                    on_change=lambda: unsaved.update(dirty=True),
                                ).classes('se-mono grow').props('outlined dense' + (' readonly' if readonly else ''))
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

                    # Skin tone and hair: the mannequin wears them wherever
                    # this profile is chosen, in the studio as here.
                    async def tone_changed(tone):
                        unsaved['dirty'] = True
                        selected_profile = profile_select.value
                        try:
                            url = await run.io_bound(profile_body_glb_url, tone, data['measurements'])
                        except ValueError as error:
                            if profile_select.value == selected_profile:
                                mannequin_note.set_text(str(error))
                            return
                        if profile_select.value == selected_profile:
                            set_mannequin_url(url)

                    async def hair_changed(hair):
                        unsaved['dirty'] = True
                        await show_hair(hair, data['measurements'])

                    ui.separator().classes('mt-3')
                    appearance['skin'] = SkinToneEditor(stored_tone, readonly, tone_changed)
                    appearance['hair'] = HairEditor(data['hair'], readonly, hair_changed)
                    if not readonly:
                        ui.button('Save changes', on_click=save_changes) \
                            .props('unelevated icon=save').classes('se-nowrap-button mt-3 self-end')

            shared_rows = {}
            default_profile = {'id': None}

            def refresh_profiles(select_id=None):
                rows = profiles.list_profiles(email)
                default = profiles.get_default_profile(email)
                default_profile['id'] = default and default['id']
                mark = lambda profile_id: ' · default' if profile_id == default_profile['id'] else ''  # noqa: E731
                options = {r['id']: r['name'] + mark(r['id']) for r in rows}
                shared_rows.clear()
                shared_rows.update({r['id']: r for r in profiles.shared_profiles(email)})
                for row in shared_rows.values():
                    options[row['id']] = f'{row["name"]} — shared by {row["owner_name"]}' + mark(row['id'])
                has_rows = bool(options)
                options[NEW_PROFILE] = '＋ New profile…'
                profile_select.set_options(options)
                hint.set_visibility(not has_rows)
                for button in (copy_btn, leave_btn, share_btn, delete_btn, default_btn):
                    button.set_visibility(False)    # load_editor shows what the role allows
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

            def share_current():
                if profile_select.value in (None, NEW_PROFILE):
                    return
                selected = profile_select.value
                item_share_dialog(email, 'body', selected, on_removed=refresh_profiles,
                                  on_done=lambda: refresh_profiles(selected))

            async def delete_current():
                if profile_select.value in (None, NEW_PROFILE):
                    return
                data = profiles.get_profile(email, profile_select.value)
                name = data['name'] if data else 'this profile'
                shared = data and data['role'] != 'owner'
                if not await confirm_delete(
                        f'Delete the measurement profile "{name}"'
                        + (' for everyone with access' if shared else '')
                        + '? Its measurements and skin tone will be lost.'):
                    return
                if not profiles.delete_profile(email, profile_select.value):
                    ui.notify('Only the profile’s owner or an admin can delete it.', type='warning')
                    return
                ui.notify('Profile deleted')
                refresh_profiles()

            def toggle_default():
                selected = profile_select.value
                if selected in (None, NEW_PROFILE):
                    return
                make = selected != default_profile['id']
                try:
                    profiles.set_default_profile(email, selected if make else None)
                except ValueError as error:
                    ui.notify(str(error), type='warning')
                    return
                if make:
                    # The draft in this browser picks it up too: no choice made here
                    # means the studio opens with the default.
                    pending = app.storage.user.get('pending_design')
                    if pending:
                        pending['body_choice'] = None
                        app.storage.user['pending_design'] = pending
                refresh_profiles(selected)
                ui.notify('New designs open with these measurements' if make else 'No default measurements',
                          type='positive' if make else 'info')

            def copy_current():
                if profile_select.value in (None, NEW_PROFILE):
                    return
                name = profiles.copy_profile(email, profile_select.value)
                if name is None:
                    ui.notify('This profile is no longer shared with you.', type='warning')
                    refresh_profiles()
                    return
                created = next((r for r in profiles.list_profiles(email) if r['name'] == name), None)
                refresh_profiles(created['id'] if created else None)
                ui.notify(f'Saved a copy as "{name}"', type='positive')

            def leave_current():
                shared = shared_rows.get(profile_select.value)
                if not shared:
                    return
                try:
                    Access(email).leave(shared['share_id'])
                except ValueError as error:
                    ui.notify(str(error), type='warning')
                refresh_profiles()

            # --- New-profile dialog ---
            def create_profile():
                name = (new_name.value or '').strip()
                if not name:
                    ui.notify('Give the profile a name', type='warning')
                    return
                profiles.save_profile(email, name, profiles.default_measurements(new_base.value),
                                      hair=profiles.default_hair(new_base.value))
                new_dialog.close()
                new_name.value = ''
                rows = profiles.list_profiles(email)
                created = next((r for r in rows if r['name'] == name), None)
                refresh_profiles(created['id'] if created else None)
                ui.notify(f'Created "{name}" from the {profiles.DEFAULT_BODIES[new_base.value].lower()}',
                          type='positive')

            with ui.dialog() as new_dialog, ui.card().classes('items-center'):
                ui.label('New measurement profile')
                ui.label('Starts from a default body — adjust and save') \
                    .classes('se-param-label')
                new_name = ui.input(label='Name', placeholder='e.g. My measurements') \
                    .classes('w-64').props('outlined dense')
                new_base = ui.select(dict(profiles.DEFAULT_BODIES), value='all', label='Start from') \
                    .classes('w-64').props('outlined dense options-dense')
                with ui.row():
                    ui.button('Create', on_click=create_profile)
                    ui.button('Cancel', on_click=new_dialog.close).props('flat')

            wanted = arriving.pop('profile', None)
            refresh_profiles(int(wanted) if wanted and wanted.isdigit() else None)

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
        design_rows = await run.io_bound(sharing.shared_designs_with_me, email)

        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Shared with me').classes('se-section-label text-lg')
            ui.label('Garments, outfits, fabrics and measurement profiles shared '
                     'with you are in your wardrobe’s Shared with me tab. '
                     'Shared measurements also appear under Measurements and in '
                     'the studio; shared fabrics under Fabrics.') \
                .classes('text-sm text-stone-600')
            ui.link('Open Shared with me', '/?tab=shared').classes('text-sm')

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
            await run.io_bound(sharing.decline_design_share, email, share_id)
            await show('shared')

        if design_rows:
            with ui.card().classes('se-stitch-card w-full'):
                ui.label('Earlier saved designs').classes('se-section-label')
                ui.label('Shared before garments and outfits had their own sharing.') \
                    .classes('se-param-label')
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

    async def build_agents():
        from webapp.agent_connections_ui import connections
        connections(email)

    async def build_bases():
        from webapp.base_garments_ui import base_library
        base_library(email)

    async def build_friends():
        from webapp.friends_ui import friends_panel
        friends_panel(email)

    async def build_fabrics():
        from webapp.fabrics_ui import fabric_library
        await fabric_library(email, open_id=arriving.pop('fabric', None))

    builders = {
        'account': build_account,
        'measurements': build_measurements,
        'garments': build_garments,
        'shared': build_shared,
        'settings': build_settings,
        'agents': build_agents,
        'bases': build_bases,
        'friends': build_friends,
        'fabrics': build_fabrics,
    }
    section = request.query_params.get('section', 'account')
    await show(section if section in builders else 'account')
