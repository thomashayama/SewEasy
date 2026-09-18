"""Owner-only sharing controls; recipients can view and save independent copies."""
from copy import deepcopy
import re
import secrets

from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import User, WardrobeShare, WardrobeInvitation
from webapp.thumbnail_cache import thumbnail_key, normalize_image
from webapp.friends import are_friends, friend_emails

VISIBILITY = {
    'private': ('Private', 'Only you and people you invite can open this design.'),
    'friends': ('Friends', 'Your accepted friends and invited people can view and save a copy.'),
    'link': ('Anyone with the link', 'Anyone with this link can view and save a copy. It stays out of Explore.'),
    'public': ('Public', 'Anyone can discover this design in Explore, view it and save a copy.'),
}


def visibility(row):
    return row.visibility or ('link' if row.public_link else 'private')


def access_label(mode='private', invited=False):
    return 'Shared privately' if mode == 'private' and invited else VISIBILITY[mode][0]


class ShareUnavailable(ValueError):
    def __init__(self):
        super().__init__('This shared item is private or no longer available.')


def _snapshot(item, kind):
    # Explicit boundary: never copy body profiles, private library metadata,
    # recipients, owner emails or other browser storage into a shared item.
    fields = ('id', 'name', 'created_at', 'updated_at', 'params', 'appearance', 'forked_from') if kind == 'garment' else (
        'id', 'name', 'revision_id', 'updated_at', 'forked_from')
    result = {key: deepcopy(item[key]) for key in fields if key in item}
    if result.get('forked_from'):
        # Attribution may cross the boundary; the original's private link may not.
        result['forked_from'] = {k: v for k, v in result['forked_from'].items() if k in ('name', 'owner_name', 'kind')}
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
        mode = visibility(row)
        friend = mode == 'friends' and row.owner_key.startswith('account:') and are_friends(
            db, row.owner_key[len('account:'):], self.store.email)
        if row.owner_key != self.store.owner_key and mode not in ('link', 'public') and not invited and not friend:
            raise ShareUnavailable()
        return row

    def _view(self, row, thumbnail=False):
        result = dict(id=row.id, kind=row.kind, revision_id=row.revision_id,
                      owner_name=row.owner_name, snapshot=_snapshot(row.snapshot, row.kind), visibility=visibility(row),
                      is_owner=row.owner_key == self.store.owner_key)
        if thumbnail:
            result['thumbnail'] = row.thumbnail
        return result

    def ensure(self, kind, revision_id):
        """Prepare owner controls; access remains private until explicitly granted."""
        snapshot = _snapshot(self.store.revision(kind, revision_id), kind)
        image = self.store.read().get('thumbnails', {}).get(thumbnail_key(kind, revision_id))
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
            return dict(public_link=row.public_link, visibility=visibility(row),
                        recipients=sorted(i.recipient_email for i in row.invitations))

    def set_link(self, share_id, enabled):
        self.set_visibility(share_id, 'link' if enabled else 'private')

    def set_visibility(self, share_id, mode):
        if mode not in VISIBILITY:
            raise ValueError('Choose Private, Friends, Anyone with the link or Public.')
        with SessionLocal() as db:
            row = self._owned(db, share_id)
            if mode in ('friends', 'public') and (not self.store.email or not db.get(User, self.store.email)):
                raise ValueError('Sign in to share with friends or publish a design.')
            row.visibility = mode
            row.public_link = mode in ('link', 'public')
            db.commit()

    def stop_sharing(self, share_id):
        with SessionLocal() as db:
            row = self._owned(db, share_id)
            row.visibility, row.public_link = 'private', False
            db.query(WardrobeInvitation).filter_by(share_id=share_id).delete()
            db.commit()

    def owner_access(self):
        """Small library badges; no draft geometry or images are loaded."""
        with SessionLocal() as db:
            rows = db.query(WardrobeShare.id, WardrobeShare.kind, WardrobeShare.revision_id,
                            WardrobeShare.visibility, WardrobeShare.public_link).filter_by(owner_key=self.store.owner_key).all()
            invited = {r[0] for r in db.query(WardrobeInvitation.share_id).filter(
                WardrobeInvitation.share_id.in_([r.id for r in rows])).distinct()} if rows else set()
            return {f'{r.kind}:{r.revision_id}': dict(visibility=visibility(r), invited=r.id in invited) for r in rows}

    def invite(self, share_id, email):
        email = (email or '').strip().lower()
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValueError('Enter a valid email address.')
        if email == self.store.email:
            raise ValueError('You already own this item.')
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
            friends = ['account:' + email for email in friend_emails(db, self.store.email)]
            invitation = db.query(WardrobeInvitation.id).filter(
                WardrobeInvitation.share_id == WardrobeShare.id,
                WardrobeInvitation.recipient_email == self.store.email).exists()
            rows = db.query(WardrobeShare).filter(or_(invitation, and_(
                WardrobeShare.visibility == 'friends', WardrobeShare.owner_key.in_(friends)))).order_by(WardrobeShare.updated_at.desc()).all()
            return [self._view(row, thumbnail=True) for row in rows]

    def discover(self, query='', offset=0, limit=24):
        """Only explicitly public items. Unlisted legacy links never appear."""
        with SessionLocal() as db:
            rows = db.query(WardrobeShare).filter_by(visibility='public')
            if query:
                term = '%' + query.strip()[:200].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                rows = rows.filter(or_(WardrobeShare.snapshot['name'].as_string().ilike(term, escape='\\'),
                                       WardrobeShare.owner_name.ilike(term, escape='\\')))
            rows = rows.order_by(WardrobeShare.updated_at.desc(), WardrobeShare.id).offset(max(0, offset)).limit(min(100, max(1, limit)))
            return [self._view(row, thumbnail=True) for row in rows]

    def get(self, share_id):
        with SessionLocal() as db:
            return self._view(self._accessible(db, share_id), thumbnail=True)

    def fork(self, share_id, name=None):
        # Recheck permission on the action, not just when its page was opened.
        source = self.get(share_id)
        item = source['snapshot']
        origin = dict(share_id=share_id, kind=source['kind'], revision_id=source['revision_id'],
                      name=item['name'], owner_name=source['owner_name'])
        result = self.store.import_fork(source['kind'], item, origin, name=name)
        if source.get('thumbnail'):
            revision_id = result['revision_id'] if source['kind'] == 'outfit' else result['id']
            self.store.save_thumbnail(source['kind'], revision_id, source['thumbnail'])
        return result
