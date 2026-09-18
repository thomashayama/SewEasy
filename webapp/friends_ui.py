"""Compact friend management, also reachable directly from the wardrobe."""
from nicegui import ui
from webapp.friends import Friends


def friends_panel(email):
    service = Friends(email)
    with ui.column().classes('w-full gap-2'):
        ui.label('Friends').classes('se-section-label text-2xl')
        ui.label('Share designs with people you know. A request needs their acceptance.').classes('se-param-label')
    with ui.row().classes('w-full items-start no-wrap gap-2'):
        address = ui.input('Friend’s email').props('outlined dense type=email maxlength=254').classes('grow min-w-0')
        def request():
            try:
                service.request(address.value)
                address.set_value('')
                listing.refresh()
                ui.notify('Friend request sent. They can accept it in Friends.', type='positive')
            except ValueError as error:
                ui.notify(str(error), type='warning')
        ui.button('Add friend', icon='person_add', on_click=request).props('unelevated no-caps').classes('shrink-0')
        address.on('keydown.enter', request)
    ui.label('Requests appear in SewEasy when they sign in. No email is sent.').classes('se-param-label text-xs')

    def act(method, identity):
        try:
            method(identity)
            listing.refresh()
        except ValueError as error:
            ui.notify(str(error), type='warning')
            listing.refresh()

    @ui.refreshable
    def listing():
        data = service.list()
        for key, title in (('incoming', 'Friend requests'), ('friends', 'Your friends'), ('outgoing', 'Sent requests')):
            if key != 'friends' and not data[key]:
                continue
            with ui.column().classes('w-full gap-0'):
                ui.label(f'{title} ({len(data[key])})').classes('font-semibold mt-4 mb-2')
                if not data[key]:
                    ui.label('Add a friend above to start sharing designs.').classes('se-param-label py-4')
                for person in data[key]:
                    with ui.row().classes('w-full items-center justify-between gap-3 py-3 border-b border-slate-500/20'):
                        with ui.row(wrap=False).classes('items-center gap-3 min-w-0'):
                            ui.icon('person_outline').classes('text-2xl opacity-60')
                            with ui.column().classes('gap-0 min-w-0'):
                                ui.label(person['name']).classes('font-medium break-all')
                                if person['name'] != person['email']:
                                    ui.label(person['email']).classes('se-param-label text-xs break-all')
                        with ui.row().classes('gap-1 shrink-0'):
                            if key == 'incoming':
                                ui.button('Accept', on_click=lambda _, i=person['id']: act(service.accept, i)).props('unelevated no-caps')
                            label = {'incoming': 'Decline', 'outgoing': 'Cancel request', 'friends': 'Remove friend'}[key]
                            ui.button(label, on_click=lambda _, i=person['id']: act(service.remove, i)).props('flat no-caps size=sm')
        if data['friends']:
            ui.link('View designs shared with you', '/?tab=shared').classes('text-sm mt-4')
            ui.label('Removing a friend ends Friends-only access in both directions. Individual invitations stay in place.').classes('se-param-label text-xs')
    listing()
