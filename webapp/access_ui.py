"""The Privacy & sharing dialog: one for garments, outfits, fabrics and body profiles."""
from nicegui import ui

from webapp.access import Access, NOUNS, ROLES, VISIBILITY, describe
from webapp.friends import Friends

ROLE_HINT = 'Viewers can view and save a copy. Admins can also edit, share and delete. Only the owner can transfer ownership.'


def item_share_dialog(email, kind, item_id, on_change=None, on_removed=None, on_done=None):
    """Open sharing for a fabric or body profile you own or administer."""
    access = Access(email)
    try:
        share_id = access.ensure(kind, item_id)
    except ValueError as error:
        ui.notify(str(error), type='warning')
        return
    access_dialog(access, share_id, on_change, on_removed, on_done)


def access_dialog(access, share_id, on_change=None, on_removed=None, on_done=None):
    """Owner and admin controls for one item.

    `on_change` runs after each change, `on_removed` when the caller loses
    access, and `on_done` when the dialog closes after any change.
    """
    try:
        first = access.settings(share_id)
    except ValueError as error:
        ui.notify(str(error), type='warning')
        return
    kind = first['kind']
    noun = NOUNS[kind]
    url = f'{str(ui.context.client.request.base_url).rstrip("/")}/shared/{share_id}'
    # A menu closes after invoking its action; keep the dialog outside that
    # transient menu's slot so Quasar does not unmount it with the menu.
    with ui.context.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-4'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            with ui.column().classes('gap-1 min-w-0'):
                ui.label('Privacy & sharing').classes('text-lg font-semibold break-words')
                ui.label(first['name']).classes('font-medium break-words')
                ownership = ui.label('').classes('text-xs text-slate-500')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close sharing"')

        touched = []

        def changed():
            touched.append(True)
            controls.refresh()
            if on_change:
                on_change()

        def attempt(action, *args, done=None):
            try:
                action(*args)
            except ValueError as error:
                ui.notify(str(error), type='warning')
                controls.refresh()
                return False
            if done:
                ui.notify(done, type='positive')
            changed()
            return True

        def lost_access():
            dialog.close()
            if on_removed:
                on_removed()

        def remove(email):
            if attempt(access.remove_member, share_id, email) and email == access.email:
                lost_access()

        def confirm_transfer(email):
            with ui.dialog() as confirm, ui.card().classes('w-96 max-w-full gap-3'):
                ui.label('Transfer ownership?').classes('text-lg font-semibold')
                ui.label(f'{email} becomes the owner of “{first["name"]}”. You stay on as an admin, '
                         'and only they can transfer it again.').classes('text-sm break-words')
                with ui.row().classes('w-full justify-end'):
                    ui.button('Cancel', on_click=confirm.close).props('flat no-caps')
                    ui.button('Transfer', on_click=lambda: confirm.submit(True)).props('unelevated no-caps')
            async def ask():
                confirm.open()
                if await confirm is True:
                    attempt(access.transfer, share_id, email, done=f'{email} now owns this {noun}.')
                confirm.delete()
            return ask()

        @ui.refreshable
        def controls():
            try:
                settings = access.settings(share_id)
            except ValueError:
                # Removed, demoted or deleted meanwhile, perhaps from another tab.
                lost_access()
                return
            owner, signed_up = settings['role'] == 'owner', settings['account_owned']
            ownership.set_text(f'You own this {noun}' if owner else
                               f'Owned by {settings["owner_name"]} · You are an admin')
            choices = {key: value[0] for key, value in VISIBILITY.items() if signed_up or key in ('private', 'link')}
            ui.select(choices, value=settings['visibility'], label=f'Who can open this {noun}',
                      on_change=lambda e: attempt(access.set_visibility, share_id, e.value)) \
                .props('outlined dense').classes('w-full')
            ui.label(describe(settings['visibility'], kind)).classes('text-sm')
            if kind in ('garment', 'outfit'):
                ui.label('Finished photos use the same access settings.').classes('se-param-label text-xs')
            if not signed_up:
                ui.label('Sign in to share with friends, publish in Explore or add admins.').classes('se-param-label text-xs')
            with ui.row().classes('w-full items-center gap-2 no-wrap'):
                ui.input('Share link', value=url).props('outlined dense readonly').classes('flex-1 min-w-0')
                ui.button(icon='content_copy', on_click=lambda: ui.clipboard.write(url)).props(
                    'flat round aria-label="Copy share link"').tooltip('Copy link')
            ui.link('Preview shared item', f'/shared/{share_id}').classes('text-xs')

            ui.separator()
            ui.label('People with access').classes('font-medium')
            with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                ui.label(settings['owner_name'] + (' (you)' if owner else '')).classes('text-sm break-all')
                ui.label('Owner').classes('text-sm text-slate-500 pr-2')
            for member in settings['members']:
                email = member['email']
                with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                    ui.label(email + (' (you)' if email == access.email else '')).classes('text-sm break-all min-w-0')
                    with ui.row().classes('items-center no-wrap gap-1 flex-none'):
                        if signed_up:
                            role = ui.select({key: value[0] for key, value in ROLES.items()}, value=member['role'],
                                             on_change=lambda e, m=email: attempt(access.set_role, share_id, m, e.value)) \
                                .props('outlined dense options-dense').classes('w-28')
                            role._props['aria-label'] = f'Role for {email}'
                        else:
                            ui.label('Viewer').classes('text-sm text-slate-500')
                        verb = 'Leave' if email == access.email else f'Remove access for {email}'
                        ui.button(icon='close', on_click=lambda _, m=email: remove(m)).props('flat round dense') \
                            .tooltip(verb)._props.update({'aria-label': verb})
            ui.label(ROLE_HINT).classes('se-param-label text-xs')

            ui.separator()
            with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                ui.label('Add people').classes('font-medium')
                # A guest's item can only have viewers: admins edit it in an account library.
                new_role = ui.select({key: f'Add as {value[0].lower()}' for key, value in ROLES.items()},
                                     value='viewer').props('outlined dense options-dense').classes('w-40')
                new_role.set_visibility(signed_up)
            friends = [p for p in Friends(access.email).list()['friends']
                       if p['email'] not in settings['recipients']] if access.email else []
            if friends:
                with ui.row().classes('w-full items-center no-wrap gap-2'):
                    friend = ui.select({p['email']: p['name'] for p in friends}, label='Choose a friend',
                                       with_input=True).props('outlined dense').classes('grow min-w-0')

                    def add_friend():
                        if friend.value:
                            attempt(access.add_member, share_id, friend.value, new_role.value)
                    ui.button('Add', on_click=add_friend).props('outline no-caps') \
                        .bind_enabled_from(friend, 'value', backward=bool)
            with ui.row().classes('w-full items-start no-wrap gap-2'):
                address = ui.input('Email address').props('outlined dense type=email').classes('flex-1 min-w-0')

                def invite():
                    attempt(access.add_member, share_id, address.value, new_role.value)
                ui.button('Invite', on_click=invite).props('unelevated no-caps')
                address.on('keydown.enter', invite)
            ui.label('They find it in Shared with me after signing in with this address. No email is sent.') \
                .classes('se-param-label text-xs')

            if owner and signed_up and settings['members']:
                ui.separator()
                with ui.expansion('Transfer ownership', icon='swap_horiz').classes('w-full'):
                    ui.label('Choose someone who already has access. You stay on as an admin.').classes('text-sm')
                    with ui.row().classes('w-full items-center no-wrap gap-2'):
                        target = ui.select({m['email']: m['email'] for m in settings['members']},
                                           label='New owner').props('outlined dense').classes('grow min-w-0')
                        ui.button('Transfer', on_click=lambda: confirm_transfer(target.value)).props('outline no-caps') \
                            .bind_enabled_from(target, 'value', backward=bool)

            if settings['visibility'] != 'private' or any(m['role'] == 'viewer' for m in settings['members']):
                ui.separator()
                ui.button('Make private', icon='lock_outline',
                          on_click=lambda: attempt(access.stop_sharing, share_id,
                                                   done=f'This {noun} is private again.')).props('flat no-caps')
                ui.label('Turns off link, friend and public access and removes every viewer. Admins keep access. '
                         'Copies already saved by others remain theirs.').classes('se-param-label text-xs')
        controls()
    def closed():
        dialog.delete()
        if touched and on_done:
            on_done()
    dialog.on('hide', closed)
    dialog.open()
