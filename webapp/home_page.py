"""Wardrobe home with cached renders and a background queue for missing thumbnails."""
from pathlib import Path
import re

from fastapi import Request
from nicegui import app, run, ui
from sqlalchemy.exc import SQLAlchemyError

from gui import theme
from webapp import auth, config
from webapp.wardrobe import Wardrobe, latest_garments
from webapp.access import NOUNS
from webapp.access_ui import access_dialog
from webapp.gui_widgets import confirm_delete
from webapp.wardrobe_sharing import WardrobeSharing, access_label
from webapp.wardrobe_actions import share_dialog, source_label
from webapp.favorites import Favorites
from webapp.friends import Friends
from webapp.finished_photos_ui import photos_dialog
from webapp.garment_catalog import draft_items, library_matches, standard_garments, starter_item, studio_snapshot
from webapp.thumbnail_ui import ThumbnailQueue


# Shared with me and Explore also list fabrics and measurement profiles.
KIND_LABELS = dict(fabric='Fabric', body='Measurements')


@ui.page('/', title='SewEasy — Your wardrobe')
def home_page(request: Request):
    user = auth.current_user(request)
    storage = app.storage.user
    store = Wardrobe(user['email'] if user else None, storage)
    sharing = WardrobeSharing(store)
    favorites = Favorites(store)
    previews = ThumbnailQueue(store)
    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    ui.colors(primary='#447cad')
    current = storage.get('pending_design') or {}
    current_items = draft_items(current)
    standards = standard_garments()
    if store.email:
        from webapp.base_garments import list_bases
        standards = [dict(b, standard=b.get('standard') or 'custom-base') for b in list_bases(store.email)]
    initial_tab = request.query_params.get('tab', 'garments')
    state = {'tab': initial_tab if initial_tab in ('garments', 'outfits', 'shared', 'favorites', 'explore') else 'garments',
             'query': '', 'create': 'garment', 'access': {}, 'favorite_keys': set(), 'explore_page': 0}
    pending_favorites = set()

    def open_items(items, name='Untitled outfit', outfit_revision_id=None, editor_mode='garment', outfit_updated_at=None):
        storage['pending_design'] = studio_snapshot(items, name, storage.get('pending_design'),
            outfit_revision_id=outfit_revision_id, editor_mode=editor_mode, outfit_updated_at=outfit_updated_at)
        storage.pop('outfit_edit_return', None)
        ui.navigate.to('/studio')

    def open_saved(kind, item_id):
        item = next((x for x in store.read()[kind] if x['id'] == item_id), None)
        if item is None:
            ui.notify('This saved item is no longer available.', type='warning')
            library.refresh()
            return
        open_items(item['garments'] if kind == 'outfits' else [item], item['name'], item.get('revision_id'),
                   'outfit' if kind == 'outfits' else 'garment', item.get('updated_at'))

    async def delete_item(kind, item_id, name, share_id=None):
        """Your own item from its card, or one you administer by its share ID."""
        if not await confirm_delete(f'Delete the {NOUNS[kind]} “{name}”? '
                                    + ('It is deleted for everyone with access. ' if share_id else '')
                                    + 'Copies others saved remain theirs.'):
            return
        try:
            if share_id:
                await run.io_bound(sharing.delete, share_id)
            else:
                await run.io_bound(store.delete_item, kind, item_id)
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return
        ui.notify(f'Deleted {name}', type='positive')
        library.refresh()

    def item_actions(kind, item):
        with ui.button(icon='more_horiz').props('flat round dense').classes('se-library-actions') as more:
            more._props['aria-label'] = f'{item["name"]} actions'
            with ui.menu():
                ui.menu_item('Privacy & sharing', lambda: share_dialog(store, kind, item, library.refresh))
                ui.menu_item('Made it — add photos', lambda: photos_dialog(store, kind, item))
                ui.menu_item('Save a copy', lambda: show_copy(kind, item))
                ui.menu_item('Delete', lambda: delete_item(kind, item['id'], item['name']))

    def shared_actions(item):
        """What the viewer's role allows on someone else's item."""
        name = item['snapshot'].get('name', '')
        admin = item['role'] in ('owner', 'admin')
        if not admin and not item['is_member']:
            return
        with ui.button(icon='more_horiz').props('flat round dense').classes('se-library-actions') as more:
            more._props['aria-label'] = f'{name} actions'
            with ui.menu():
                if admin:
                    ui.menu_item('Privacy & sharing', lambda: access_dialog(
                        sharing, item['id'], library.refresh, library.refresh))
                    ui.menu_item('Delete', lambda: delete_item(item['kind'], item['revision_id'], name, item['id']))
                if item['is_member']:
                    def leave():
                        try:
                            sharing.leave(item['id'])
                        except ValueError as error:
                            ui.notify(str(error), type='warning')
                        library.refresh()
                    ui.menu_item('Remove from my list', leave)

    def favorite_button(kind, item_id, name):
        key = f'{kind}:{item_id}'

        def update():
            selected = key in state['favorite_keys']
            button.props(f'icon={"favorite" if selected else "favorite_border"} aria-pressed={str(selected).lower()}')
            button.classes(add='is-favorite' if selected else '', remove='' if selected else 'is-favorite')
            button._props['aria-label'] = f'{"Remove" if selected else "Add"} {name} {"from" if selected else "to"} favorites'
            button.update()

        async def toggle():
            if key in pending_favorites:
                return
            if not store.email:
                ui.notify('Sign in to save favorites.', type='info')
                return
            selected = key in state['favorite_keys']
            pending_favorites.add(key)
            (state['favorite_keys'].discard if selected else state['favorite_keys'].add)(key)
            update()
            state['favorite_count'].set_text(str(len(state['favorite_keys'])))
            try:
                await run.io_bound(favorites.set, kind, item_id, not selected)
            except (ValueError, SQLAlchemyError) as error:
                (state['favorite_keys'].add if selected else state['favorite_keys'].discard)(key)
                ui.notify(str(error) if isinstance(error, ValueError) else 'Could not save favorite. Please try again.', type='warning')
            finally:
                pending_favorites.discard(key)
                update()
                state['favorite_count'].set_text(str(len(state['favorite_keys'])))
                if state['tab'] == 'favorites':
                    state['refresh_results']()

        button = ui.button(on_click=toggle, color=None).props('flat round dense :ripple=false').classes('se-favorite')
        update()

    def access_status(kind, item):
        access = state['access'].get(f'{kind}:{item["id"]}', {})
        mode = access.get('visibility', 'private')
        icon = {'private': 'lock_outline', 'friends': 'people_outline', 'link': 'link', 'public': 'public'}[mode]
        return icon, access_label(mode, access.get('invited', False))

    def caption(item, detail=None):
        with ui.column().classes('se-library-caption'):
            title = ui.label(item['name']).classes('se-library-name')
            if detail:
                ui.label(detail).classes('se-home-muted')
            if source_label(item):
                title.tooltip(source_label(item))

    def illustrations(items, classes='', status=None, **options):
        with ui.element('div').classes('se-home-flats ' + classes):
            previews.visual(items, **options)
            if status:
                icon, label = status
                indicator = ui.icon(icon).classes('se-library-status').props('role=img aria-hidden=false')
                indicator._props['aria-label'] = label
                indicator.tooltip(label)

    def standard_cards(create=False):
        with ui.element('div').classes('se-library-grid'):
            for item in standards:
                garment_card(item, create=create)

    def garment_card(item, create=False):
        standard = item.get('standard')
        with ui.element('div').classes('se-library-entry' + ('' if standard else ' is-owned')):
            with ui.button(on_click=lambda: open_items([item], editor_mode=state['create'] if create else 'garment') if standard
                           else open_saved('garments', item['id'])) \
                    .props('flat no-caps').classes('se-library-card') as card:
                card._props['aria-label'] = f'{"Customize" if standard else "Open garment"} {item["name"]}'
                illustrations([item], 'se-library-art', status=('design_services', 'Your base garment') if standard == 'custom-base' else
                        ('checkroom', 'Standard garment') if standard else access_status('garment', item))
                caption(item)
            if not standard:
                item_actions('garment', item)
                favorite_button('garment', item['id'], item['name'])

    def outfit_card(item):
        with ui.element('div').classes('se-library-entry is-owned'):
            with ui.button(on_click=lambda: open_saved('outfits', item['id'])).props('flat no-caps').classes('se-library-card') as card:
                card._props['aria-label'] = f'Open outfit {item["name"]}'
                illustrations(item['garments'], 'se-library-art', outfit_id=item['revision_id'], status=access_status('outfit', item))
                count = len(item['garments'])
                caption(item, f'{count} garment' + ('s' if count != 1 else ''))
            item_actions('outfit', item)
            favorite_button('outfit', item['id'], item['name'])

    def material_art(item, status):
        """Fabrics and measurements have no garment drawing: a swatch colour or an icon."""
        color = item['snapshot'].get('display_color') or ''
        with ui.element('div').classes('se-home-flats se-library-art se-library-material'):
            if item['kind'] == 'fabric' and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                ui.element('div').classes('se-library-swatch').style(f'background-color:{color}')
            else:
                ui.icon('texture' if item['kind'] == 'fabric' else 'accessibility_new').classes('se-library-kind')
            icon, label = status
            indicator = ui.icon(icon).classes('se-library-status').props('role=img aria-hidden=false')
            indicator._props['aria-label'] = label
            indicator.tooltip(label)

    def shared_card(item):
        snapshot = item['snapshot']
        wardrobe_item = item['kind'] in ('garment', 'outfit')
        has_actions = not item['is_owner'] and (item.get('role') in ('owner', 'admin') or item.get('is_member'))
        with ui.element('div').classes('se-library-entry' + (' is-owned' if has_actions else '')):
            with ui.button(on_click=lambda: ui.navigate.to(f'/shared/{item["id"]}')).props('flat no-caps').classes('se-library-card') as card:
                card._props['aria-label'] = f'View shared {NOUNS[item["kind"]]} {snapshot["name"]}'
                mode = item.get('visibility', 'private')
                status = ({'private': 'lock_outline', 'friends': 'people_outline', 'link': 'link', 'public': 'public'}[mode],
                          access_label(mode, mode == 'private' and not item['is_owner']))
                if wardrobe_item:
                    illustrations(snapshot['garments'] if item['kind'] == 'outfit' else [snapshot],
                                  'se-library-art', image=item.get('thumbnail'), status=status)
                else:
                    material_art(item, status)
                detail = item['owner_name'] + (' · Admin' if item.get('role') == 'admin' else '')
                caption(snapshot, detail if wardrobe_item else f'{KIND_LABELS[item["kind"]]} · {detail}')
            if wardrobe_item:
                favorite_button(item['kind'] if item['is_owner'] else 'share',
                                item['revision_id'] if item['is_owner'] else item['id'], snapshot['name'])
            if not item['is_owner']:
                shared_actions(item)

    with ui.dialog() as new_dialog, ui.card().classes('se-new-outfit-dialog'):
        with ui.row().classes('w-full items-center justify-between'):
            new_title = ui.label('Choose a garment').classes('se-home-dialog-title')
            ui.button(icon='close', on_click=new_dialog.close).props('flat round dense aria-label="Close new outfit"')
        new_hint = ui.label('Start with a standard garment, then make it your own.').classes('se-home-muted')
        standard_cards(create=True)
        saved = latest_garments(store.read())
        if saved:
            ui.separator()
            chosen = ui.select({g['id']: g['name'] for g in reversed(saved)},
                               label='Or start from a saved garment', with_input=True).props('outlined dense').classes('w-full')
            def use_saved():
                item = next((g for g in store.read()['garments'] if g['id'] == chosen.value), None)
                if item:
                    if state['create'] == 'garment':
                        new_dialog.close()
                        show_copy('garment', item)
                    else:
                        open_items([item], editor_mode='outfit')
            ui.button('Use garment', on_click=use_saved).props('unelevated') \
                .bind_enabled_from(chosen, 'value', backward=bool).classes('self-end')

    def show_new(mode):
        state['create'] = mode
        new_title.set_text('Choose the first garment' if mode == 'outfit' else 'Choose a garment')
        new_hint.set_text('Add more pieces in the outfit editor.' if mode == 'outfit' else
                          'Start with a standard garment, then make it your own.')
        new_dialog.open()

    copy_source = {}
    with ui.dialog() as copy_dialog, ui.card().classes('w-96 max-w-full gap-3'):
        ui.label('Save a copy').classes('text-lg font-semibold')
        copy_input = ui.input('Name').props('outlined dense autofocus').classes('w-full')
        def save_copy():
            kind, item = copy_source['kind'], copy_source['item']
            try:
                original = store.revision(kind, item['id'])
                result = store.import_fork(kind, original, dict(kind=kind, name=original['name'], revision_id=original['id']), copy_input.value)
                image = store.read().get('thumbnails', {}).get(f'{kind}:{item["id"]}')
                if image:
                    store.save_thumbnail(kind, result['id'], image)
            except ValueError as error:
                ui.notify(str(error), type='warning')
                return
            open_items(result['garments'] if kind == 'outfit' else [result], result['name'],
                       result.get('revision_id'), kind, result.get('updated_at'))
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=copy_dialog.close).props('flat')
            ui.button('Save a copy', on_click=save_copy).props('unelevated')

    def show_copy(kind, item):
        copy_source.update(kind=kind, item=item)
        copy_input.set_value(store.suggested_copy_name(kind, item['name']))
        copy_dialog.open()

    @ui.refreshable
    def library():
        data = store.read()
        data['garments'] = latest_garments(data)
        data['shared'] = sharing.shared_with_me()
        state['access'] = sharing.owner_access()
        state['favorite_keys'] = favorites.keys()
        with ui.element('div').classes('se-library-toolbar'):
            def switch(event):
                if event.value != state['tab']:
                    state['tab'] = event.value
                    state['explore_page'] = 0
                    results.refresh()
            with ui.tabs(value=state['tab'], on_change=switch).props(
                    'no-caps dense align=left aria-label="Your library"').classes('se-library-tabs'):
                for key, title in (('garments', 'Garments'), ('outfits', 'Outfits'), ('favorites', 'Favorites'),
                                   ('shared', 'Shared with me'), ('explore', 'Explore')):
                    with ui.tab(key, label='').classes('se-library-tab'):
                        with ui.row(wrap=False).classes('items-center gap-0'):
                            ui.label(title)
                            if key == 'favorites':
                                state['favorite_count'] = ui.label(str(len(state['favorite_keys']))).classes('se-library-count')
                            elif key in data:
                                ui.label(str(len(data[key]) + (len(standards) if key == 'garments' else 0))).classes('se-library-count')
            def search(event):
                state['query'] = event.value
                state['explore_page'] = 0
                results.refresh()
            ui.input(placeholder='Search designs', value=state['query'], on_change=search).props(
                'outlined dense clearable debounce=250 aria-label="Search designs"').classes('se-library-search') \
                .add_slot('prepend', '<q-icon name="search"/>')

        @ui.refreshable
        def results():
            kind = state['tab']
            more = False
            if kind == 'favorites':
                data['favorites'] = favorites.list()
            if kind == 'explore':
                entries = sharing.discover(state['query'], offset=state['explore_page'] * 24, limit=25)
                more, entries = len(entries) > 24, entries[:24]
            elif kind in ('shared', 'favorites'):
                entries = [s for s in data[kind] if not state['query'] or
                           state['query'].casefold() in (s['snapshot']['name'] + ' ' + s.get('owner_name', '')).casefold()]
            else:
                entries = library_matches(data[kind], state['query'])
            if kind == 'garments':
                entries += list(reversed(library_matches(standards, state['query'])))
            with ui.element('section').classes('se-library-results').props('aria-label="Library items" aria-live=polite'):
                if entries:
                    with ui.element('div').classes('se-library-grid'):
                        for item in entries:
                            if kind in ('shared', 'explore') or (kind == 'favorites' and item['favorite_kind'] == 'share'):
                                shared_card(item)
                                continue
                            if kind == 'favorites':
                                (garment_card if item['kind'] == 'garment' else outfit_card)(item['snapshot'])
                                continue
                            if kind == 'garments':
                                garment_card(item)
                                continue
                            outfit_card(item)
                elif state['query']:
                    with ui.column().classes('se-library-empty'):
                        ui.icon('search').classes('se-empty-icon')
                        ui.label('No matches in ' + kind).classes('se-empty-title')
                        ui.label('Try a garment or outfit name.').classes('se-home-muted')
                elif kind == 'shared':
                    with ui.column().classes('se-library-empty'):
                        ui.icon('people_outline').classes('se-empty-icon')
                        ui.label('Nothing shared with you yet' if user else 'Shared items live here').classes('se-empty-title')
                        ui.label('Garments, outfits, fabrics and measurements shared by friends or by invitation appear here.' if user else
                                 'Sign in with your invited email to see private shares.').classes('se-home-muted')
                        if user:
                            ui.link('Find friends', '/account?section=friends')
                elif kind in ('favorites', 'explore'):
                    with ui.column().classes('se-library-empty'):
                        ui.icon('favorite_border' if kind == 'favorites' else 'public').classes('se-empty-icon')
                        ui.label('Keep your favorites here' if kind == 'favorites' else 'Discover what others are making').classes('se-empty-title')
                        ui.label(('Tap the heart on a garment or outfit to find it here.' if user else 'Sign in to save favorites across devices.')
                                 if kind == 'favorites' else 'Public garments, outfits, fabrics and measurements appear here. '
                                 'Publish one from Privacy & sharing.').classes('se-home-muted')
                else:
                    with ui.element('div').classes('se-library-empty se-library-first'):
                        ui.icon('checkroom').classes('se-empty-icon')
                        with ui.column().classes('gap-1'):
                            ui.label('No saved outfits yet').classes('se-empty-title')
                            ui.label('Start with New outfit above, then save your combination in the studio.') \
                                .classes('se-home-muted')
                if kind == 'explore' and (state['explore_page'] or more):
                    def page(delta):
                        state['explore_page'] += delta
                        results.refresh()
                    with ui.row().classes('w-full justify-center items-center gap-3 mt-5'):
                        ui.button('Previous', on_click=lambda: page(-1)).props('flat no-caps').set_enabled(state['explore_page'] > 0)
                        ui.label(f'Page {state["explore_page"] + 1}').classes('se-home-muted')
                        ui.button('Next', on_click=lambda: page(1)).props('flat no-caps').set_enabled(more)
        state['refresh_results'] = results.refresh
        results()

    with ui.element('main').classes('se-home'):
        with ui.element('header').classes('se-home-header'):
            ui.link('SewEasy', '/').classes('se-wordmark se-home-logo').props('aria-label="SewEasy home"')
            ui.label('Your wardrobe').classes('se-home-location')
            ui.space()
            ui.button('Measurements', icon='straighten', on_click=lambda: ui.navigate.to(
                '/account?section=measurements' if user else '/studio?measurements=1')).props('flat').classes('se-home-measurements')
            if user:
                # The library lives in the account; Home is where a project starts.
                ui.button('Fabrics', icon='texture', on_click=lambda: ui.navigate.to('/account?section=fabrics')).props(
                    'flat aria-label="Fabric library"').classes('se-home-fabrics')
                incoming = len(Friends(store.email).list()['incoming'])
                with ui.button('Friends', icon='people_outline', on_click=lambda: ui.navigate.to('/account?section=friends')).props('flat'):
                    if incoming:
                        ui.badge(str(incoming), color='primary').props('floating')
                ui.button(user.get('name') or 'Account', icon='account_circle', on_click=lambda: ui.navigate.to('/account')).props('flat')
            else:
                def sign_in():
                    if config.google_configured():
                        ui.navigate.to('/auth/login')
                    else:
                        ui.notify('Sign-in is not configured on this installation. You can save outfits in this browser.', type='info')
                ui.button('Sign in', on_click=sign_in).props('flat').classes('se-home-signin')

        with ui.element('div').classes('se-home-content'):
            with ui.element('div').classes('se-home-heading'):
                with ui.column().classes('gap-1'):
                    ui.label('Your wardrobe').classes('se-home-title').props('role=heading aria-level=1')
                    ui.label('Customize a garment or combine pieces into an outfit.').classes('se-home-subtitle')
                with ui.row().classes('se-home-create-actions gap-2'):
                    ui.button('New garment', icon='add', on_click=lambda: show_new('garment')).props('unelevated').classes('se-home-create')
                    ui.button('New outfit', icon='add', on_click=lambda: show_new('outfit')).props('outline').classes('se-home-create')

            if current_items:
                with ui.element('section').classes('se-home-resume').props('aria-label="Current draft"'):
                    illustrations(current_items, 'se-resume-art', outfit_id=current.get('outfit_revision_id'))
                    with ui.column().classes('se-resume-copy'):
                        ui.label('Outfit draft' if current.get('editor_mode') == 'outfit' else 'Garment draft').classes('se-home-muted')
                        ui.label((current.get('outfit_name') or 'Untitled outfit') if current.get('editor_mode') == 'outfit'
                                 else current_items[0]['name']).classes('se-resume-title')
                    ui.button('Continue editing', icon='edit', on_click=lambda: ui.navigate.to('/studio')).props('outline')

            library()

            with ui.element('footer').classes('se-home-footer'):
                ui.link('Built on GarmentCode', 'https://github.com/maria-korosteleva/GarmentCode', new_tab=True)
    previews.enqueue_library(standards=True)
