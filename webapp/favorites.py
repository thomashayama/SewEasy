"""Bookmarks retain identity, not copies of somebody else's private design."""
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import WardrobeFavorite, User
from webapp.wardrobe_sharing import WardrobeSharing


# Fabric hearts share the table (webapp/fabric_favorites.py) but are not wardrobe items.
KINDS = ('garment', 'outfit', 'share')


class Favorites:
    def __init__(self, store):
        self.store = store

    def keys(self):
        if not self.store.email:
            return set()
        with SessionLocal() as db:
            return {f'{r.kind}:{r.item_id}' for r in db.query(WardrobeFavorite).filter(
                WardrobeFavorite.owner_email == self.store.email, WardrobeFavorite.kind.in_(KINDS))}

    def set(self, kind, item_id, enabled):
        if not self.store.email:
            raise ValueError('Sign in to save favorites.')
        if kind not in KINDS:
            raise ValueError('Choose a garment or outfit.')
        if kind == 'share':
            try:
                source = WardrobeSharing(self.store).get(item_id)
            except ValueError:
                if enabled:
                    raise
            else:
                if source['is_owner']:
                    kind, item_id = source['kind'], source['revision_id']
        elif enabled:
            self.store.revision(kind, item_id)
        with SessionLocal() as db:
            if db.get(User, self.store.email) is None:
                raise ValueError('Sign in to save favorites.')
            query = db.query(WardrobeFavorite).filter_by(owner_email=self.store.email, kind=kind, item_id=item_id)
            if not enabled:
                query.delete()
            elif query.first() is None:
                db.add(WardrobeFavorite(owner_email=self.store.email, kind=kind, item_id=item_id))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # Two clicks/tabs may favorite the same item.

    def list(self):
        if not self.store.email:
            return []
        with SessionLocal() as db:
            refs = [(r.kind, r.item_id) for r in db.query(WardrobeFavorite).filter(
                WardrobeFavorite.owner_email == self.store.email, WardrobeFavorite.kind.in_(KINDS)
            ).order_by(WardrobeFavorite.created_at.desc())]
        result, sharing = [], WardrobeSharing(self.store)
        library = self.store.read()
        owned = {f'{kind}:{item["id"]}': item for kind, bucket in (('garment', 'garments'), ('outfit', 'outfits'))
                 for item in library[bucket]}
        for kind, item_id in refs:
            try:
                if kind == 'share':
                    result.append(dict(sharing.get(item_id), favorite_kind=kind))
                elif f'{kind}:{item_id}' in owned:
                    result.append(dict(id=item_id, kind=kind, favorite_kind=kind, is_owner=True,
                                       snapshot=owned[f'{kind}:{item_id}']))
            except ValueError:
                continue  # Revoked/private shares disappear, including their names and photos.
        return result
