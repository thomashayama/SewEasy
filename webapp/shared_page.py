"""Permission-checked landing page for any shared item: garment, outfit, fabric or body profile.

What it offers follows the visitor's role (webapp/access.py): anyone who can
open it may save a copy; admins also edit, manage access and delete; members
can remove it from their list.
"""
from pathlib import Path

from fastapi import Request
from nicegui import app, run, ui

from gui import theme
from webapp import auth, config
from webapp.access import NOUNS
from webapp.access_ui import access_dialog
from webapp.garment_catalog import thumbnail, studio_snapshot
from webapp.gui_widgets import confirm_delete
from webapp.wardrobe import Wardrobe
from webapp.wardrobe_sharing import WardrobeSharing, ShareUnavailable
from webapp.wardrobe_actions import source_label
from webapp.favorites import Favorites
from webapp import finished_photos
from webapp.finished_photos_ui import photo_gallery, photos_dialog


def unavailable(user):
    with ui.column().classes('se-home-content gap-4'):
        ui.icon('lock_outline').classes('text-3xl')
        ui.label('This item isn’t available').classes('se-home-title')
        ui.label('The owner may have made it private, or access is limited to friends or invited people.').classes('text-sm')
        if not user:
            def sign_in():
                if config.google_configured():
                    ui.navigate.to('/auth/login')
                else:
                    ui.notify('Sign-in is not configured on this installation.', type='info')
            ui.button('Sign in with your invited account', on_click=sign_in).props('unelevated')
        else:
            ui.label('Sign in with the email address the owner invited.').classes('text-sm')


def role_actions(sharing, source, share_id, reopen):
    """Manage, delete and leave, as the visitor's role allows."""
    noun = NOUNS[source['kind']]
    name = source['snapshot'].get('name', '')
    if source['role'] in ('owner', 'admin'):
        ui.button('Privacy & sharing', icon='share',
                  on_click=lambda: access_dialog(sharing, share_id, on_removed=reopen, on_done=reopen)).props('flat no-caps')

        async def delete():
            if not await confirm_delete(f'Delete the {noun} “{name}” for everyone? Copies others saved remain theirs.'):
                return
            try:
                await run.io_bound(sharing.delete, share_id)
            except ValueError as error:
                ui.notify(str(error), type='warning')
                return
            ui.notify(f'Deleted {name}', type='positive')
            ui.navigate.to('/')
        ui.button(f'Delete {noun}', icon='delete_outline', on_click=delete).props('flat no-caps color=negative')
    if source['is_member'] and not source['is_owner']:
        def leave():
            try:
                sharing.leave(share_id)
            except ValueError as error:
                ui.notify(str(error), type='warning')
                return
            ui.notify(f'Removed {name} from your list', type='positive')
            ui.navigate.to('/?tab=shared')
        ui.button('Remove from my list', icon='close', on_click=leave).props('flat no-caps')


def sign_in_to_copy(user):
    if not user:
        ui.label('Sign in to save your own copy.').classes('text-sm')
    return bool(user)


@ui.page('/shared/{share_id}', title='SewEasy — Shared item')
def shared_page(request: Request, share_id: str):
    user = auth.current_user(request)
    email = user['email'] if user else None
    store = Wardrobe(email, app.storage.user)
    sharing = WardrobeSharing(store)
    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    ui.add_css(Path(__file__).with_name('fabrics.css').read_text(encoding='utf-8'))
    reopen = lambda: ui.navigate.to(f'/shared/{share_id}')   # noqa: E731
    with ui.element('main').classes('se-home'):
        with ui.element('header').classes('se-home-header'):
            ui.link('SewEasy', '/').classes('se-wordmark se-home-logo')
            ui.space()
            ui.link('Your wardrobe', '/').classes('text-sm')
        try:
            source = sharing.get(share_id)
        except ShareUnavailable:
            unavailable(user)
            return
        kind = source['kind']
        if kind == 'fabric':
            from webapp import fabrics
            try:
                record = fabrics.get_fabric(email, source['revision_id'])
            except ValueError:
                unavailable(user)
                return
            shared_fabric(user, sharing, source, share_id, record, reopen)
        elif kind == 'body':
            from webapp import profiles
            data = profiles.get_profile(email, source['revision_id'])
            if data is None:
                unavailable(user)
                return
            shared_body(user, sharing, source, share_id, data, reopen)
        else:
            shared_design(store, sharing, source, share_id, reopen)


def shared_design(store, sharing, source, share_id, reopen):
    item, kind = source['snapshot'], source['kind']
    items = item['garments'] if kind == 'outfit' else [item]
    administers = source['role'] in ('owner', 'admin')
    with ui.element('section').classes('se-home-content se-shared-design'):
        image = source.get('thumbnail')
        with ui.element('div').classes('se-shared-preview'):
            if image:
                ui.image(image).props('fit=contain alt="3D render on the default mannequin"').classes('w-full h-full')
            else:
                ui.html(''.join(thumbnail(g) for g in items[:3])).classes('se-home-flats w-full h-full')
        with ui.column().classes('gap-4 min-w-0'):
            ui.label(f'Shared {kind}').classes('se-home-muted')
            ui.label(item['name']).classes('se-home-title break-words')
            ui.label(f'Owned by {source["owner_name"]}' + (' · You are an admin' if source['role'] == 'admin' else '')) \
                .classes('text-sm')
            favorites = Favorites(store)
            favorite_kind = kind if source['is_owner'] else 'share'
            favorite_id = source['revision_id'] if source['is_owner'] else share_id

            @ui.refreshable
            def favorite_control():
                selected = f'{favorite_kind}:{favorite_id}' in favorites.keys()

                def toggle():
                    try:
                        favorites.set(favorite_kind, favorite_id, not selected)
                        favorite_control.refresh()
                    except ValueError as error:
                        ui.notify(str(error), type='info')
                ui.button('Favorited' if selected else 'Add to favorites',
                          icon='favorite' if selected else 'favorite_border', on_click=toggle).props('flat no-caps')
            favorite_control()
            if source_label(item):
                ui.label(source_label(item)).classes('se-home-muted')
            if kind == 'outfit':
                for g in items:
                    ui.label(g['name']).classes('text-sm')
            ui.label('Your saves update the original for everyone with access.' if administers else
                     'Save your own copy to customize the design, colors and fabrics.').classes('text-sm')

            def open_editor():
                # Access is checked again when saving from the editor.
                try:
                    latest = sharing.get(share_id)
                except ValueError as error:
                    ui.notify(str(error), type='warning')
                    return
                current = latest['snapshot']
                app.storage.user['pending_design'] = studio_snapshot(
                    current['garments'] if kind == 'outfit' else [current], current['name'],
                    app.storage.user.get('pending_design'), editor_mode=kind,
                    outfit_revision_id=current.get('revision_id'), source_share=share_id,
                    outfit_updated_at=current.get('updated_at'))
                app.storage.user.pop('outfit_edit_return', None)
                ui.navigate.to('/studio')
            with ui.dialog() as copy_dialog, ui.card().classes('w-96 max-w-full gap-3'):
                ui.label('Save a copy').classes('text-lg font-semibold')
                copy_name = ui.input('Name', value=store.suggested_copy_name(kind, item['name'])).props('outlined dense autofocus').classes('w-full')

                def save_copy():
                    try:
                        result = sharing.fork(share_id, copy_name.value)
                    except ValueError as error:
                        ui.notify(str(error), type='warning')
                        return
                    app.storage.user['pending_design'] = studio_snapshot(
                        result['garments'] if kind == 'outfit' else [result], result['name'],
                        app.storage.user.get('pending_design'), editor_mode=kind,
                        outfit_revision_id=result.get('revision_id'), outfit_updated_at=result.get('updated_at'))
                    app.storage.user.pop('outfit_edit_return', None)
                    ui.navigate.to('/studio')
                with ui.row().classes('w-full justify-end'):
                    ui.button('Cancel', on_click=copy_dialog.close).props('flat')
                    ui.button('Save a copy', on_click=save_copy).props('unelevated')
            ui.button('Save a copy', icon='content_copy', on_click=copy_dialog.open).props('unelevated')
            ui.button('Edit ' + kind, icon='edit', on_click=open_editor).props('outline')
            role_actions(sharing, source, share_id, reopen)
            if source['is_owner']:
                ui.button('Made it — add photos', icon='add_a_photo',
                          on_click=lambda: photos_dialog(store, kind, item, made_it.refresh)).props('flat')

            @ui.refreshable
            def made_it():
                photos = finished_photos.list_photos(store, share_id=share_id)
                if photos:
                    ui.separator()
                    ui.label('Made it').classes('se-home-dialog-title')
                    ui.label('Photos of the finished piece, added by its owner.').classes('se-home-muted')
                    photo_gallery(photos)
            made_it()


def shared_fabric(user, sharing, source, share_id, record, reopen):
    from webapp import fabrics
    from webapp.fabric_catalog import evidence_label, metadata
    from webapp.fabrics_ui import preview_tile
    content = record['content']
    with ui.element('section').classes('se-home-content se-shared-design'):
        with ui.element('div').classes('se-shared-preview se-shared-fabric'):
            preview_tile(record)
        with ui.column().classes('gap-4 min-w-0'):
            ui.label('Shared fabric').classes('se-home-muted')
            ui.label(record['name']).classes('se-home-title break-words')
            ui.label(f'Owned by {source["owner_name"]}' + (' · You are an admin' if source['role'] == 'admin' else '')) \
                .classes('text-sm')
            catalog = metadata(content.get('catalog'))
            if catalog:
                ui.label(f'{catalog["composition"]} · {catalog["construction"]}').classes('text-sm')
            values = content['properties']
            summary = [f'{values[key]["value"]:.4g} {unit}' for key, unit in (('weight', 'g/m²'), ('thickness', 'mm'))
                       if values[key]['value'] is not None]
            ui.label(' · '.join(summary) or 'Physical properties not supplied').classes('text-sm')
            ui.label(evidence_label(content)).classes('se-home-muted')
            if content.get('description'):
                ui.label(content['description']).classes('text-sm break-words')
            if sign_in_to_copy(user):
                async def copy():
                    try:
                        mine = await run.io_bound(fabrics.copy_fabric, user['email'], record['id'])
                    except ValueError as error:
                        ui.notify(str(error), type='warning')
                        return
                    ui.navigate.to(f'/account?section=fabrics&fabric={mine["id"]}')
                ui.button('Save a copy', icon='content_copy', on_click=copy).props('unelevated')
                ui.button('Edit fabric' if source['role'] in ('owner', 'admin') else 'Open in fabric library',
                          icon='edit' if source['role'] in ('owner', 'admin') else 'texture',
                          on_click=lambda: ui.navigate.to(f'/account?section=fabrics&fabric={record["id"]}')) \
                    .props('outline')
            role_actions(sharing, source, share_id, reopen)


def shared_body(user, sharing, source, share_id, data, reopen):
    from webapp import measurement_guide as guide
    from webapp import profiles
    units = profiles.get_units(user['email']) if user else 'cm'
    with ui.element('section').classes('se-home-content se-shared-design'):
        with ui.element('div').classes('se-shared-preview justify-center'):
            ui.icon('accessibility_new').classes('text-8xl text-slate-400')
        with ui.column().classes('gap-4 min-w-0'):
            ui.label('Shared measurements').classes('se-home-muted')
            ui.label(data['name']).classes('se-home-title break-words')
            ui.label(f'Owned by {source["owner_name"]}' + (' · You are an admin' if source['role'] == 'admin' else '')) \
                .classes('text-sm')
            values = guide.editor_values(data['measurements'])
            with ui.grid(columns=2).classes('w-full gap-x-6 gap-y-1'):
                for key in guide.editor_keys(data['measurements'], essential_only=True):
                    try:
                        shown = guide.display_value(key, values[key], units)
                    except (TypeError, ValueError):
                        continue
                    ui.label(guide.label_for(key)).classes('text-sm')
                    ui.label(f'{shown:.1f} {guide.unit_suffix(key, units).strip(" ()")}').classes('text-sm se-mono')
            if sign_in_to_copy(user):
                def copy():
                    name = profiles.copy_profile(user['email'], data['id'])
                    if name is None:
                        ui.notify('This profile is no longer shared with you.', type='warning')
                        return
                    mine = next((p for p in profiles.list_profiles(user['email']) if p['name'] == name), None)
                    ui.navigate.to('/account?section=measurements' + (f'&profile={mine["id"]}' if mine else ''))
                ui.button('Save a copy', icon='content_copy', on_click=copy).props('unelevated')
                ui.button('Edit measurements' if source['role'] in ('owner', 'admin') else 'Open in measurements',
                          icon='straighten',
                          on_click=lambda: ui.navigate.to(f'/account?section=measurements&profile={data["id"]}')) \
                    .props('outline')
            role_actions(sharing, source, share_id, reopen)

