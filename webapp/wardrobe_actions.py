"""Small, reusable owner controls for library cards and the studio."""
from nicegui import ui

from webapp.wardrobe_sharing import WardrobeSharing, VISIBILITY
from webapp.friends import Friends


def revision_id(kind, item):
    return item['id'] if kind == 'garment' else item['revision_id']


def source_label(item):
    source = item.get('forked_from')
    return f'Copied from {source["name"]}' + (f' by {source["owner_name"]}' if source.get("owner_name") else "") if source else ""


def share_dialog(store, kind, item, on_change=None):
    sharing = WardrobeSharing(store)
    try:
        share_id = sharing.ensure(kind, revision_id(kind, item))
    except ValueError as error:
        ui.notify(str(error), type='warning')
        return
    base = str(ui.context.client.request.base_url).rstrip('/')
    url = f'{base}/shared/{share_id}'
    # A menu closes after invoking its action; keep the dialog outside that
    # transient menu's slot so Quasar does not unmount it with the menu.
    with ui.context.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-4'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            with ui.column().classes('gap-1 min-w-0'):
                ui.label('Privacy & sharing').classes('text-lg font-semibold break-words')
                ui.label(item['name']).classes('font-medium break-words')
                ui.label(f'You own this {kind}').classes('text-xs text-slate-500')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close sharing"')
        ui.label('People with access can view this item and save their own copy. Your saved changes appear here too.').classes('text-sm')

        @ui.refreshable
        def controls():
            settings = sharing.settings(share_id)
            def changed():
                controls.refresh()
                if on_change:
                    on_change()
            def change_access(event):
                try:
                    sharing.set_visibility(share_id, event.value)
                    changed()
                except ValueError as error:
                    ui.notify(str(error), type='warning')
                    controls.refresh()
            choices = {key: value[0] for key, value in VISIBILITY.items() if store.email or key in ('private', 'link')}
            ui.select(choices, value=settings['visibility'], label='Who can open this design', on_change=change_access) \
                .props('outlined dense').classes('w-full')
            ui.label(VISIBILITY[settings['visibility']][1]).classes('text-sm')
            ui.label('Finished photos use the same access settings.').classes('se-param-label text-xs')
            if not store.email:
                ui.label('Sign in to share with friends or publish in Explore.').classes('se-param-label text-xs')
            with ui.row().classes('w-full items-center gap-2 no-wrap'):
                ui.input('Share link', value=url).props('outlined dense readonly').classes('flex-1 min-w-0')
                ui.button(icon='content_copy', on_click=lambda: ui.clipboard.write(url)).props(
                    'flat round aria-label="Copy share link"').tooltip('Copy link')
            ui.link('Preview shared item', f'/shared/{share_id}').classes('text-xs')
            ui.separator()
            ui.label('Invite people').classes('font-medium')
            friends = [p for p in Friends(store.email).list()['friends'] if p['email'] not in settings['recipients']]
            if friends:
                with ui.row().classes('w-full gap-2 items-center no-wrap'):
                    friend = ui.select({p['email']: p['name'] for p in friends}, label='Choose a friend', with_input=True) \
                        .props('outlined dense').classes('grow min-w-0')
                    def invite_friend():
                        if friend.value:
                            sharing.invite(share_id, friend.value)
                            changed()
                    ui.button('Invite friend', on_click=invite_friend).props('outline no-caps') \
                        .bind_enabled_from(friend, 'value', backward=bool)
            with ui.row().classes('w-full items-start no-wrap gap-2'):
                address = ui.input('Email address').props('outlined dense type=email').classes('flex-1 min-w-0')
                def invite():
                    try:
                        sharing.invite(share_id, address.value)
                    except ValueError as error:
                        ui.notify(str(error), type='warning')
                        return
                    changed()
                ui.button('Invite', on_click=invite).props('unelevated')
                address.on('keydown.enter', invite)
            ui.label('Invitations appear in Shared with me after signing in. No email is sent.').classes('se-param-label text-xs')
            for email in settings['recipients']:
                with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                    ui.label(email).classes('text-sm break-all')
                    def revoke(_, recipient=email):
                        sharing.revoke_invitation(share_id, recipient)
                        changed()
                    ui.button(icon='close', on_click=revoke).props('flat round dense').tooltip(f'Remove access for {email}') \
                        ._props.update({'aria-label': f'Remove access for {email}'})
            if settings['visibility'] != 'private' or settings['recipients']:
                ui.separator()
                def stop():
                    sharing.stop_sharing(share_id)
                    changed()
                    ui.notify('Access removed. This design is now private.', type='positive')
                ui.button('Stop sharing', icon='lock_outline', on_click=stop).props('flat no-caps')
                ui.label('Removes link, public, friend and invitation access. Copies already saved by others remain theirs.').classes('se-param-label text-xs')
        controls()
    dialog.on('hide', dialog.delete)
    dialog.open()
