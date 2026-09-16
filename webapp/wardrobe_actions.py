"""Small, reusable owner controls for library cards and the studio."""
from nicegui import ui

from webapp.wardrobe_sharing import WardrobeSharing


def revision_id(kind, item):
    return item['id'] if kind == 'garment' else item['revision_id']


def source_label(item):
    source = item.get('forked_from')
    return f'Copied from {source["name"]}' + (f' by {source["owner_name"]}' if source.get("owner_name") else "") if source else ""


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
                ui.label(f'You own this {kind}').classes('text-xs text-slate-500')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close sharing"')
        ui.label('People with access can view this item and save their own copy. Your saved changes appear here too.').classes('text-sm')

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
                ui.input('Share link', value=url).props('outlined dense readonly').classes('flex-1 min-w-0')
                ui.button(icon='content_copy', on_click=lambda: ui.clipboard.write(url)).props(
                    'flat round aria-label="Copy share link"').tooltip('Copy link')
            ui.link('Preview shared item', f'/shared/{share_id}').classes('text-xs')
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
            ui.label('Theyâ€™ll find it in Shared with me after signing in. No email is sent.').classes('text-xs text-slate-500')
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
