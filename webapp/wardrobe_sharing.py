"""Owner-only sharing controls; recipients can read and fork pinned revisions."""
from copy import deepcopy
import re
import secrets

from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import User, WardrobeShare, WardrobeInvitation
from webapp.thumbnail_cache import thumbnail_key, normalize_image


class ShareUnavailable(ValueError):
    def __init__(self):
        super().__init__('This shared version is private or no longer available.')


def _snapshot(item, kind):
    # Explicit boundary: never copy body profiles, private library metadata,
    # recipients, owner emails or other browser storage into a shared version.
    fields = ('id', 'name', 'version', 'created_at', 'params', 'appearance', 'forked_from') if kind == 'garment' else (
        'id', 'name', 'version', 'revision_id', 'updated_at', 'forked_from')
    result = {key: deepcopy(item[key]) for key in fields if key in item}
    if kind == 'outfit':
        result['garments'] = [_snapshot(g, 'garment') for g in item['garments']]
    return result


class WardrobeSharing:
    def __init__(self, store):
        self.store = store

    def _owned(self, db, share_id):
        row = db.query(WardrobeShare).filter_by(id=share_id, owner_key=self.store.owner_key).with_for_update().first()
        if row is None:
            raise ShareUnavailable()
        return row

    def _accessible(self, db, share_id):
        row = db.get(WardrobeShare, share_id)
        if row is None:
            raise ShareUnavailable()
        invited = self.store.email and db.query(WardrobeInvitation.id).filter_by(
            share_id=share_id, recipient_email=self.store.email).first()
        if row.owner_key != self.store.owner_key and not row.public_link and not invited:
            raise ShareUnavailable()
        return row

    def _view(self, row, thumbnail=False):
        result = dict(id=row.id, kind=row.kind, revision_id=row.revision_id,
                      owner_name=row.owner_name, snapshot=deepcopy(row.snapshot),
                      is_owner=row.owner_key == self.store.owner_key)
        if thumbnail:
            result['thumbnail'] = row.thumbnail
        return result

    def ensure(self, kind, revision_id):
        """Prepare owner controls; access remains private until explicitly granted."""
        snapshot = _snapshot(self.store.revision(kind, revision_id), kind)
        items = snapshot['garments'] if kind == 'outfit' else [snapshot]
        image = self.store.read().get('thumbnails', {}).get(thumbnail_key(items))
        with SessionLocal() as db:
            row = db.query(WardrobeShare).filter_by(owner_key=self.store.owner_key, kind=kind, revision_id=revision_id).first()
            if row:
                if not row.thumbnail and image:
                    row.thumbnail = normalize_image(image)
                    db.commit()
                return row.id
            user = db.get(User, self.store.email) if self.store.email else None
            name = (user.name if user else None) or ('SewEasy member' if self.store.email else 'Guest designer')
            row = WardrobeShare(id=secrets.token_urlsafe(32), owner_key=self.store.owner_key,
                                owner_name=name, kind=kind, revision_id=revision_id, snapshot=snapshot,
                                thumbnail=normalize_image(image) if image else None, public_link=False)
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                # Two tabs can open the same share dialog concurrently.
                row = db.query(WardrobeShare).filter_by(owner_key=self.store.owner_key, kind=kind, revision_id=revision_id).one()
            return row.id

    def settings(self, share_id):
        with SessionLocal() as db:
            row = self._owned(db, share_id)
            return dict(public_link=row.public_link, recipients=sorted(i.recipient_email for i in row.invitations))

    def set_link(self, share_id, enabled):
        with SessionLocal() as db:
            row = self._owned(db, share_id)
            row.public_link = bool(enabled)
            db.commit()

    def invite(self, share_id, email):
        email = (email or '').strip().lower()
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValueError('Enter a valid email address.')
        if email == self.store.email:
            raise ValueError('You already own this version.')
        with SessionLocal() as db:
            self._owned(db, share_id)
            if not db.query(WardrobeInvitation).filter_by(share_id=share_id, recipient_email=email).first():
                db.add(WardrobeInvitation(share_id=share_id, recipient_email=email))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()  # A concurrent, identical invitation already won.

    def revoke_invitation(self, share_id, email):
        with SessionLocal() as db:
            self._owned(db, share_id)
            db.query(WardrobeInvitation).filter_by(share_id=share_id, recipient_email=email.strip().lower()).delete()
            db.commit()

    def shared_with_me(self):
        if not self.store.email:
            return []
        with SessionLocal() as db:
            rows = db.query(WardrobeShare).join(WardrobeInvitation).filter(
                WardrobeInvitation.recipient_email == self.store.email).order_by(WardrobeShare.created_at.desc()).all()
            return [self._view(row) for row in rows]

    def get(self, share_id):
        with SessionLocal() as db:
            return self._view(self._accessible(db, share_id), thumbnail=True)

    def fork(self, share_id, name=None):
        # Recheck permission on the action, not just when its page was opened.
        source = self.get(share_id)
        item = source['snapshot']
        origin = dict(share_id=share_id, kind=source['kind'], revision_id=source['revision_id'],
                      name=item['name'], version=item['version'], owner_name=source['owner_name'])
        result = self.store.import_fork(source['kind'], item, origin, name=name)
        if source.get('thumbnail'):
            items = result['garments'] if source['kind'] == 'outfit' else [result]
            self.store.save_thumbnail(thumbnail_key(items), source['thumbnail'])
        return result
