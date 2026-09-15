"""Wardrobe home with cached renders and a background queue for missing thumbnails."""
from pathlib import Path

from fastapi import Request
from nicegui import app, ui

from gui import theme
from webapp import auth, config
from webapp.wardrobe import Wardrobe
from webapp.garment_catalog import draft_items, library_matches, standard_garments, starter_item, studio_snapshot
from webapp.thumbnail_ui import ThumbnailQueue


@ui.page('/', title='SewEasy — Your wardrobe')
def home_page(request: Request):
    user = auth.current_user(request)
    storage = app.storage.user
    store = Wardrobe(user['email'] if user else None, storage)
    previews = ThumbnailQueue(store)
    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    ui.colors(primary='#447cad')
    current = storage.get('pending_design') or {}
    current_items = draft_items(current)
    standards = standard_garments()
    state = {'tab': 'garments', 'query': ''}

    def open_items(items, name='Untitled outfit'):
        storage['pending_design'] = studio_snapshot(items, name, storage.get('pending_design'))
        ui.navigate.to('/studio')

    def open_saved(kind, item_id):
        item = next((x for x in store.read()[kind] if x['id'] == item_id), None)
        if item is None:
            ui.notify('This saved item is no longer available.', type='warning')
            library.refresh()
            return
        open_items(item['garments'] if kind == 'outfits' else [item], item['name'])

    def illustrations(items, classes=''):
        with ui.element('div').classes('se-home-flats ' + classes):
            previews.visual(items)

    def standard_cards():
        with ui.element('div').classes('se-library-grid'):
            for item in standards:
                garment_card(item)

    def garment_card(item):
        standard = item.get('standard')
        with ui.button(on_click=lambda: open_items([starter_item(standard)]) if standard
                       else open_saved('garments', item['id'])) \
                .props('flat no-caps').classes('se-library-card') as card:
            card._props['aria-label'] = f'{"Customize" if standard else "Open garment"} {item["name"]}'
            illustrations([item], 'se-library-art')
            with ui.column().classes('se-library-caption'):
                ui.label(item['name']).classes('se-library-name')
                ui.label('Standard garment' if standard else f'Saved version {item["version"]}').classes('se-home-muted')

    with ui.dialog() as new_dialog, ui.card().classes('se-new-outfit-dialog'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Choose the first garment').classes('se-home-dialog-title')
            ui.button(icon='close', on_click=new_dialog.close).props('flat round dense aria-label="Close new outfit"')
        ui.label('Add more pieces from the outfit sidebar in the studio.').classes('se-home-muted')
        standard_cards()
        saved = store.read()['garments']
        if saved:
            ui.separator()
            chosen = ui.select({g['id']: f'{g["name"]} (v{g["version"]})' for g in reversed(saved)},
                               label='Or use a saved garment', with_input=True).props('outlined dense').classes('w-full')
            def use_saved():
                item = next((g for g in store.read()['garments'] if g['id'] == chosen.value), None)
                if item:
                    open_items([item])
            ui.button('Use garment', on_click=use_saved).props('unelevated') \
                .bind_enabled_from(chosen, 'value', backward=bool).classes('self-end')

    @ui.refreshable
    def library():
        data = store.read()
        with ui.element('div').classes('se-library-toolbar'):
            def switch(event):
                if event.value != state['tab']:
                    state['tab'] = event.value
                    results.refresh()
            with ui.tabs(value=state['tab'], on_change=switch).props(
                    'no-caps dense align=left aria-label="Your library"').classes('se-library-tabs'):
                for key, title in (('garments', 'Garments'), ('outfits', 'Outfits')):
                    with ui.tab(key, label='').classes('se-library-tab'):
                        with ui.row(wrap=False).classes('items-center gap-0'):
                            ui.label(title)
                            ui.label(str(len(data[key]) + (len(standards) if key == 'garments' else 0))).classes('se-library-count')
            def search(event):
                state['query'] = event.value
                results.refresh()
            ui.input(placeholder='Search your wardrobe', value=state['query'], on_change=search).props(
                'outlined dense clearable debounce=150 aria-label="Search your wardrobe"').classes('se-library-search') \
                .add_slot('prepend', '<q-icon name="search"/>')

        @ui.refreshable
        def results():
            kind = state['tab']
            entries = library_matches(data[kind], state['query'])
            if kind == 'garments':
                entries += list(reversed(library_matches(standards, state['query'])))
            with ui.element('section').classes('se-library-results').props('aria-label="Library items" aria-live=polite'):
                if entries:
                    with ui.element('div').classes('se-library-grid'):
                        for item in entries:
                            if kind == 'garments':
                                garment_card(item)
                                continue
                            with ui.button(on_click=lambda _, k=kind, item_id=item['id']: open_saved(k, item_id)) \
                                    .props('flat no-caps').classes('se-library-card') as card:
                                card._props['aria-label'] = f'Open outfit {item["name"]}'
                                illustrations(item['garments'], 'se-library-art')
                                with ui.column().classes('se-library-caption'):
                                    ui.label(item['name']).classes('se-library-name')
                                    count = len(item['garments'])
                                    ui.label(f'{count} garment' + ('s' if count != 1 else '')).classes('se-home-muted')
                elif state['query']:
                    with ui.column().classes('se-library-empty'):
                        ui.icon('search').classes('se-empty-icon')
                        ui.label('No matches in ' + kind).classes('se-empty-title')
                        ui.label('Try a garment or outfit name.').classes('se-home-muted')
                else:
                    with ui.element('div').classes('se-library-empty se-library-first'):
                        ui.icon('checkroom').classes('se-empty-icon')
                        with ui.column().classes('gap-1'):
                            ui.label('No saved outfits yet').classes('se-empty-title')
                            ui.label('Start with New outfit above, then save your combination in the studio.') \
                                .classes('se-home-muted')
        results()

    with ui.element('main').classes('se-home'):
        with ui.element('header').classes('se-home-header'):
            ui.link('SewEasy', '/').classes('se-wordmark se-home-logo').props('aria-label="SewEasy home"')
            ui.label('Your wardrobe').classes('se-home-location')
            ui.space()
            ui.button('Measurements', icon='straighten', on_click=lambda: ui.navigate.to(
                '/account?section=measurements' if user else '/studio?measurements=1')).props('flat').classes('se-home-measurements')
            if user:
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
                ui.button('New outfit', icon='add', on_click=new_dialog.open).props('unelevated').classes('se-home-create')

            if current_items:
                with ui.element('section').classes('se-home-resume').props('aria-label="Current draft"'):
                    illustrations(current_items, 'se-resume-art')
                    with ui.column().classes('se-resume-copy'):
                        ui.label('Current draft').classes('se-home-muted')
                        ui.label(current.get('outfit_name') or 'Untitled outfit').classes('se-resume-title')
                    ui.button('Continue editing', icon='edit', on_click=lambda: ui.navigate.to('/studio')).props('outline')

            library()

            with ui.element('footer').classes('se-home-footer'):
                ui.label('Saved to your account.' if user else 'Your saves stay in this browser on this installation.')
                ui.link('Built on GarmentCode', 'https://github.com/maria-korosteleva/GarmentCode', new_tab=True)
    previews.enqueue_library(standards=True)
