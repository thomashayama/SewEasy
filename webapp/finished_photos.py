"""Owner-uploaded finished garments, with the design's current access rules."""
from io import BytesIO
from uuid import uuid4
import warnings

from fastapi import HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text

from webapp import auth
from webapp.db import SessionLocal
from webapp.models import FinishedPhoto, User
from webapp.wardrobe import Wardrobe
from webapp.wardrobe_sharing import WardrobeSharing

MAX_BYTES = 8_000_000
MAX_PHOTOS = 8


def normalize_photo(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError('Choose a JPEG, PNG or WebP photo under 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in ('JPEG', 'PNG', 'WEBP') or original.width * original.height > 24_000_000:
                    raise ValueError('Choose a JPEG, PNG or WebP photo up to 24 megapixels.')
                original.seek(0)
                photo = ImageOps.exif_transpose(original)
                if photo.mode == 'P' and 'transparency' in photo.info:
                    photo = photo.convert('RGBA')
                photo.thumbnail((1600, 1600))
                # New pixels only: strip EXIF (including location), XMP and ICC metadata.
                clean = Image.new('RGB', photo.size, '#ffffff')
                if 'A' in photo.getbands():
                    clean.paste(photo.convert('RGB'), mask=photo.getchannel('A'))
                else:
                    clean.paste(photo.convert('RGB'))
                out = BytesIO()
                clean.save(out, 'WEBP', quality=85, method=4)
                return out.getvalue(), clean.width, clean.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('This photo could not be read. Choose a JPEG, PNG or WebP image.') from None


def add(store, kind, item_id, data, caption=''):
    if not store.email:
        raise ValueError('Sign in to add finished photos.')
    store.revision(kind, item_id)
    caption = (caption or '').strip()
    if len(caption) > 200:
        raise ValueError('Keep the caption under 200 characters.')
    image, width, height = normalize_photo(data)
    with SessionLocal() as db:
        # Serialize the per-item limit across simultaneous uploads.
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        user = db.query(User).filter_by(email=store.email).with_for_update().first()
        if user is None:
            raise ValueError('Sign in to add finished photos.')
        if db.query(FinishedPhoto).filter_by(owner_email=store.email, kind=kind, item_id=item_id).count() >= MAX_PHOTOS:
            raise ValueError('This design already has eight photos. Remove one before adding another.')
        row = FinishedPhoto(id=uuid4().hex, owner_email=store.email, kind=kind, item_id=item_id,
                            caption=caption, image=image, width=width, height=height)
        db.add(row)
        db.commit()
        return row.id


def list_photos(store, kind=None, item_id=None, share_id=None):
    if share_id:
        source = WardrobeSharing(store).get(share_id)
        kind, item_id = source['kind'], source['revision_id']
        # Resolve the owner internally, never return their email to a viewer.
        from webapp.models import WardrobeShare
        with SessionLocal() as db:
            owner_key = db.get(WardrobeShare, share_id).owner_key
        owner = owner_key[len('account:'):] if owner_key.startswith('account:') else None
    else:
        store.revision(kind, item_id)
        owner = store.email
    if not owner:
        return []
    with SessionLocal() as db:
        rows = db.query(FinishedPhoto).filter_by(owner_email=owner, kind=kind, item_id=item_id).order_by(FinishedPhoto.created_at).all()
        return [dict(id=r.id, caption=r.caption, width=r.width, height=r.height,
                     url=f'/shared-photos/{share_id}/{r.id}' if share_id else f'/finished-photos/{r.id}') for r in rows]


def remove(store, photo_id):
    with SessionLocal() as db:
        row = db.query(FinishedPhoto).filter_by(id=photo_id, owner_email=store.email).first() if store.email else None
        if row is None:
            raise ValueError('This photo is no longer available.')
        db.delete(row)
        db.commit()


def image_for(store, photo_id, share_id=None):
    with SessionLocal() as db:
        row = db.get(FinishedPhoto, photo_id)
        if row is None:
            raise ValueError('Photo unavailable.')
        if share_id:
            sharing = WardrobeSharing(store)
            share = sharing._accessible(db, share_id)
            if (share.owner_key, share.kind, share.revision_id) != ('account:' + row.owner_email, row.kind, row.item_id):
                raise ValueError('Photo unavailable.')
        elif row.owner_email != store.email:
            raise ValueError('Photo unavailable.')
        return row.image


def register(app):
    def serve(request, photo_id, share_id=None):
        user = auth.current_user(request)
        try:
            data = image_for(Wardrobe(user['email'] if user else None), photo_id, share_id)
        except ValueError:
            raise HTTPException(404, 'Photo unavailable.')
        return Response(data, media_type='image/webp', headers={
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})

    @app.get('/finished-photos/{photo_id}')
    def own_photo(request: Request, photo_id: str):
        return serve(request, photo_id)

    @app.get('/shared-photos/{share_id}/{photo_id}')
    def shared_photo(request: Request, share_id: str, photo_id: str):
        return serve(request, photo_id, share_id)
