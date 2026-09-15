"""Wardrobe home. Browse saved snapshots without drafting or starting WebGPU."""
from pathlib import Path

from fastapi import Request
from nicegui import app, ui

from gui import theme
from webapp import auth, config
from webapp.wardrobe import Wardrobe
from webapp.garment_catalog import STARTERS, draft_items, library_matches, starter_item, studio_snapshot, thumbnail


@ui.page('/', title='SewEasy — Your wardrobe')
def home_page(request: Request):
    user = auth.current_user(request)
    storage = app.storage.user
    store = Wardrobe(user['email'] if user else None, storage)
    ui.add_head_html(theme.HEAD_HTML)
    ui.add_css(Path(__file__).with_name('home.css').read_text(encoding='utf-8'))
    ui.colors(primary='#447cad')
    current = storage.get('pending_design') or {}
    current_items = draft_items(current)
    state = {'tab': 'outfits', 'query': ''}

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
            for item in items[:3]:
                ui.html(thumbnail(item))
            if len(items) > 3:
                ui.label(f'+{len(items)-3}').classes('se-home-more')

    def starters():
        with ui.element('div').classes('se-starter-grid'):
            for kind, name, description, _ in STARTERS:
                with ui.button(on_click=lambda _, k=kind: open_items([starter_item(k)])) \
                        .props('flat no-caps').classes('se-starter') as button:
                    button._props['aria-label'] = f'Start with {name.lower()}'
                    ui.html(thumbnail(starter_item(kind))).classes('se-starter-art')
                    with ui.column().classes('se-starter-copy'):
                        ui.label(name).classes('se-starter-name')
                        ui.label(description).classes('se-home-muted')
                    ui.icon('add').classes('se-starter-plus')

    with ui.dialog() as new_dialog, ui.card().classes('se-new-outfit-dialog'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Start an outfit').classes('se-home-dialog-title')
            ui.button(icon='close', on_click=new_dialog.close).props('flat round dense aria-label="Close new outfit"')
        ui.label('Choose your first garment. Add more in the studio.').classes('se-home-muted')
        starters()
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
                for key, title in (('outfits', 'Outfits'), ('garments', 'Garments')):
                    with ui.tab(key, label='').classes('se-library-tab'):
                        with ui.row(wrap=False).classes('items-center gap-0'):
                            ui.label(title)
                            ui.label(str(len(data[key]))).classes('se-library-count')
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
            with ui.element('section').classes('se-library-results').props('aria-label="Saved items" aria-live=polite'):
                if entries:
                    with ui.element('div').classes('se-library-grid'):
                        for item in entries:
                            with ui.button(on_click=lambda _, k=kind, item_id=item['id']: open_saved(k, item_id)) \
                                    .props('flat no-caps').classes('se-library-card') as card:
                                card._props['aria-label'] = f'Open {"outfit" if kind == "outfits" else "garment"} {item["name"]}'
                                illustrations(item['garments'] if kind == 'outfits' else [item], 'se-library-art')
                                with ui.column().classes('se-library-caption'):
                                    ui.label(item['name']).classes('se-library-name')
                                    count = len(item['garments']) if kind == 'outfits' else 0
                                    ui.label(f'{count} garment' + ('s' if count != 1 else '') if kind == 'outfits'
                                             else f'Version {item["version"]}').classes('se-home-muted')
                elif state['query']:
                    with ui.column().classes('se-library-empty'):
                        ui.icon('search').classes('se-empty-icon')
                        ui.label('No matches in ' + kind).classes('se-empty-title')
                        ui.label('Try another name or switch between outfits and garments.').classes('se-home-muted')
                else:
                    with ui.element('div').classes('se-library-empty se-library-first'):
                        ui.icon('checkroom' if kind == 'outfits' else 'style').classes('se-empty-icon')
                        with ui.column().classes('gap-1'):
                            ui.label('A place for your ' + kind).classes('se-empty-title')
                            ui.label('Save an outfit in the studio to keep its garments together.' if kind == 'outfits'
                                     else 'Save garment versions in the studio to reuse their colors, fabrics and details.') \
                                .classes('se-home-muted')
                        ui.button('New outfit', icon='add', on_click=new_dialog.open).props('outline')
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
                with ui.column().classes('gap-2'):
                    ui.label('Your wardrobe').classes('se-home-title').props('role=heading aria-level=1')
                    ui.label('Individual pieces. Outfits that are yours.').classes('se-home-subtitle')
                ui.button('New outfit', icon='add', on_click=new_dialog.open).props('unelevated').classes('se-home-create')

            if current_items:
                with ui.element('section').classes('se-home-resume').props('aria-label="Current draft"'):
                    illustrations(current_items, 'se-resume-art')
                    with ui.column().classes('se-resume-copy'):
                        ui.label('Pick up where you left off').classes('se-home-muted')
                        ui.label(current.get('outfit_name') or 'Untitled outfit').classes('se-resume-title')
                        ui.label('Your latest design and fabric settings are ready to continue.').classes('se-resume-description')
                    ui.button('Continue editing', icon='edit', on_click=lambda: ui.navigate.to('/studio')).props('outline')

            library()

            with ui.element('section').classes('se-home-starters').props('aria-label="Starter garments"'):
                with ui.row().classes('se-section-heading'):
                    ui.label('Start with a garment').classes('se-home-section-title').props('role=heading aria-level=2')
                    ui.label('Make the fit, fabric and details your own.').classes('se-home-muted')
                starters()

            with ui.element('footer').classes('se-home-footer'):
                ui.label('Saved to your account.' if user else 'Your saves stay in this browser on this installation.')
                ui.link('Built on GarmentCode', 'https://github.com/maria-korosteleva/GarmentCode', new_tab=True)
