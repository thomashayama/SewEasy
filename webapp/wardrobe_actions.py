"""Small, reusable owner controls for library cards and the studio."""
from nicegui import ui

from webapp.wardrobe_sharing import WardrobeSharing


def revision_id(kind, item):
    return item['id'] if kind == 'garment' else item['revision_id']


def source_label(item):
    source = item.get('forked_from')
    return f'Forked from {source["name"]} · v{source["version"]} by {source["owner_name"]}' if source else ''


def share_dialog(store, kind, item):
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
                ui.label(f'Share {item["name"]}').classes('text-lg font-semibold break-words')
                ui.label(f'You own this {kind} · Version {item["version"]}').classes('text-xs text-slate-500')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close sharing"')
        ui.label('People with access can view and fork this version. Future saves stay private.').classes('text-sm')

        @ui.refreshable
        def controls():
            settings = sharing.settings(share_id)
            def toggle(event):
                sharing.set_link(share_id, event.value)
                controls.refresh()
            ui.switch('Anyone with the link', value=settings['public_link'], on_change=toggle)
            if not settings['public_link']:
                ui.label('Only you and invited people have access.').classes('text-xs text-slate-500')
            with ui.row().classes('w-full items-center gap-2 no-wrap'):
                ui.input('Version link', value=url).props('outlined dense readonly').classes('flex-1 min-w-0')
                ui.button(icon='content_copy', on_click=lambda: ui.clipboard.write(url)).props(
                    'flat round aria-label="Copy version link"').tooltip('Copy link')
            ui.link('Preview shared version', f'/shared/{share_id}').classes('text-xs')
            ui.separator()
            ui.label('Invite people').classes('font-medium')
            with ui.row().classes('w-full items-start no-wrap gap-2'):
                address = ui.input('Email address').props('outlined dense type=email').classes('flex-1 min-w-0')
                def invite():
                    try:
                        sharing.invite(share_id, address.value)
                    except ValueError as error:
                        ui.notify(str(error), type='warning')
                        return
                    controls.refresh()
                ui.button('Invite', on_click=invite).props('unelevated')
                address.on('keydown.enter', invite)
            ui.label('They’ll find it in Shared with me after signing in. No email is sent.').classes('text-xs text-slate-500')
            for email in settings['recipients']:
                with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                    ui.label(email).classes('text-sm break-all')
                    def revoke(_, recipient=email):
                        sharing.revoke_invitation(share_id, recipient)
                        controls.refresh()
                    ui.button(icon='close', on_click=revoke).props('flat round dense').tooltip(f'Remove access for {email}') \
                        ._props.update({'aria-label': f'Remove access for {email}'})
            if settings['public_link'] and settings['recipients']:
                ui.label('To remove all access, turn off the link and remove invitations.').classes('text-xs text-slate-500')
        controls()
    dialog.on('hide', dialog.delete)
    dialog.open()


def history_dialog(store, kind, item, open_version):
    history = store.history(kind, revision_id(kind, item))
    with ui.context.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-4'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(f'{item["name"]} · Version history').classes('text-lg font-semibold')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close version history"')
        ui.label(f'You own this {kind}. Opening an older version creates an editable draft.').classes('text-sm')
        if source_label(item):
            ui.label(source_label(item)).classes('text-xs text-slate-500')
        with ui.column().classes('w-full gap-1 max-h-96 overflow-auto'):
            for version in history:
                with ui.row().classes('w-full items-center justify-between no-wrap gap-3 py-2'):
                    with ui.column().classes('gap-1 min-w-0'):
                        ui.label(f'Version {version["version"]} · {version["name"]}').classes('font-medium break-words')
                        date = version.get('created_at') or version.get('updated_at') or ''
                        ui.label(date[:16].replace('T', ' ') + ' UTC').classes('text-xs text-slate-500')
                    with ui.row().classes('gap-1 no-wrap'):
                        async def open_item(_, v=version):
                            import inspect
                            result = open_version(v)
                            if inspect.isawaitable(result):
                                await result
                            dialog.close()
                        ui.button('Open', on_click=open_item).props('flat')._props.update(
                            {'aria-label': f'Open version {version["version"]}'})
                        with ui.button(icon='more_horiz').props('flat round dense') as more:
                            more._props['aria-label'] = f'Version {version["version"]} actions'
                            with ui.menu():
                                ui.menu_item('Share this version', lambda _, v=version: share_dialog(store, kind, v))
        ui.label('Saved versions and outfits that use them never change.').classes('text-xs text-slate-500')
    dialog.on('hide', dialog.delete)
    dialog.open()
