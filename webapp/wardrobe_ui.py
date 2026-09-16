"""Parallel garment and outfit editors with named saves and independent copies."""
from copy import deepcopy
import asyncio
from nicegui import app, ui

from webapp.wardrobe import Wardrobe, same_design, same_items
from webapp.wardrobe_actions import share_dialog
from webapp.wardrobe_sharing import WardrobeSharing
from webapp.garment_catalog import garment_title, standard_garments, studio_snapshot
from webapp.thumbnail_ui import ThumbnailQueue


def wardrobe_ui(state):
    store = Wardrobe(state.user['email'] if state.user else None, app.storage.user)
    previews = ThumbnailQueue(store)
    pattern = state.pattern_state
    state._editor_mode = getattr(state, '_editor_mode', 'garment')
    state._outfit_name = getattr(state, '_outfit_name', 'Untitled outfit')
    state._outfit_revision_id = getattr(state, '_outfit_revision_id', None)
    state._outfit_updated_at = getattr(state, '_outfit_updated_at', None)
    state._source_share = getattr(state, '_source_share', None)
    saving = False
    dialog_action = {}

    def current_items():
        pattern.sync_outfit_garment()
        return deepcopy(pattern.outfit_items) if pattern.outfit_items else [dict(
            id='draft', name=garment_title(pattern.design_params),
            params=deepcopy(pattern.design_params), appearance=pattern.garment_appearance())]

    def active_item():
        return current_items()[pattern.active_garment if pattern.outfit_items else 0]

    def owned_item(kind=None):
        kind = kind or state._editor_mode
        identity = active_item()['id'] if kind == 'garment' else state._outfit_revision_id
        return next((g for g in store.read()['garments' if kind == 'garment' else 'outfits'] if g['id'] == identity), None)

    async def apply(items, active=0):
        state.toggle_param_update_events(state.ui_design_refs)
        try:
            pattern.load_outfit(items, active)
            state._design_undo = None
            state.ui_undo_design_btn.set_visibility(False)
            state.update_design_params_ui_state(state.ui_design_refs, pattern.design_params)
            state.set_pattern_selection([], open_panel=False)
            await state.update_pattern_ui_state()
            refresh_studio()
        finally:
            state.toggle_param_update_events(state.ui_design_refs)

    async def edit_item(index):
        if pattern.outfit_items and index != pattern.active_garment:
            await apply(current_items(), index)
        state.ui_design_settings.open()

    async def remove_item(index):
        items = current_items()
        if len(items) > 1 and state._editor_mode == 'outfit':
            items.pop(index)
            await apply(items, min(pattern.active_garment, len(items) - 1))

    def edit_separately(index):
        if not state.stash_pending_design():
            return
        item = current_items()[index]
        # Open the actual owned garment when available; outfit adjustments stay
        # in the return draft and can instead be saved as a named copy.
        item = next((g for g in store.read()['garments'] if g['id'] == item['id']), item)
        app.storage.user['outfit_edit_return'] = dict(snapshot=deepcopy(app.storage.user['pending_design']), index=index)
        app.storage.user['pending_design'] = studio_snapshot([item], previous=app.storage.user['pending_design'],
                                                            editor_mode='garment', source_share=state._source_share)
        ui.navigate.to('/studio')

    def return_to_outfit():
        context = app.storage.user.get('outfit_edit_return')
        if not context:
            return
        snapshot = deepcopy(context['snapshot'])
        index = context['index']
        snapshot['outfit'][index] = active_item()
        snapshot['active_garment'] = index
        snapshot['design'] = deepcopy(snapshot['outfit'][index]['params'])
        snapshot['appearance'] = deepcopy(snapshot['outfit'][index]['appearance'])
        snapshot['fabric'] = snapshot['appearance'].get('fabric_color', pattern.fabric_color)
        app.storage.user['pending_design'] = snapshot
        app.storage.user.pop('outfit_edit_return', None)
        ui.navigate.to('/studio')

    def create_outfit():
        if not state.stash_pending_design():
            return
        app.storage.user['pending_design'] = studio_snapshot(current_items(), previous=app.storage.user['pending_design'], editor_mode='outfit')
        ui.navigate.to('/studio')

    def refresh_studio():
        if state.ui_outfit_list.client.id not in state.ui_outfit_list.client.instances:
            return
        previews.reload_library()
        mode = state._editor_mode
        items = current_items()
        owned = owned_item()
        name = items[0]['name'] if mode == 'garment' else state._outfit_name
        unchanged = owned and (same_design(items[0], owned) if mode == 'garment' else same_items(items, owned['garments']))
        state.ui_outfit_title.set_text(name)
        state.ui_editor_kind.set_text('Garment' if mode == 'garment' else 'Outfit')
        state.ui_wardrobe_heading.set_text('This garment' if mode == 'garment' else 'This outfit')
        state.ui_wardrobe_panel.props(f'aria-label="This {mode}"')
        state.ui_draft_status.set_text('Saved' if unchanged else 'Unsaved changes' if owned else 'Working copy')
        state.ui_save_button.set_text('Save' if owned or (mode == 'outfit' and not state._source_share) else 'Save a copy')
        state.ui_save_options.set_visibility(bool(owned))
        state.ui_add_garment.set_visibility(mode == 'outfit')
        state.ui_detail_save.set_text('Save' if mode == 'garment' and owned else 'Save garment as copy')
        state.ui_save_menu.clear()
        with state.ui_save_menu:
            ui.menu_item('Save a copy', lambda: show_save(copy=True))
            if owned:
                ui.menu_item('Rename', lambda: show_save(rename=True))
                ui.menu_item('Share', lambda: share_dialog(store, mode, owned_item()))
        state.ui_outfit_list.clear()
        with state.ui_outfit_list:
            for index, item in enumerate(items):
                with ui.element('div').classes('se-garment-row' + (' is-active' if index == pattern.active_garment else '')):
                    with ui.button(on_click=lambda _, i=index: edit_item(i)).props(
                            f'flat no-caps aria-label="Edit garment {index + 1}"').classes('se-garment-card'):
                        previews.visual([item], 'se-garment-thumb')
                        with ui.column().classes('se-garment-caption'):
                            ui.label(item['name']).classes('se-garment-name')
                            ui.label('Design & fabric' if mode == 'garment' else 'Adjust in this outfit').classes('se-garment-version')
                    if mode == 'outfit':
                        with ui.button(icon='more_horiz').props(
                                f'flat round dense size=sm aria-label="Garment {index + 1} actions"').classes('se-garment-more'):
                            with ui.menu():
                                ui.menu_item('Adjust in outfit', lambda _, i=index: edit_item(i))
                                ui.menu_item('Edit garment separately', lambda _, i=index: edit_separately(i))
                                async def copy_piece(_, i=index):
                                    if i != pattern.active_garment:
                                        await apply(current_items(), i)
                                    show_save(copy=True, kind='garment')
                                ui.menu_item('Save garment as copy', copy_piece)
                                if len(items) > 1:
                                    ui.menu_item('Remove from outfit', lambda _, i=index: remove_item(i))
            if mode == 'garment':
                ui.button('Design details', icon='tune', on_click=state.ui_design_settings.open).props('flat').classes('se-garment-tool')
                if app.storage.user.get('outfit_edit_return'):
                    ui.button('Back to outfit', icon='arrow_back', on_click=return_to_outfit).props('outline').classes('se-garment-tool')
                else:
                    ui.button('Create outfit with this', icon='checkroom', on_click=create_outfit).props('flat').classes('se-garment-tool')
            else:
                ui.label('Adjustments here are saved with this outfit.').classes('se-editor-note')
        if not state._draft_pending and not state._draft_failed and not state._released:
            state.stash_pending_design()

    async def persist(name, *, kind=None, copy=False):
        nonlocal saving
        if saving:
            return False
        saving = True
        try:
            # Fabric edits run in the drafting executor. Wait for them before
            # snapshotting so a quick Save includes the user's last change.
            async with state._fabric_edit_lock:
                pass
            while state._draft_pending and not state._released:
                await asyncio.sleep(.05)
            if state._released:
                return False
            if state._draft_failed:
                raise ValueError('Fix the pattern settings before saving.')
            kind = kind or state._editor_mode
            original = owned_item(kind)
            copy = copy or original is None
            origin = None
            if copy:
                source = active_item() if kind == 'garment' else dict(name=state._outfit_name, id=state._outfit_revision_id)
                if source.get('id') and source['id'] != 'draft':
                    origin = dict(kind=kind, name=source['name'], revision_id=source['id'])
                if state._source_share:
                    shared = WardrobeSharing(store).get(state._source_share)  # recheck access on save
                    origin = origin or dict(kind=kind, name=source['name'])
                    origin.update(share_id=shared['id'], owner_name=shared['owner_name'])
            parent = original['id'] if original and not copy else None
            if kind == 'garment':
                item = active_item()
                result = store.save_garment(name, item['params'], item['appearance'], parent_id=parent,
                    new=copy, origin=origin, expected_updated_at=item.get('updated_at', '') if parent else None)
                if pattern.outfit_items:
                    pattern.outfit_items[pattern.active_garment] = deepcopy(result)
                else:
                    # Legacy/direct studio drafts use unprefixed panel names.
                    # Rebuild once when they become a saved garment, so fabric
                    # selection and the scene use the same garment namespace.
                    await apply([result])
            else:
                result = store.save_outfit(name, items=current_items(), parent_id=parent, new=copy, origin=origin,
                                           expected_updated_at=state._outfit_updated_at if parent else None)
                pattern.outfit_items = deepcopy(result['garments'])
                state._outfit_name = result['name']
                state._outfit_revision_id = result['id']
                state._outfit_updated_at = result['updated_at']
            if kind == state._editor_mode:
                state._source_share = None
            refresh_studio()
            previews.enqueue_library()
            ui.notify(f'Saved {result["name"]}', type='positive')
            return True
        except ValueError as error:
            ui.notify(str(error), type='warning')
            return False
        finally:
            saving = False

    async def save():
        owned = owned_item()
        if owned:
            await persist(owned['name'])
        else:
            show_save(copy=state._editor_mode == 'garment' or bool(state._source_share))

    with ui.dialog() as save_dialog, ui.card().classes('w-96 max-w-full gap-3'):
        dialog_title = ui.label('Save a copy').classes('text-lg font-semibold')
        name_input = ui.input('Name').props('outlined dense autofocus maxlength=120').classes('w-full')
        dialog_hint = ui.label('An independent item with its own design, colors and fabrics.').classes('text-sm text-slate-500')
        async def confirm_save():
            if await persist(name_input.value, kind=dialog_action['kind'], copy=dialog_action['copy']):
                save_dialog.close()
        name_input.on('keydown.enter', confirm_save)
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=save_dialog.close).props('flat')
            confirm_button = ui.button('Save a copy', on_click=confirm_save).props('unelevated')

    def show_save(copy=False, rename=False, kind=None):
        kind = kind or state._editor_mode
        original = owned_item(kind)
        name = active_item()['name'] if kind == 'garment' else state._outfit_name
        copy = copy or (not original and (kind == 'garment' or bool(state._source_share)))
        dialog_action.update(kind=kind, copy=copy)
        title = 'Save a copy' if copy else 'Rename ' + kind if rename else 'Save ' + kind
        dialog_title.set_text(title)
        confirm_button.set_text('Save a copy' if copy else 'Save')
        name_input.set_label(kind.capitalize() + ' name')
        name_input.set_value(store.suggested_copy_name(kind, name) if copy else '' if name == 'Untitled outfit' else name)
        dialog_hint.set_text('An independent item with its own design, colors and fabrics.' if copy else
                             'Updates this item in your library.' if original else 'Keeps this combination and its fabric settings.')
        save_dialog.open()

    async def detail_save():
        if state._editor_mode == 'garment':
            await save()
        else:
            show_save(copy=True, kind='garment')

    async def add_item(item):
        if state._editor_mode != 'outfit':
            return
        items = current_items()
        items.append(deepcopy(item))
        add_dialog.close()
        await apply(items, len(items) - 1)

    with ui.dialog() as add_dialog, ui.card().classes('w-96 max-w-full gap-4 se-garment-picker'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Add garment').classes('text-lg font-semibold')
            ui.button(icon='close', on_click=add_dialog.close).props('flat round dense aria-label="Close add garment"')
        add_box = ui.column().classes('w-full gap-2 max-h-96 overflow-auto')

    def show_add():
        if state._editor_mode != 'outfit':
            return
        add_box.clear()
        with add_box:
            for heading, records in (('Your garments', store.read()['garments']), ('Standard garments', standard_garments())):
                if records:
                    ui.label(heading).classes('se-param-label')
                    for item in records:
                        ui.button(item['name'], icon='add', on_click=lambda _, g=item: add_item(g)).props('flat').classes('w-full')
        add_dialog.open()

    state.show_outfits = state.go_home
    state.show_save_garment = detail_save
    state.show_add_garment = show_add
    state.save_current = save
    state.rename_current = lambda: show_save(rename=True)
    state.refresh_wardrobe = refresh_studio
    refresh_studio()
