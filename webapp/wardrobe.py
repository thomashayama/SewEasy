"""Saved garment versions and outfits made from those immutable snapshots.

Account libraries live in SQL; guest libraries use the browser's existing
NiceGUI user storage. Neither includes body measurements.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import contextmanager
from threading import RLock
from sqlalchemy import text

from webapp.db import SessionLocal
from webapp.models import WardrobeLibrary
from webapp.designs import snapshot_design_params


def empty_library():
    return {'garments': [], 'outfits': [], 'outfit_revisions': []}


def normalize_library(content):
    """Give pre-versioning saves deterministic identities, without changing designs."""
    library = deepcopy(content or empty_library())
    groups = {}
    for garment in library['garments']:
        previous = groups.get(garment['name'])
        garment.setdefault('lineage_id', previous['lineage_id'] if previous else garment['id'])
        garment.setdefault('parent_revision_id', previous['id'] if previous else None)
        groups[garment['name']] = garment
    history = library.setdefault('outfit_revisions', [])
    for outfit in library['outfits']:
        outfit.setdefault('revision_id', outfit['id'])
        outfit.setdefault('version', 1)
        outfit.setdefault('parent_revision_id', None)
        if not any(o['revision_id'] == outfit['revision_id'] for o in history):
            history.append(deepcopy(outfit))
    from webapp.thumbnail_migration import migrate_thumbnails
    migrate_thumbnails(library)
    return library


def latest_garments(library):
    latest = {}
    for garment in library['garments']:
        latest[garment['lineage_id']] = garment
    return list(latest.values())


_guest_lock = RLock()


class Wardrobe:
    def __init__(self, email=None, storage=None):
        self.email = email.strip().lower() if email else None
        self.storage = storage if storage is not None else {}

    @property
    def owner_key(self):
        if self.email:
            return 'account:' + self.email
        # Stored server-side in signed-session user storage, never accepted
        # from share URLs or garment metadata.
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
        if library.get('thumbnails') != (content or {}).get('thumbnails'):
            # Persist the one-time image migration under the normal write lock.
            with self._edit() as migrated:
                return deepcopy(migrated)
        return library

    @contextmanager
    def _edit(self):
        """Allocate versions and update JSON in one transaction, including thumbnails."""
        if self.email:
            with SessionLocal() as db:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                else:
                    # Lock the parent even before its library row exists.
                    from webapp.models import User
                    db.query(User).filter_by(email=self.email).with_for_update().one()
                row = db.get(WardrobeLibrary, self.email)
                library = normalize_library(row.content if row else None)
                yield library
                if row is None:
                    row = WardrobeLibrary(owner_email=self.email)
                    db.add(row)
                row.content = deepcopy(library)
                db.commit()
        else:
            with _guest_lock:
                library = normalize_library(self.storage.get('wardrobe'))
                yield library
                self.storage['wardrobe'] = deepcopy(library)

    @staticmethod
    def _append_garment(library, name, params, appearance, parent_id=None, new=False, origin=None):
        name = (name or '').strip()
        if not name:
            raise ValueError('Give the garment a name.')
        if not any(v.get('v') for v in params.get('meta', {}).values()):
            raise ValueError('Choose a garment before saving.')
        parent = next((g for g in reversed(library['garments']) if
                       (g['id'] == parent_id if parent_id else g['name'] == name)), None) if not new else None
        if parent_id and parent is None:
            raise ValueError('The original garment version is not in your library.')
        identity = uuid4().hex
        lineage = parent['lineage_id'] if parent else identity
        revision = 1 + max((g['version'] for g in library['garments'] if g['lineage_id'] == lineage), default=0)
        garment = dict(id=identity, lineage_id=lineage, parent_revision_id=parent['id'] if parent else None,
                       name=name, version=revision,
                       params=snapshot_design_params(params), appearance=snapshot_design_params(appearance),
                       created_at=datetime.now(timezone.utc).isoformat())
        origin = origin or (parent or {}).get('forked_from')
        if origin:
            garment['forked_from'] = deepcopy(origin)
        library['garments'].append(garment)
        return garment

    def save_garment(self, name, params, appearance, *, parent_id=None, new=False):
        with self._edit() as library:
            garment = self._append_garment(library, name, params, appearance, parent_id, new)
            return deepcopy(garment)

    @staticmethod
    def _append_outfit(library, name, garment_ids, parent_id=None, new=False, origin=None):
        name = (name or '').strip()
        if not name:
            raise ValueError('Give the outfit a name.')
        if not garment_ids:
            raise ValueError('An outfit needs at least one saved garment.')
        versions = {g['id']: g for g in library['garments']}
        if any(gid not in versions for gid in garment_ids):
            raise ValueError('A garment version is no longer in this library.')
        # Copy the full versions: later revisions cannot silently change outfits.
        items = [deepcopy(versions[gid]) for gid in garment_ids]
        old = next((o for o in reversed(library['outfit_revisions']) if
                    (o['revision_id'] == parent_id if parent_id else o['name'] == name)), None) if not new else None
        if parent_id and old is None:
            raise ValueError('The original outfit version is not in your library.')
        version = 1 + max((o['version'] for o in library['outfit_revisions'] if old and o['id'] == old['id']), default=0)
        outfit = dict(id=old['id'] if old else uuid4().hex, name=name,
                      revision_id=uuid4().hex, version=version, parent_revision_id=old['revision_id'] if old else None,
                      garments=items, updated_at=datetime.now(timezone.utc).isoformat())
        origin = origin or (old or {}).get('forked_from')
        if origin:
            outfit['forked_from'] = deepcopy(origin)
        library['outfit_revisions'].append(deepcopy(outfit))
        library['outfits'] = [o for o in library['outfits'] if o['id'] != outfit['id']] + [outfit]
        return outfit

    def save_outfit(self, name, garment_ids, *, parent_id=None, new=False):
        with self._edit() as library:
            return deepcopy(self._append_outfit(library, name, garment_ids, parent_id, new))

    def revision(self, kind, revision_id):
        key, field = ('garments', 'id') if kind == 'garment' else ('outfit_revisions', 'revision_id')
        if kind not in ('garment', 'outfit'):
            raise ValueError('Unknown item type.')
        item = next((g for g in self.read()[key] if g[field] == revision_id), None)
        if not item:
            raise ValueError('This version is not in your library.')
        return item

    def history(self, kind, revision_id):
        item = self.revision(kind, revision_id)
        key, field = ('garments', 'lineage_id') if kind == 'garment' else ('outfit_revisions', 'id')
        return list(reversed([g for g in self.read()[key] if g[field] == item[field]]))

    def import_fork(self, kind, snapshot, origin, name=None):
        """One atomic, independently owned copy; outfit members are copied too."""
        with self._edit() as library:
            if kind == 'garment':
                result = self._append_garment(library, name or snapshot['name'], snapshot['params'],
                                              snapshot['appearance'], new=True, origin=origin)
            elif kind == 'outfit':
                versions = {}
                for g in snapshot['garments']:
                    if g['id'] not in versions:
                        source = dict(origin, kind='garment', name=g['name'], revision_id=g['id'], version=g['version'])
                        versions[g['id']] = self._append_garment(library, g['name'], g['params'],
                                                                g['appearance'], new=True, origin=source)
                result = self._append_outfit(library, name or snapshot['name'],
                    [versions[g['id']]['id'] for g in snapshot['garments']], new=True, origin=origin)
            else:
                raise ValueError('Unknown item type.')
            return deepcopy(result)

    def delete_outfit(self, outfit_id):
        with self._edit() as library:
            library['outfits'] = [o for o in library['outfits'] if o['id'] != outfit_id]

    def save_thumbnail(self, kind, revision_id, image):
        from webapp.garment_catalog import standard_garments
        from webapp.thumbnail_cache import normalize_image, thumbnail_key
        key = thumbnail_key(kind, revision_id)
        normalized = normalize_image(image)
        with self._edit() as library:
            records, field = ((library['garments'] + standard_garments(), 'id') if kind == 'garment'
                              else (library['outfit_revisions'], 'revision_id'))
            if not any(item[field] == revision_id for item in records):
                raise ValueError('This version is not in your library.')
            # A late render stays attached to its original revision, even when
            # a newer version has been saved in another tab.
            library.setdefault('thumbnails', {})[key] = normalized
        return normalized
