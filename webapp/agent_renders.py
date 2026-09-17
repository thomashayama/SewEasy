"""CPU draft artifacts and browser-only 3D rendering for agent-created items."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from webapp.config import APP_URL
from webapp.db import SessionLocal
from webapp.models import AgentRender
from webapp.wardrobe import Wardrobe

WORKERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agent-draft')
CAPACITY = asyncio.Semaphore(4)
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff'}


def artifacts(items, three_d):
    from gui.gui_pattern import GUIPattern
    from gui.browser_drape import prepare_scene
    import cairosvg
    pattern = GUIPattern(draft=False)
    try:
        pattern.load_outfit(items)
        pattern.reload_garment()
        svg = pattern.svg_path().read_text(encoding='utf-8')
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=1200)
        scene = None
        if three_d:
            with TemporaryDirectory(prefix='seweasy-agent-') as temp:
                path = prepare_scene(pattern, Path(temp) / 'scene.json')
                if path.stat().st_size > 32_000_000:
                    raise ValueError('This scene is too large for an interactive preview.')
                scene = gzip.compress(path.read_bytes())
        return svg, png, scene
    finally:
        pattern.release()


async def render(email, kind, item_id, three_d=True):
    store = Wardrobe(email)
    item = store.revision(kind, item_id)
    items = [item] if kind == 'garment' else item['garments']
    if CAPACITY.locked():
        raise ValueError('The renderer is busy. Try again shortly.')
    async with CAPACITY:
        with SessionLocal() as db:
            db.query(AgentRender).filter(AgentRender.expires_at < datetime.utcnow()).delete()
            if db.query(AgentRender).filter_by(owner_email=email).count() >= 20:
                raise ValueError('You have 20 active render jobs. Delete an older job or wait for it to expire.')
            db.commit()
        svg, png, scene = await asyncio.get_running_loop().run_in_executor(WORKERS, artifacts, items, three_d)
        identity = secrets.token_urlsafe(32)
        with SessionLocal() as db:
            db.add(AgentRender(id=identity, owner_email=email, kind=kind, item_id=item_id, items=items,
                              state='awaiting_browser' if three_d else 'ready_2d', svg=svg, png=png, scene=scene,
                              expires_at=datetime.utcnow() + timedelta(hours=24)))
            db.commit()
    return status(email, identity)


def find(db, identity, email=None):
    query = db.query(AgentRender).filter_by(id=identity).filter(AgentRender.expires_at > datetime.utcnow())
    if email is not None:
        query = query.filter_by(owner_email=email)
    row = query.first()
    if row is None:
        raise ValueError('Render unavailable or expired.')
    return row


def status(email, identity):
    with SessionLocal() as db:
        row = find(db, identity, email)
        root = f'{APP_URL}/agent-render/{identity}'
        return dict(id=identity, state=row.state, error=row.error, expires_at=row.expires_at.isoformat() + 'Z',
                    pattern_svg_url=root + '/pattern.svg', pattern_png_url=root + '/pattern.png',
                    viewer_url=root, thumbnail_url=root + '/thumbnail.webp' if row.state == 'ready_3d' else None,
                    next_step='Open viewer_url in a WebGPU browser, then call get_render for the completed image.'
                    if row.state in ('awaiting_browser', 'failed') else None)


def delete(email, identity):
    with SessionLocal() as db:
        row = find(db, identity, email)
        db.delete(row)
        db.commit()
    return {'deleted': identity}


def image(email, identity, view):
    with SessionLocal() as db:
        row = find(db, identity, email)
        if view == '3d':
            if not row.thumbnail:
                return None
            return row.thumbnail.split(',', 1)[1], 'image/webp'
        return base64.b64encode(row.png).decode(), 'image/png'


def register(app):
    @app.get('/agent-render/{identity}', response_class=HTMLResponse)
    def viewer(identity: str):
        with SessionLocal() as db:
            try:
                find(db, identity)
            except ValueError:
                raise HTTPException(404, 'Render unavailable or expired.')
        page = (Path(__file__).parent / 'agent_viewer.html').read_text(encoding='utf-8')
        return HTMLResponse(page, headers={**HEADERS, 'Content-Security-Policy':
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"})

    @app.get('/agent-render/{identity}/{asset}')
    def asset(identity: str, asset: str):
        with SessionLocal() as db:
            try:
                row = find(db, identity)
            except ValueError:
                raise HTTPException(404, 'Render unavailable or expired.')
            if asset == 'scene.json' and row.scene:
                return Response(gzip.decompress(row.scene), media_type='application/json', headers=HEADERS)
            if asset == 'pattern.svg':
                return Response(row.svg, media_type='image/svg+xml', headers={**HEADERS, 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"})
            if asset == 'pattern.png':
                return Response(row.png, media_type='image/png', headers=HEADERS)
            if asset == 'thumbnail.webp' and row.thumbnail:
                return Response(base64.b64decode(row.thumbnail.split(',', 1)[1]), media_type='image/webp', headers=HEADERS)
            if asset == 'status':
                return {**status(row.owner_email, identity), 'has_scene': row.scene is not None}
            raise HTTPException(404, 'Artifact unavailable.')

    @app.post('/agent-render/{identity}/complete')
    @app.post('/agent-render/{identity}/failed')
    async def complete(identity: str, request: Request):
        # The random, short-lived render URL is a capability for this job only.
        if request.headers.get('origin') and request.headers['origin'].rstrip('/') != APP_URL:
            raise HTTPException(403, 'Invalid origin.')
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 410_000:
                raise HTTPException(413, 'Image too large.')
        try:
            body = json.loads(data)
            with SessionLocal() as db:
                row = find(db, identity)
                if not row.scene:
                    raise ValueError('This job has no 3D scene.')
                if request.url.path.endswith('/failed'):
                    if row.state != 'ready_3d':
                        row.state = 'failed'
                        row.error = str(body.get('error', 'Browser rendering failed.'))[:500]
                        db.commit()
                    return {'state': row.state}
                from webapp.thumbnail_cache import normalize_image
                thumbnail = normalize_image(body.get('image'))
                Wardrobe(row.owner_email).save_thumbnail(row.kind, row.item_id, thumbnail, items=row.items)
                row.thumbnail = thumbnail
                row.state = 'ready_3d'
                row.error = None
                db.commit()
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(400, str(error))
        return {'state': 'ready_3d'}
