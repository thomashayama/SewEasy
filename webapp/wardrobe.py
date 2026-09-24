"""Named, independently owned garments and outfits; Save updates an existing item."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import contextmanager
from threading import RLock
import re
from sqlalchemy import text

from webapp.db import SessionLocal
from webapp.models import WardrobeLibrary, WardrobeShare
from webapp.designs import snapshot_design_params


def empty_library():
    return {'format': 2, 'garments': [], 'outfits': []}


def copy_name(name, records):
    name = re.sub(r' \(copy(?: \d+)?\)$', '', name, flags=re.IGNORECASE)
    used = {r['name'].casefold() for r in records}
    candidate = f'{name} (copy)'
    number = 2
    while candidate.casefold() in used:
        candidate = f'{name} (copy {number})'
        number += 1
    return candidate


def normalize_library(content):
    library = deepcopy(content or empty_library())
    library.setdefault('garments', [])
    library.setdefault('outfits', [])
    from webapp.thumbnail_migration import migrate_thumbnails
    migrate_thumbnails(library)
    if library.get('format') == 2:
        return library
    # Preserve every old save as a named item. Existing IDs retain their images,
    # shares and outfit references. Newest saves retain the original name.
    live = {o['id'] for o in library['outfits']}
    outfits = {o.get('revision_id', o['id']): o for o in library.get('outfit_revisions', []) if o['id'] in live}
    outfits.update({o.get('revision_id', o['id']): o for o in library['outfits']})
    library['outfits'] = list(outfits.values())
    for key in ('garments', 'outfits'):
        named = []
        for item in reversed(library[key]):
            if key == 'outfits':
                item['id'] = item.get('revision_id', item['id'])
                item['revision_id'] = item['id']  # compatibility alias, never incremented
            if any(r['name'].casefold() == item['name'].casefold() for r in named):
                item['name'] = copy_name(item['name'], named)
            for field in ('version', 'lineage_id', 'parent_revision_id'):
                item.pop(field, None)
            if key == 'outfits':
                for garment in item['garments']:
                    for field in ('version', 'lineage_id', 'parent_revision_id'):
                        garment.pop(field, None)
            item.setdefault('updated_at', item.get('created_at', ''))
            named.append(item)
        library[key] = list(reversed(named))
    library.pop('outfit_revisions', None)
    library['format'] = 2
    return library


def latest_garments(library):
    return library['garments']


def same_design(a, b):
    return all(a.get(k) == b.get(k) for k in ('params', 'appearance'))


def same_items(a, b):
    return len(a) == len(b) and all(same_design(x, y) for x, y in zip(a, b))


_guest_lock = RLock()


class Wardrobe:
    def __init__(self, email=None, storage=None):
        self.email = email.strip().lower() if email else None
        self.storage = storage if storage is not None else {}

    @property
    def owner_key(self):
        if self.email:
            return 'account:' + self.email
        with _guest_lock:
            if not self.storage.get('wardrobe_owner'):
                self.storage['wardrobe_owner'] = uuid4().hex
            return 'guest:' + self.storage['wardrobe_owner']

    def read(self):
        if self.email:
            with SessionLocal() as db:
                row = db.get(WardrobeLibrary, self.email)
                content = row.content if row else None
        else:
            content = self.storage.get('wardrobe')
        library = normalize_library(content)
        if content is not None and library != content:
            with self._edit() as migrated:
                return deepcopy(migrated)
        return library

    def _sync_shares(self, db, library):
        from webapp.wardrobe_sharing import _snapshot
        for row in db.query(WardrobeShare).filter(WardrobeShare.owner_key == self.owner_key,
                                                  WardrobeShare.kind.in_(('garment', 'outfit'))):
            records = library['garments' if row.kind == 'garment' else 'outfits']
            item = next((x for x in records if x['id'] == row.revision_id), None)
            if item:
                row.snapshot = _snapshot(item, row.kind)
                row.thumbnail = library.get('thumbnails', {}).get(f'{row.kind}:{item["id"]}')

    @contextmanager
    def _edit(self):
        if self.email:
            with SessionLocal() as db:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                else:
                    from webapp.models import User
                    db.query(User).filter_by(email=self.email).with_for_update().one()
                row = db.get(WardrobeLibrary, self.email)
                library = normalize_library(row.content if row else None)
                yield library
                if row is None:
                    row = WardrobeLibrary(owner_email=self.email)
                    db.add(row)
                row.content = deepcopy(library)
                self._sync_shares(db, library)
                db.commit()
        else:
            with _guest_lock:
                library = normalize_library(self.storage.get('wardrobe'))
                yield library
                if self.storage.get('wardrobe_owner'):
                    with SessionLocal() as db:
                        self._sync_shares(db, library)
                        db.commit()
                self.storage['wardrobe'] = deepcopy(library)

    def suggested_copy_name(self, kind, name):
        return copy_name(name, self.read()['garments' if kind == 'garment' else 'outfits'])

    @staticmethod
    def _target(library, kind, name, parent_id, new, expected_updated_at=None):
        records = library['garments' if kind == 'garment' else 'outfits']
        name = (name or '').strip()
        if not name:
            raise ValueError(f'Give the {kind} a name.')
        old = next((g for g in records if g['id'] == parent_id), None) if parent_id and not new else None
        if parent_id and not new and old is None:
            raise ValueError(f'This {kind} is not in your library. Save a copy instead.')
        if old and expected_updated_at is not None and old.get('updated_at', '') != expected_updated_at:
            raise ValueError('This item changed in another tab. Reopen it from your wardrobe or save a copy.')
        if any(g['name'].casefold() == name.casefold() and (not old or g['id'] != old['id']) for g in records):
            raise ValueError(f'This {kind} name is already in use. Choose another name.')
        return records, name, old

    @classmethod
    def _save_garment(cls, library, name, params, appearance, parent_id=None, new=False, origin=None, expected_updated_at=None):
        records, name, old = cls._target(library, 'garment', name, parent_id, new, expected_updated_at)
        if not any(v.get('v') for v in params.get('meta', {}).values()):
            raise ValueError('Choose a garment before saving.')
        now = datetime.now(timezone.utc).isoformat()
        item = dict(id=old['id'] if old else uuid4().hex, name=name,
                    params=snapshot_design_params(params), appearance=snapshot_design_params(appearance),
                    created_at=old.get('created_at', now) if old else now, updated_at=now)
        origin = origin or (old or {}).get('forked_from')
        if origin:
            item['forked_from'] = deepcopy(origin)
        if old:
            records[records.index(old)] = item
            if not same_design(old, item):
                library.get('thumbnails', {}).pop('garment:' + item['id'], None)
        else:
            records.append(item)
        return item

    def save_garment(self, name, params, appearance, *, parent_id=None, new=False, origin=None, expected_updated_at=None):
        with self._edit() as library:
            return deepcopy(self._save_garment(library, name, params, appearance, parent_id, new, origin, expected_updated_at))

    @classmethod
    def _save_outfit(cls, library, name, garment_ids=None, parent_id=None, new=False, origin=None, items=None, expected_updated_at=None):
        records, name, old = cls._target(library, 'outfit', name, parent_id, new, expected_updated_at)
        if items is None:
            owned = {g['id']: g for g in library['garments']}
            if any(gid not in owned for gid in (garment_ids or [])):
                raise ValueError('A garment is no longer in your library.')
            items = [owned[gid] for gid in (garment_ids or [])]
        if not items:
            raise ValueError('An outfit needs at least one garment.')
        if any(not any(v.get('v') for v in g.get('params', {}).get('meta', {}).values()) for g in items):
            raise ValueError('Choose a garment before saving.')
        # Outfit adjustments belong to the outfit, never silently update library garments.
        from webapp.wardrobe_sharing import _snapshot
        identity = old['id'] if old else uuid4().hex
        item = dict(id=identity, revision_id=identity, name=name,
                    garments=[_snapshot(g, 'garment') for g in items], updated_at=datetime.now(timezone.utc).isoformat())
        origin = origin or (old or {}).get('forked_from')
        if origin:
            item['forked_from'] = deepcopy(origin)
        if old:
            records[records.index(old)] = item
            if not same_items(old['garments'], item['garments']):
                library.get('thumbnails', {}).pop('outfit:' + identity, None)
        else:
            records.append(item)
        return item

    def save_outfit(self, name, garment_ids=None, *, parent_id=None, new=False, origin=None, items=None, expected_updated_at=None):
        with self._edit() as library:
            return deepcopy(self._save_outfit(library, name, garment_ids, parent_id, new, origin, items, expected_updated_at))

    def revision(self, kind, item_id):
        if kind not in ('garment', 'outfit'):
            raise ValueError('Unknown item type.')
        item = next((g for g in self.read()['garments' if kind == 'garment' else 'outfits'] if g['id'] == item_id), None)
        if not item:
            raise ValueError('This item is not in your library.')
        return item

    def import_fork(self, kind, snapshot, origin, name=None):
        with self._edit() as library:
            records = library['garments' if kind == 'garment' else 'outfits']
            name = copy_name(snapshot['name'], records) if name is None else name
            if kind == 'garment':
                result = self._save_garment(library, name, snapshot['params'], snapshot['appearance'], new=True, origin=origin)
            elif kind == 'outfit':
                result = self._save_outfit(library, name, items=snapshot['garments'], new=True, origin=origin)
            else:
                raise ValueError('Unknown item type.')
            return deepcopy(result)

    def delete_item(self, kind, item_id):
        """Delete a garment or outfit along with its access, bookmarks and photos.

        Outfits embed their garments, so deleting a garment leaves them intact.
        Copies other people saved are theirs and remain.
        """
        if kind not in ('garment', 'outfit'):
            raise ValueError('Unknown item type.')
        from webapp.access import forget
        with self._edit() as library:
            bucket = 'garments' if kind == 'garment' else 'outfits'
            if not any(item['id'] == item_id for item in library[bucket]):
                raise ValueError('This item is not in your library.')
            library[bucket] = [item for item in library[bucket] if item['id'] != item_id]
            library.get('thumbnails', {}).pop(f'{kind}:{item_id}', None)
        with SessionLocal() as db:
            forget(db, kind, item_id)
            db.commit()

    def delete_outfit(self, outfit_id):
        self.delete_item('outfit', outfit_id)

    def save_thumbnail(self, kind, item_id, image, *, items=None):
        from webapp.garment_catalog import standard_garments
        from webapp.thumbnail_cache import normalize_image, thumbnail_key
        key = thumbnail_key(kind, item_id)
        normalized = normalize_image(image)
        with self._edit() as library:
            records = library['garments'] + standard_garments() if kind == 'garment' else library['outfits']
            item = next((g for g in records if g['id'] == item_id), None)
            if item is None:
                raise ValueError('This item is not in your library.')
            current = [item] if kind == 'garment' else item['garments']
            if items is not None and not same_items(items, current):
                raise ValueError('The design changed while its thumbnail was rendering.')
            library.setdefault('thumbnails', {})[key] = normalized
        return normalized


def delete_item(kind, item_id, owner):
    """For webapp.access, once an admin's role is checked."""
    Wardrobe(owner).delete_item(kind, item_id)


def transfer_item(kind, item_id, old_owner, new_owner):
    """Move a garment or outfit between two account libraries in one transaction.

    Its ID, share link, thumbnail and finished photos go with it; a name the
    new owner already uses gains a number. Returns the moved item.
    """
    from webapp.access import reassign, unique_name
    from webapp.models import FinishedPhoto, User
    bucket = 'garments' if kind == 'garment' else 'outfits'
    with SessionLocal() as db:
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        else:
            # Both owners' rows, in a stable order, as Wardrobe._edit locks one.
            db.query(User).filter(User.email.in_(sorted((old_owner, new_owner)))).order_by(
                User.email).with_for_update().all()
        rows = {email: db.get(WardrobeLibrary, email) for email in (old_owner, new_owner)}
        source, target = (normalize_library(rows[email].content if rows[email] else None)
                          for email in (old_owner, new_owner))
        item = next((x for x in source[bucket] if x['id'] == item_id), None)
        if item is None:
            raise ValueError('This item is no longer available.')
        share = reassign(db, kind, item_id, old_owner, new_owner)
        source[bucket].remove(item)
        item['name'] = unique_name(item['name'], [x['name'] for x in target[bucket]])
        target[bucket].append(item)
        image = source.get('thumbnails', {}).pop(f'{kind}:{item_id}', None)
        if image:
            target.setdefault('thumbnails', {})[f'{kind}:{item_id}'] = image
        for email, library in ((old_owner, source), (new_owner, target)):
            if rows[email] is None:
                rows[email] = WardrobeLibrary(owner_email=email)
                db.add(rows[email])
            rows[email].content = deepcopy(library)
        from webapp.wardrobe_sharing import _snapshot
        share.snapshot = _snapshot(item, kind)
        db.query(FinishedPhoto).filter_by(owner_email=old_owner, kind=kind, item_id=item_id).update(
            dict(owner_email=new_owner), synchronize_session=False)
        db.commit()
        return deepcopy(item)
