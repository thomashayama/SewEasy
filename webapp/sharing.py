"""Sharing body profiles and designs between users.

A share grants the recipient read access to the live item: it appears in
their account ("Shared with me") and in the studio's measurement/library
pickers, always reflecting the owner's latest edits. Recipients can also
copy a shared item into their own library to get an editable version.

Recipients are addressed by (lowercased) email, so an item can be shared
with someone who hasn't signed in yet.
"""

from typing import Optional

from webapp.db import SessionLocal
from webapp.models import (BodyProfile, BodyProfileShare, Design,
                           DesignShare, User)


def _normalize(email: str) -> str:
    return (email or '').strip().lower()


def _owner_display(db, owner_email: str) -> str:
    user = db.get(User, owner_email)
    return user.name if user is not None and user.name else owner_email


# ----------------------------------------------------------------------
# Owner side: grant, list, and revoke shares

def _share(db, item, shares_model, item_column, owner_email: str,
           recipient_email: str) -> str:
    """Shared grant logic; returns a result code:
    'shared' | 'bad_email' | 'self' | 'not_found' | 'exists'"""
    recipient = _normalize(recipient_email)
    if not recipient or '@' not in recipient:
        return 'bad_email'
    if recipient == owner_email:
        return 'self'
    if item is None or item.owner_email != owner_email:
        return 'not_found'
    exists = (db.query(shares_model)
              .filter(item_column == item.id,
                      shares_model.recipient_email == recipient)
              .one_or_none())
    if exists is not None:
        return 'exists'
    db.add(shares_model(**{item_column.key: item.id,
                           'recipient_email': recipient}))
    db.commit()
    return 'shared'


def share_profile(owner_email: str, profile_id: int,
                  recipient_email: str) -> str:
    with SessionLocal() as db:
        return _share(db, db.get(BodyProfile, profile_id), BodyProfileShare,
                      BodyProfileShare.profile_id, owner_email,
                      recipient_email)


def share_design(owner_email: str, design_id: int,
                 recipient_email: str) -> str:
    with SessionLocal() as db:
        return _share(db, db.get(Design, design_id), DesignShare,
                      DesignShare.design_id, owner_email, recipient_email)


def _recipients(db, item, owner_email: str) -> list:
    if item is None or item.owner_email != owner_email:
        return []
    return [{'share_id': s.id, 'email': s.recipient_email,
             'created_at': s.created_at}
            for s in sorted(item.shares, key=lambda s: s.created_at)]


def profile_recipients(owner_email: str, profile_id: int) -> list:
    with SessionLocal() as db:
        return _recipients(db, db.get(BodyProfile, profile_id), owner_email)


def design_recipients(owner_email: str, design_id: int) -> list:
    with SessionLocal() as db:
        return _recipients(db, db.get(Design, design_id), owner_email)


def _revoke(db, share, item, owner_email: str) -> bool:
    if share is None or item is None or item.owner_email != owner_email:
        return False
    db.delete(share)
    db.commit()
    return True


def revoke_profile_share(owner_email: str, share_id: int) -> bool:
    with SessionLocal() as db:
        share = db.get(BodyProfileShare, share_id)
        item = share.profile if share is not None else None
        return _revoke(db, share, item, owner_email)


def revoke_design_share(owner_email: str, share_id: int) -> bool:
    with SessionLocal() as db:
        share = db.get(DesignShare, share_id)
        item = share.design if share is not None else None
        return _revoke(db, share, item, owner_email)


# ----------------------------------------------------------------------
# Recipient side: list, read, copy, and decline incoming shares

def shared_profiles_with_me(email: str) -> list:
    with SessionLocal() as db:
        rows = (db.query(BodyProfileShare, BodyProfile)
                .join(BodyProfile,
                      BodyProfileShare.profile_id == BodyProfile.id)
                .filter(BodyProfileShare.recipient_email == email)
                .order_by(BodyProfile.updated_at.desc())
                .all())
        return [{'share_id': s.id, 'profile_id': p.id, 'name': p.name,
                 'owner_email': p.owner_email,
                 'owner_name': _owner_display(db, p.owner_email),
                 'updated_at': p.updated_at}
                for s, p in rows]


def shared_designs_with_me(email: str) -> list:
    with SessionLocal() as db:
        rows = (db.query(DesignShare, Design)
                .join(Design, DesignShare.design_id == Design.id)
                .filter(DesignShare.recipient_email == email)
                .order_by(Design.updated_at.desc())
                .all())
        return [{'share_id': s.id, 'design_id': d.id, 'name': d.name,
                 'kind': d.kind or 'outfit', 'preview': d.preview,
                 'owner_email': d.owner_email,
                 'owner_name': _owner_display(db, d.owner_email),
                 'updated_at': d.updated_at}
                for s, d in rows]


def _shared_with(db, shares_model, item_column, item_id: int, email: str):
    return (db.query(shares_model)
            .filter(item_column == item_id,
                    shares_model.recipient_email == email)
            .one_or_none())


def get_shared_profile(email: str, profile_id: int) -> Optional[dict]:
    """The profile's data iff it is shared with `email` (same shape as
    profiles.get_profile, plus the owner's display name)."""
    with SessionLocal() as db:
        if _shared_with(db, BodyProfileShare, BodyProfileShare.profile_id,
                        profile_id, email) is None:
            return None
        row = db.get(BodyProfile, profile_id)
        if row is None:
            return None
        return {'id': row.id, 'name': row.name,
                'measurements': row.measurements,
                'skin_color': row.skin_color,
                'owner_name': _owner_display(db, row.owner_email)}


def get_shared_design(email: str, design_id: int) -> Optional[dict]:
    """The design's data iff it is shared with `email` (same shape as
    designs.get_design, plus the owner's display name)."""
    with SessionLocal() as db:
        if _shared_with(db, DesignShare, DesignShare.design_id,
                        design_id, email) is None:
            return None
        row = db.get(Design, design_id)
        if row is None:
            return None
        return {'id': row.id, 'name': row.name, 'params': row.params,
                'kind': row.kind or 'outfit',
                'drape_glb': row.drape_glb,
                'fabric_color': row.fabric_color,
                'owner_name': _owner_display(db, row.owner_email)}


def decline_profile_share(email: str, share_id: int) -> bool:
    """Recipient removes a share from their list (owner's item untouched)"""
    with SessionLocal() as db:
        share = db.get(BodyProfileShare, share_id)
        if share is None or share.recipient_email != email:
            return False
        db.delete(share)
        db.commit()
        return True


def decline_design_share(email: str, share_id: int) -> bool:
    with SessionLocal() as db:
        share = db.get(DesignShare, share_id)
        if share is None or share.recipient_email != email:
            return False
        db.delete(share)
        db.commit()
        return True


def _unique_name(db, model, owner_email: str, base: str) -> str:
    names = {name for (name,) in
             db.query(model.name).filter(model.owner_email == owner_email)}
    if base not in names:
        return base
    n = 2
    while f'{base} ({n})' in names:
        n += 1
    return f'{base} ({n})'


def copy_shared_profile(email: str, profile_id: int) -> Optional[str]:
    """Copy a profile shared with `email` into their own library.
    Returns the new profile's name, or None if it isn't shared with them."""
    with SessionLocal() as db:
        if _shared_with(db, BodyProfileShare, BodyProfileShare.profile_id,
                        profile_id, email) is None:
            return None
        src = db.get(BodyProfile, profile_id)
        if src is None:
            return None
        name = _unique_name(db, BodyProfile, email, src.name)
        db.add(BodyProfile(owner_email=email, name=name,
                           measurements=dict(src.measurements),
                           skin_color=src.skin_color))
        db.commit()
        return name


def copy_shared_design(email: str, design_id: int) -> Optional[str]:
    """Copy a design shared with `email` into their own library (including
    preview and any stored 3D drape). Returns the new design's name."""
    with SessionLocal() as db:
        if _shared_with(db, DesignShare, DesignShare.design_id,
                        design_id, email) is None:
            return None
        src = db.get(Design, design_id)
        if src is None:
            return None
        name = _unique_name(db, Design, email, src.name)
        db.add(Design(owner_email=email, name=name, params=src.params,
                      kind=src.kind or 'outfit', preview=src.preview,
                      drape_glb=src.drape_glb,
                      fabric_color=src.fabric_color))
        db.commit()
        return name
