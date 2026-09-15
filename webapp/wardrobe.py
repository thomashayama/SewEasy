"""Saved garment versions and outfits made from those immutable snapshots.

Account libraries live in SQL; guest libraries use the browser's existing
NiceGUI user storage. Neither includes body measurements.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from webapp.db import SessionLocal
from webapp.models import WardrobeLibrary
from webapp.designs import snapshot_design_params


def empty_library():
    return {'garments': [], 'outfits': []}


class Wardrobe:
    def __init__(self, email=None, storage=None):
        self.email, self.storage = email, storage

    def read(self):
        if self.email:
            with SessionLocal() as db:
                row = db.get(WardrobeLibrary, self.email)
                return deepcopy(row.content) if row else empty_library()
        return deepcopy(self.storage.get('wardrobe', empty_library()))

    def _write(self, library):
        if self.email:
            with SessionLocal() as db:
                row = db.get(WardrobeLibrary, self.email)
                if row is None:
                    row = WardrobeLibrary(owner_email=self.email)
                    db.add(row)
                row.content = deepcopy(library)
                db.commit()
        else:
            self.storage['wardrobe'] = deepcopy(library)

    def save_garment(self, name, params, appearance):
        name = (name or '').strip()
        if not name:
            raise ValueError('Give the garment a name.')
        if not any(v.get('v') for v in params.get('meta', {}).values()):
            raise ValueError('Choose a garment before saving.')
        library = self.read()
        revision = 1 + max((g['version'] for g in library['garments'] if g['name'] == name), default=0)
        garment = dict(id=uuid4().hex, name=name, version=revision,
                       params=snapshot_design_params(params), appearance=snapshot_design_params(appearance),
                       created_at=datetime.now(timezone.utc).isoformat())
        library['garments'].append(garment)
        self._write(library)
        return deepcopy(garment)

    def save_outfit(self, name, garment_ids):
        name = (name or '').strip()
        if not name:
            raise ValueError('Give the outfit a name.')
        if not garment_ids:
            raise ValueError('An outfit needs at least one saved garment.')
        library = self.read()
        versions = {g['id']: g for g in library['garments']}
        if any(gid not in versions for gid in garment_ids):
            raise ValueError('A garment version is no longer in this library.')
        # Copy the full versions: later revisions cannot silently change outfits.
        items = [deepcopy(versions[gid]) for gid in garment_ids]
        old = next((o for o in library['outfits'] if o['name'] == name), None)
        outfit = dict(id=old['id'] if old else uuid4().hex, name=name,
                      garments=items, updated_at=datetime.now(timezone.utc).isoformat())
        library['outfits'] = [o for o in library['outfits'] if o['id'] != outfit['id']] + [outfit]
        self._write(library)
        return deepcopy(outfit)

    def delete_outfit(self, outfit_id):
        library = self.read()
        library['outfits'] = [o for o in library['outfits'] if o['id'] != outfit_id]
        self._write(library)

    def save_thumbnail(self, key, image):
        from webapp.garment_catalog import standard_garments
        from webapp.thumbnail_cache import normalize_image, thumbnail_key
        library = self.read()
        targets = [[g] for g in library['garments'] + standard_garments()]
        targets.extend(o['garments'] for o in library['outfits'])
        owned_keys = {thumbnail_key(items) for items in targets}
        if key not in owned_keys:
            raise ValueError('This thumbnail no longer matches an item in your library.')
        normalized = normalize_image(image)
        # Keep images separate from garment snapshots, so saving a preview does
        # not create a design revision or alter an outfit's pinned versions.
        library['thumbnails'] = {k: v for k, v in library.get('thumbnails', {}).items() if k in owned_keys}
        library['thumbnails'][key] = normalized
        self._write(library)
        return normalized
