"""One access model for garments, outfits, fabrics and body profiles.

Every item is private when it is created, and has exactly one owner: the
account that made it (or the browser, for a guest's garment or outfit) until
the owner transfers it. Everyone else reaches it in two ways:

* General access: private, friends (the owner's), anyone with the link, or
  public (also listed in Explore). Each lets its audience view the item.
* Members, added by email as a viewer or an admin.

Viewers open the item and save their own copy, which is a new private item.
Admins can also edit and rename it, change its general access and members
(other admins included), and delete it. Only the owner transfers ownership,
and only to a member who has signed in; the previous owner stays an admin.

Records live in `wardrobe_shares` and `wardrobe_invitations`, names kept from
when only garments and outfits could be shared. An item without a record is
private. The record is created the first time its sharing is opened, and its
ID is the item's unguessable link. Each item module owns its storage and
exposes `delete_item(kind, item_id, owner)` and `transfer_item(kind, item_id,
old_owner, new_owner)`, which this module calls once a role is checked.
"""
from copy import deepcopy
import secrets

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.friends import are_friends, friend_emails, normalize_email
from webapp.models import (BodyProfile, Fabric, FinishedPhoto, User, WardrobeFavorite, WardrobeInvitation,
                           WardrobeShare)

KINDS = ('garment', 'outfit', 'fabric', 'body')
WARDROBE = ('garment', 'outfit')
NOUNS = dict(garment='garment', outfit='outfit', fabric='fabric', body='measurement profile')

VISIBILITY = {
    'private': ('Private', 'Only the owner and the people added below can open this {noun}.'),
    'friends': ('Friends', "The owner's accepted friends can view this {noun} and save a copy."),
    'link': ('Anyone with the link', 'Anyone with this link can view this {noun} and save a copy. '
                                     'It stays out of Explore.'),
    'public': ('Public', 'Anyone can discover this {noun} in Explore, view it and save a copy.'),
}
ROLES = {
    'viewer': ('Viewer', 'Can view and save a copy'),
    'admin': ('Admin', 'Can also edit, share and delete'),
}
RANK = {None: 0, 'viewer': 1, 'admin': 2, 'owner': 3}


class ShareUnavailable(ValueError):
    """No access, told the same way whether or not the item exists."""

    def __init__(self, message='This shared item is private or no longer available.'):
        super().__init__(message)


class NotAllowed(ShareUnavailable):
    """The person can open the item, but their role does not permit this."""


def visibility(row):
    return row.visibility or ('link' if row.public_link else 'private')


def access_label(mode='private', invited=False):
    return 'Shared privately' if mode == 'private' and invited else VISIBILITY[mode][0]


def describe(mode, kind):
    return VISIBILITY[mode][1].format(noun=NOUNS[kind])


def account_of(owner_key):
    """The owning account's email, or None for a guest's item."""
    return owner_key[len('account:'):] if owner_key and owner_key.startswith('account:') else None


def display_name(db, email):
    user = db.get(User, email) if email else None
    return (user.name if user else None) or ('SewEasy member' if email else 'Guest designer')


def public_snapshot(item, kind):
    """What may cross the privacy boundary to someone who can view the item.

    Explicit fields only: never body profiles, private library metadata,
    members, owner emails or other browser storage. Fabrics and profiles are
    read from their own tables, so their records hold just enough to list them.
    """
    if kind in ('fabric', 'body'):
        return {key: item[key] for key in ('name', 'display_color') if item.get(key)}
    fields = ('id', 'name', 'created_at', 'updated_at', 'params', 'appearance', 'forked_from') if kind == 'garment' else (
        'id', 'name', 'revision_id', 'updated_at', 'forked_from')
    result = {key: deepcopy(item[key]) for key in fields if key in item}
    if result.get('forked_from'):
        # Attribution may cross the boundary; the original's private link may not.
        result['forked_from'] = {k: v for k, v in result['forked_from'].items() if k in ('name', 'owner_name', 'kind')}
    if kind == 'outfit':
        result['garments'] = [public_snapshot(g, 'garment') for g in item['garments']]
    return result


def membership(db, row, email):
    if not email:
        return None
    member = db.query(WardrobeInvitation.role).filter_by(share_id=row.id, recipient_email=email).first()
    return (member[0] or 'viewer') if member else None


def role_of(db, row, email, owner_key):
    """'owner', 'admin', 'viewer' or None: the strongest of ownership, membership and general access."""
    if row is None:
        return None
    if owner_key and row.owner_key == owner_key:
        return 'owner'
    member = membership(db, row, email)
    if member == 'admin':
        return 'admin'
    mode = visibility(row)
    if member or mode in ('link', 'public'):
        return 'viewer'
    if mode == 'friends' and are_friends(db, account_of(row.owner_key), email):
        return 'viewer'
    return None


def require(current, minimum):
    if current is None:
        raise ShareUnavailable()
    if RANK[current] < RANK[minimum]:
        raise NotAllowed('Only the owner can transfer ownership.' if minimum == 'owner' else
                         'Only the owner or an admin can change this.')
    return current


def record(db, kind, item_id, lock=False):
    query = db.query(WardrobeShare).filter_by(kind=kind, revision_id=str(item_id))
    return (query.with_for_update() if lock else query).first()


def item_role(db, kind, item_id, email, owner):
    """A person's role on a fabric or profile, which need not have a record yet."""
    if email and owner == email:
        return 'owner'
    return role_of(db, record(db, kind, item_id), email, 'account:' + email if email else None)


def create(db, kind, item_id, owner_key, snapshot, thumbnail=None):
    """A new, private record: no general access and no members. Returns its share ID."""
    db.add(WardrobeShare(id=secrets.token_urlsafe(32), owner_key=owner_key,
                         owner_name=display_name(db, account_of(owner_key)), kind=kind, revision_id=str(item_id),
                         snapshot=snapshot, thumbnail=thumbnail, public_link=False, visibility='private'))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()   # Two tabs opened the same sharing dialog.
    return record(db, kind, item_id).id


def sync(db, kind, item_id, item):
    """Keep a record's listing snapshot in step with its item; the caller commits."""
    row = record(db, kind, item_id)
    if row is not None:
        row.snapshot = public_snapshot(item, kind)


def forget(db, kind, item_id):
    """Drop a deleted item's record, members, bookmarks and photos; the caller commits."""
    item_id = str(item_id)
    for row in db.query(WardrobeShare).filter_by(kind=kind, revision_id=item_id).all():
        db.query(WardrobeFavorite).filter_by(kind='share', item_id=row.id).delete(synchronize_session=False)
        db.delete(row)
    db.query(WardrobeFavorite).filter_by(kind=kind, item_id=item_id).delete(synchronize_session=False)
    db.query(FinishedPhoto).filter_by(kind=kind, item_id=item_id).delete(synchronize_session=False)


def reassign(db, kind, item_id, old_owner, new_owner):
    """Hand an item's record to its new owner within the caller's transaction.

    The new owner stops being a member; the previous owner becomes an admin.
    Returns the record, or raises if ownership changed since it was checked.
    """
    row = record(db, kind, item_id, lock=True)
    if row is None or row.owner_key != 'account:' + old_owner:
        raise ShareUnavailable('This item changed owner. Reopen it and try again.')
    if membership(db, row, new_owner) is None:
        raise ValueError('Add them to this item before making them its owner.')
    db.query(WardrobeInvitation).filter_by(share_id=row.id, recipient_email=new_owner).delete(
        synchronize_session=False)
    row.owner_key, row.owner_name = 'account:' + new_owner, display_name(db, new_owner)
    db.add(WardrobeInvitation(share_id=row.id, recipient_email=old_owner, role='admin'))
    # A bookmark of your own item follows it into its new place in the lists.
    db.query(WardrobeFavorite).filter_by(owner_email=old_owner, kind=kind, item_id=str(item_id)).update(
        dict(kind='share', item_id=row.id), synchronize_session=False)
    db.query(WardrobeFavorite).filter_by(owner_email=new_owner, kind='share', item_id=row.id).update(
        dict(kind=kind, item_id=str(item_id)), synchronize_session=False)
    return row


def unique_name(name, taken):
    """`name`, or `name (2)`, `name (3)`… when the new owner already uses it."""
    taken = {n.casefold() for n in taken}
    candidate, number = name, 2
    while candidate.casefold() in taken:
        candidate, number = f'{name} ({number})', number + 1
    return candidate


def _items(kind):
    if kind in WARDROBE:
        from webapp import wardrobe as module
    elif kind == 'fabric':
        from webapp import fabrics as module
    else:
        from webapp import profiles as module
    return module


class Access:
    """What one person may do with any item, addressed by its share ID."""

    def __init__(self, email=None):
        self._email = email.strip().lower() if email else None

    @property
    def email(self):
        return self._email

    @property
    def owner_key(self):
        return 'account:' + self.email if self.email else None

    def _open(self, db, share_id, minimum='viewer', lock=False):
        query = db.query(WardrobeShare).filter_by(id=share_id)
        row = (query.with_for_update() if lock else query).first()
        return row, require(role_of(db, row, self.email, self.owner_key), minimum)

    def _view(self, db, row, current, thumbnail=False):
        result = dict(id=row.id, kind=row.kind, revision_id=row.revision_id, owner_name=row.owner_name,
                      snapshot=public_snapshot(row.snapshot, row.kind), visibility=visibility(row), role=current,
                      is_owner=current == 'owner', is_member=membership(db, row, self.email) is not None)
        if thumbnail:
            result['thumbnail'] = row.thumbnail
        return result

    def get(self, share_id):
        with SessionLocal() as db:
            row, current = self._open(db, share_id)
            return self._view(db, row, current, thumbnail=True)

    def role(self, share_id):
        """The caller's role, or None; never raises for a missing item."""
        with SessionLocal() as db:
            return role_of(db, db.get(WardrobeShare, share_id), self.email, self.owner_key)

    def ensure(self, kind, item_id):
        """A fabric's or profile's share ID, for its owner or an admin. A new record is private."""
        if kind not in ('fabric', 'body'):
            raise ValueError('Unknown item type.')
        with SessionLocal() as db:
            try:
                item = db.get(Fabric, str(item_id)) if kind == 'fabric' else db.get(BodyProfile, int(item_id))
            except (TypeError, ValueError):
                item = None
            if item is None:
                raise ShareUnavailable()
            existing = record(db, kind, item.id)
            if existing is not None:
                require(role_of(db, existing, self.email, self.owner_key), 'admin')
                return existing.id
            if not self.email or item.owner_email != self.email:
                raise ShareUnavailable()
            color = ((item.content or {}).get('appearance') or {}).get('display_color') if kind == 'fabric' else None
            return create(db, kind, item.id, self.owner_key,
                          public_snapshot(dict(name=item.name, display_color=color), kind))

    def settings(self, share_id):
        with SessionLocal() as db:
            row, current = self._open(db, share_id, 'admin')
            members = sorted(row.invitations, key=lambda m: m.recipient_email)
            return dict(kind=row.kind, name=(row.snapshot or {}).get('name', ''), role=current,
                        owner_name=row.owner_name, account_owned=account_of(row.owner_key) is not None,
                        visibility=visibility(row), public_link=row.public_link,
                        recipients=[m.recipient_email for m in members],
                        members=[dict(email=m.recipient_email, role=m.role or 'viewer') for m in members])

    def set_visibility(self, share_id, mode):
        if mode not in VISIBILITY:
            raise ValueError('Choose Private, Friends, Anyone with the link or Public.')
        with SessionLocal() as db:
            row, _ = self._open(db, share_id, 'admin', lock=True)
            if mode in ('friends', 'public') and account_of(row.owner_key) is None:
                raise ValueError('Sign in to share with friends or publish in Explore.')
            row.visibility = mode
            row.public_link = mode in ('link', 'public')
            db.commit()

    def set_link(self, share_id, enabled):
        self.set_visibility(share_id, 'link' if enabled else 'private')

    def add_member(self, share_id, email, role=None):
        """Give someone access by email. An existing member keeps their role unless one is given."""
        email = normalize_email(email)
        if role is not None and role not in ROLES:
            raise ValueError('Choose Viewer or Admin.')
        with SessionLocal() as db:
            row, _ = self._open(db, share_id, 'admin', lock=True)
            if row.owner_key == 'account:' + email:
                raise ValueError('You already own this item.' if email == self.email else 'That person owns this item.')
            if role == 'admin' and account_of(row.owner_key) is None:
                raise ValueError('Sign in to add admins. A guest’s item can only have viewers.')
            member = db.query(WardrobeInvitation).filter_by(share_id=share_id, recipient_email=email).first()
            if member is None:
                db.add(WardrobeInvitation(share_id=share_id, recipient_email=email, role=role or 'viewer'))
            elif role:
                member.role = role
            try:
                db.commit()
            except IntegrityError:
                db.rollback()   # A concurrent, identical invitation already won.

    def invite(self, share_id, email):
        self.add_member(share_id, email)

    def set_role(self, share_id, email, role):
        if role not in ROLES:
            raise ValueError('Choose Viewer or Admin.')
        email = (email or '').strip().lower()
        with SessionLocal() as db:
            row, _ = self._open(db, share_id, 'admin', lock=True)
            if role == 'admin' and account_of(row.owner_key) is None:
                raise ValueError('Sign in to add admins. A guest’s item can only have viewers.')
            member = db.query(WardrobeInvitation).filter_by(share_id=share_id, recipient_email=email).first()
            if member is None:
                raise ValueError('They no longer have access. Add them again.')
            member.role = role
            db.commit()

    def remove_member(self, share_id, email):
        """Admins remove anyone but the owner; any member may remove themselves."""
        email = (email or '').strip().lower()
        with SessionLocal() as db:
            leaving = bool(email) and email == self.email
            self._open(db, share_id, 'viewer' if leaving else 'admin', lock=True)
            db.query(WardrobeInvitation).filter_by(share_id=share_id, recipient_email=email).delete(
                synchronize_session=False)
            db.commit()

    revoke_invitation = remove_member

    def leave(self, share_id):
        if not self.email:
            raise ValueError('Sign in to manage what is shared with you.')
        self.remove_member(share_id, self.email)

    def stop_sharing(self, share_id):
        """Private again and without viewers. Admins keep access, so it stays manageable."""
        with SessionLocal() as db:
            self._open(db, share_id, 'admin', lock=True)
            row = db.get(WardrobeShare, share_id)
            row.visibility, row.public_link = 'private', False
            db.query(WardrobeInvitation).filter(WardrobeInvitation.share_id == share_id,
                                                WardrobeInvitation.role != 'admin').delete(synchronize_session=False)
            db.commit()

    def transfer(self, share_id, email):
        """Make a signed-in member the owner. The caller stays on as an admin."""
        email = normalize_email(email)
        with SessionLocal() as db:
            row, _ = self._open(db, share_id, 'owner')
            previous = account_of(row.owner_key)
            if previous is None:
                raise ValueError('Sign in before transferring ownership.')
            if email == previous:
                raise ValueError('You already own this item.')
            if membership(db, row, email) is None:
                raise ValueError('Add them to this item before making them its owner.')
            if db.get(User, email) is None:
                raise ValueError('They need to sign in to SewEasy once before they can own it.')
            kind, item_id = row.kind, row.revision_id
        return _items(kind).transfer_item(kind, item_id, previous, email)

    def delete(self, share_id):
        """Delete the item itself, for its owner or an admin. Copies others saved remain theirs."""
        with SessionLocal() as db:
            row, _ = self._open(db, share_id, 'admin')
            kind, item_id, owner = row.kind, row.revision_id, account_of(row.owner_key)
        if owner is None:
            raise NotAllowed('Only the owner can delete this item.')
        _items(kind).delete_item(kind, item_id, owner)

    def owner_access(self, kinds=WARDROBE):
        """Small badges for your own items; no snapshots or images are loaded."""
        with SessionLocal() as db:
            rows = db.query(WardrobeShare.id, WardrobeShare.kind, WardrobeShare.revision_id, WardrobeShare.visibility,
                            WardrobeShare.public_link).filter(WardrobeShare.owner_key == self.owner_key,
                                                              WardrobeShare.kind.in_(kinds)).all()
            invited = {r[0] for r in db.query(WardrobeInvitation.share_id).filter(
                WardrobeInvitation.share_id.in_([r.id for r in rows])).distinct()} if rows else set()
            return {f'{r.kind}:{r.revision_id}': dict(share_id=r.id, visibility=visibility(r), invited=r.id in invited)
                    for r in rows}

    def shared_with_me(self, kinds=KINDS):
        """Items you are a member of, or that a friend opened to friends. Never your own."""
        if not self.email:
            return []
        with SessionLocal() as db:
            friends = ['account:' + email for email in friend_emails(db, self.email)]
            member = db.query(WardrobeInvitation.id).filter(
                WardrobeInvitation.share_id == WardrobeShare.id,
                WardrobeInvitation.recipient_email == self.email).exists()
            rows = db.query(WardrobeShare).filter(
                WardrobeShare.kind.in_(kinds), WardrobeShare.owner_key != self.owner_key,
                or_(member, and_(WardrobeShare.visibility == 'friends', WardrobeShare.owner_key.in_(friends)))
            ).order_by(WardrobeShare.updated_at.desc()).all()
            return [self._view(db, row, role_of(db, row, self.email, self.owner_key), thumbnail=True) for row in rows]

    def discover(self, query='', offset=0, limit=24, kinds=KINDS):
        """Only explicitly public items. Unlisted legacy links never appear."""
        with SessionLocal() as db:
            rows = db.query(WardrobeShare).filter(WardrobeShare.visibility == 'public', WardrobeShare.kind.in_(kinds))
            if query:
                term = '%' + query.strip()[:200].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                rows = rows.filter(or_(WardrobeShare.snapshot['name'].as_string().ilike(term, escape='\\'),
                                       WardrobeShare.owner_name.ilike(term, escape='\\')))
            rows = rows.order_by(WardrobeShare.updated_at.desc(), WardrobeShare.id).offset(max(0, offset)).limit(
                min(100, max(1, limit)))
            return [self._view(db, row, role_of(db, row, self.email, self.owner_key), thumbnail=True) for row in rows]


def migrate_profile_shares(engine):
    """Fold legacy body-profile shares into viewer members. Idempotent."""
    from sqlalchemy.orm import Session
    from webapp.models import BodyProfileShare
    with Session(engine) as db:
        for share in db.query(BodyProfileShare).all():
            profile = db.get(BodyProfile, share.profile_id)
            if profile is not None and share.recipient_email != profile.owner_email:
                row = record(db, 'body', profile.id)
                if row is None:
                    row = WardrobeShare(id=secrets.token_urlsafe(32), owner_key='account:' + profile.owner_email,
                                        owner_name=display_name(db, profile.owner_email), kind='body',
                                        revision_id=str(profile.id), snapshot=dict(name=profile.name),
                                        public_link=False, visibility='private')
                    db.add(row)
                    db.flush()
                if membership(db, row, share.recipient_email) is None:
                    db.add(WardrobeInvitation(share_id=row.id, recipient_email=share.recipient_email, role='viewer'))
            db.delete(share)
            db.flush()
        db.commit()
