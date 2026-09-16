"""Permission-checked read-only landing page for a shared garment or outfit."""
from pathlib import Path

from fastapi import Request
from nicegui import app, ui

from gui import theme
from webapp import auth, config
from webapp.garment_catalog import thumbnail, studio_snapshot
from webapp.wardrobe import Wardrobe
from webapp.wardrobe_sharing import WardrobeSharing, ShareUnavailable
from webapp.wardrobe_actions import share_dialog, source_label


@ui.page('/shared/{share_id}', title='SewEasy — Shared design')
def shared_page(request: Request, share_id: str):
    user = auth.current_user(request)
    store = Wardrobe(user['email'] if user else None, app.storage.user)
    sharing = WardrobeSharing(store)
    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    with ui.element('main').classes('se-home'):
        with ui.element('header').classes('se-home-header'):
            ui.link('SewEasy', '/').classes('se-wordmark se-home-logo')
            ui.space()
            ui.link('Your wardrobe', '/').classes('text-sm')
        try:
            source = sharing.get(share_id)
        except ShareUnavailable:
            with ui.column().classes('se-home-content gap-4'):
                ui.icon('lock_outline').classes('text-3xl')
                ui.label('This item isn’t available').classes('se-home-title')
                ui.label('The link may have been turned off, or access is limited to invited people.').classes('text-sm')
                if not user:
                    def sign_in():
                        if config.google_configured():
                            ui.navigate.to('/auth/login')
                        else:
                            ui.notify('Sign-in is not configured on this installation.', type='info')
                    ui.button('Sign in with your invited account', on_click=sign_in).props('unelevated')
                else:
                    ui.label('Sign in with the email address the owner invited.').classes('text-sm')
            return
        item, kind = source['snapshot'], source['kind']
        items = item['garments'] if kind == 'outfit' else [item]
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
                ui.label(f'Owned by {source["owner_name"]}').classes('text-sm')
                if source_label(item):
                    ui.label(source_label(item)).classes('se-home-muted')
                if kind == 'outfit':
                    for g in items:
                        ui.label(g['name']).classes('text-sm')
                ui.label('Save your own copy to customize the design, colors and fabrics.').classes('text-sm')
                def open_editor():
                    # Access is checked again when saving a copy from the editor.
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
                if source['is_owner']:
                    ui.button('Manage access', icon='share', on_click=lambda: share_dialog(store, kind, item)).props('flat')
