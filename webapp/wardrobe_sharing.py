"""Garments and outfits in the unified access model (webapp/access.py).

Viewers view and save independent copies; admins also save changes to the
original in its owner's library; the owner can also transfer it.
"""
from webapp.access import (Access, NotAllowed, ShareUnavailable, VISIBILITY, WARDROBE, access_label,  # noqa: F401
                           account_of, create, public_snapshot, record, require, role_of)
from webapp.db import SessionLocal
from webapp.models import WardrobeShare
from webapp.thumbnail_cache import thumbnail_key, normalize_image


def _snapshot(item, kind):
    return public_snapshot(item, kind)


class WardrobeSharing(Access):
    """Access for one wardrobe (an account's, or a guest browser's)."""

    def __init__(self, store):
        super().__init__()
        self.store = store

    @property
    def email(self):
        return self.store.email

    @property
    def owner_key(self):
        return self.store.owner_key

    def _accessible(self, db, share_id):
        return self._open(db, share_id)[0]

    def ensure(self, kind, revision_id):
        """Prepare sharing controls for the owner or an admin; a new record stays private."""
        if kind not in WARDROBE:
            return super().ensure(kind, revision_id)
        with SessionLocal() as db:
            existing = record(db, kind, revision_id)
            if existing is not None and existing.owner_key != self.store.owner_key:
                require(role_of(db, existing, self.email, self.owner_key), 'admin')
                return existing.id
        snapshot = _snapshot(self.store.revision(kind, revision_id), kind)
        image = self.store.read().get('thumbnails', {}).get(thumbnail_key(kind, revision_id))
        with SessionLocal() as db:
            row = db.query(WardrobeShare).filter_by(owner_key=self.store.owner_key, kind=kind,
                                                    revision_id=revision_id).first()
            if row:
                if not row.thumbnail and image:
                    row.thumbnail = normalize_image(image)
                    db.commit()
                return row.id
            return create(db, kind, revision_id, self.store.owner_key, snapshot,
                          normalize_image(image) if image else None)

    def fork(self, share_id, name=None):
        # Recheck permission on the action, not just when its page was opened.
        source = self.get(share_id)
        if source['kind'] not in WARDROBE:
            raise ValueError('Only a garment or outfit can be copied into your wardrobe.')
        item = source['snapshot']
        origin = dict(share_id=share_id, kind=source['kind'], revision_id=source['revision_id'],
                      name=item['name'], owner_name=source['owner_name'])
        result = self.store.import_fork(source['kind'], item, origin, name=name)
        if source.get('thumbnail'):
            revision_id = result['revision_id'] if source['kind'] == 'outfit' else result['id']
            self.store.save_thumbnail(source['kind'], revision_id, source['thumbnail'])
        return result

    def _administered(self, share_id, kind):
        """The owner's library, for someone allowed to change the original."""
        from webapp.wardrobe import Wardrobe
        with SessionLocal() as db:
            row, current = self._open(db, share_id, 'admin')
            if row.kind != kind:
                raise ValueError(f'This shared item is not a {kind}.')
            item_id, owner = row.revision_id, account_of(row.owner_key)
        return (self.store if current == 'owner' else Wardrobe(owner)), item_id

    def save_garment(self, share_id, name, params, appearance, expected_updated_at=None):
        """Save an admin's changes to the original garment."""
        store, item_id = self._administered(share_id, 'garment')
        return store.save_garment(name, params, appearance, parent_id=item_id, expected_updated_at=expected_updated_at)

    def save_outfit(self, share_id, name, items, expected_updated_at=None):
        """Save an admin's changes to the original outfit."""
        store, item_id = self._administered(share_id, 'outfit')
        return store.save_outfit(name, items=items, parent_id=item_id, expected_updated_at=expected_updated_at)

    def delete(self, share_id):
        with SessionLocal() as db:
            row, current = self._open(db, share_id, 'admin')
            kind, item_id = row.kind, row.revision_id
        if current == 'owner' and kind in WARDROBE:
            return self.store.delete_item(kind, item_id)   # Also a guest's own item.
        return super().delete(share_id)

    def owner_access(self, kinds=WARDROBE):
        return super().owner_access(kinds)
