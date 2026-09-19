"""Hearted fabrics keep a stable fabric id. Nothing is copied, not even a standard fabric."""
from sqlalchemy.exc import IntegrityError

from webapp import fabrics
from webapp.db import SessionLocal
from webapp.models import User, WardrobeFavorite

# Shares one table with garment and outfit favorites; the kind keeps them apart.
KIND = 'fabric'


def keys(email):
    if not email:
        return set()
    with SessionLocal() as db:
        return {row.item_id for row in db.query(WardrobeFavorite).filter_by(
            owner_email=fabrics._email(email), kind=KIND)}


def set_favorite(email, identity, enabled):
    if not email:
        raise ValueError('Sign in to save favorites.')
    if enabled:
        fabrics.get_fabric(email, identity)     # Only a fabric this account can open.
    with SessionLocal() as db:
        owner = fabrics._email(email)
        if db.get(User, owner) is None:
            raise ValueError('Sign in to save favorites.')
        query = db.query(WardrobeFavorite).filter_by(owner_email=owner, kind=KIND, item_id=identity)
        if not enabled:
            query.delete()
        elif query.first() is None:
            db.add(WardrobeFavorite(owner_email=owner, kind=KIND, item_id=identity))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()                       # Two clicks or tabs may heart the same fabric.


def favorites(email):
    """Most recent first, each fabric once. A fabric that no longer resolves is skipped."""
    if not email:
        return []
    with SessionLocal() as db:
        order = [row.item_id for row in db.query(WardrobeFavorite).filter_by(
            owner_email=fabrics._email(email), kind=KIND).order_by(WardrobeFavorite.created_at.desc(),
                                                                  WardrobeFavorite.id.desc())]
    available = {record['id']: record for record in fabrics.standard_fabrics() + fabrics.list_fabrics(email)}
    return [available[identity] for identity in order if identity in available]
