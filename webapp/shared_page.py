"""Permission-checked read-only landing page for a shared garment or outfit."""
from pathlib import Path

from fastapi import Request
from nicegui import app, ui

from gui import theme
from webapp import auth, config
from webapp.garment_catalog import thumbnail, studio_snapshot
from webapp.thumbnail_cache import bundled_thumbnail, thumbnail_key
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
                ui.label('This version isn’t available').classes('se-home-title')
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
            image = source.get('thumbnail') or bundled_thumbnail(thumbnail_key(items))
            with ui.element('div').classes('se-shared-preview'):
                if image:
                    ui.image(image).props('fit=contain alt="3D render on the default mannequin"').classes('w-full h-full')
                else:
                    ui.html(''.join(thumbnail(g) for g in items[:3])).classes('se-home-flats w-full h-full')
            with ui.column().classes('gap-4 min-w-0'):
                ui.label(f'Shared {kind} · Version {item["version"]}').classes('se-home-muted')
                ui.label(item['name']).classes('se-home-title break-words')
                ui.label(f'Owned by {source["owner_name"]}').classes('text-sm')
                if source_label(item):
                    ui.label(source_label(item)).classes('se-home-muted')
                if kind == 'outfit':
                    for g in items:
                        ui.label(f'{g["name"]} · v{g["version"]}').classes('text-sm')
                ui.label('Fork it to make your own version, including its colors and fabrics.').classes('text-sm')
                async def fork():
                    try:
                        result = sharing.fork(share_id)
                    except ValueError as error:
                        ui.notify(str(error), type='warning')
                        return
                    snapshot = studio_snapshot(result['garments'] if kind == 'outfit' else [result],
                        result['name'], app.storage.user.get('pending_design'),
                        outfit_revision_id=result['revision_id'] if kind == 'outfit' else None)
                    app.storage.user['pending_design'] = snapshot
                    ui.navigate.to('/studio')
                ui.button('Fork to my library', icon='call_split', on_click=fork).props('unelevated')
                ui.label('Your fork belongs to you. The original stays unchanged.').classes('se-home-muted')
                if source['is_owner']:
                    ui.button('Manage access', icon='share', on_click=lambda: share_dialog(store, kind, item)).props('flat')
