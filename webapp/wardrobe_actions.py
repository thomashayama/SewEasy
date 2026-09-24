"""Small, reusable owner controls for library cards and the studio."""
from nicegui import ui

from webapp.access_ui import access_dialog
from webapp.wardrobe_sharing import WardrobeSharing


def revision_id(kind, item):
    return item['id'] if kind == 'garment' else item['revision_id']


def source_label(item):
    source = item.get('forked_from')
    return f'Copied from {source["name"]}' + (f' by {source["owner_name"]}' if source.get("owner_name") else "") if source else ""


def share_dialog(store, kind, item, on_change=None, on_removed=None, on_done=None):
    """Privacy & sharing for a garment or outfit you own or administer."""
    sharing = WardrobeSharing(store)
    try:
        share_id = sharing.ensure(kind, revision_id(kind, item))
    except ValueError as error:
        ui.notify(str(error), type='warning')
        return
    access_dialog(sharing, share_id, on_change, on_removed, on_done)
