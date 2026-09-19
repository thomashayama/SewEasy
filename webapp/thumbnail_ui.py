"""One background browser renderer per page; durable images in the owner's library."""
import asyncio
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import mimetypes
from pathlib import Path
import shutil
from uuid import uuid4

from nicegui import app, ui
from nicegui.element import Element

from webapp.garment_catalog import standard_garments, thumbnail
from webapp.thumbnail_cache import ROOT, bundled_thumbnail, prepare_thumbnail_scene, preview_key, thumbnail_key, transparent_thumbnail
from webapp.wardrobe import same_items

SCENES = ROOT / 'tmp_gui/thumbnail-scenes'
SCENES.mkdir(parents=True, exist_ok=True)
app.add_static_files('/thumbnail-scenes', SCENES, max_cache_age=0)
(ROOT / 'assets/garment_thumbnails').mkdir(parents=True, exist_ok=True)
mimetypes.add_type('image/webp', '.webp')
app.add_static_files('/garment-thumbnails', ROOT / 'assets/garment_thumbnails')
PREPARER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='thumbnail-mesh')


class ThumbnailQueue(Element, component='thumbnail_renderer.js'):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.reload_library()
        self.pending, self.seen, self.views = deque(), {}, defaultdict(list)
        self.current = None
        self.scene = None
        self.busy = False
        self.online = False
        self.closed = False
        self.folder = SCENES / uuid4().hex
        ui.add_css('''
            .se-thumbnail {min-width:0; overflow:hidden;}
            .se-render-thumbnail {display:block; width:100%; height:100%; object-fit:contain;}
            .se-thumbnail-fallback {display:flex; justify-content:center; align-items:center; width:100%; height:100%; padding:10px;}
            .se-thumbnail-fallback svg {min-width:0; height:100%; max-width:100%; flex:1;}
        ''')
        self._props.update(job=None)
        self.on('available', self.available)
        self.on('thumbnail', self.received)
        self.on('failed', self.failed)
        self.client.on_disconnect(self.close)

    def reload_library(self):
        library = self.store.read()
        self.images = library.get('thumbnails', {})
        self.garments = {g['id']: g for g in library['garments'] + standard_garments()}
        self.outfits = {o['id']: o for o in library['outfits']}
        return library

    def image(self, key):
        image = self.images.get(key)
        return bundled_thumbnail(key) or (image if transparent_thumbnail(image) else None)

    def markup(self, items, key=None, image=None):
        image = image or self.image(key)
        if image:
            return f'<img src="{image}" alt="3D render on the default mannequin" class="se-render-thumbnail" draggable="false">'
        # The lightweight flat remains usable while its real render is queued.
        return '<div class="se-thumbnail-fallback">' + ''.join(thumbnail(g) for g in items[:3]) + '</div>'

    def visual(self, items, classes='', *, outfit_id=None, image=None):
        # Studio edits replace sidebar elements often; don't retain old design
        # snapshots just because a thumbnail view once referred to them.
        for key in list(self.views):
            live = [(view, snapshot) for view, snapshot in self.views[key] if not view.is_deleted]
            if live:
                self.views[key] = live
            else:
                del self.views[key]
        key = preview_key(items, self.garments, self.outfits, outfit_id)
        element = ui.html(self.markup(items, key, image)).classes('se-thumbnail ' + classes)
        if key and not image:
            self.views[key].append((element, deepcopy(items)))
        return element

    def enqueue(self, kind, revision_id, items):
        key = thumbnail_key(kind, revision_id)
        if (key not in self.seen or not same_items(self.seen[key], items)) and not self.image(key):
            self.seen[key] = deepcopy(items)
            self.pending.append((key, deepcopy(items)))

    def enqueue_library(self, standards=False):
        library = self.reload_library()
        # Backfill both tabs, not only the currently visible cards.
        for garment in library['garments'] + (standard_garments() if standards else []):
            self.enqueue('garment', garment['id'], [garment])
        for outfit in library['outfits']:
            self.enqueue('outfit', outfit['revision_id'], outfit['garments'])
        if self.online and not self.closed:
            ui.timer(.1, self.next, once=True)

    async def available(self):
        self.online = True
        await self.next()

    async def next(self):
        if self.closed or self.busy or self.current or not self.online:
            return
        self.busy = True
        try:
            while self.pending and not self.closed:
                self.current = self.pending.popleft()
                key, items = self.current
                # Another tab may have completed it in the meantime.
                self.reload_library()
                kind, identity = key.split(':', 1)
                saved = (self.garments if kind == 'garment' else self.outfits).get(identity)
                saved_items = ([saved] if kind == 'garment' else saved['garments']) if saved else []
                if not same_items(items, saved_items):
                    continue
                if self.image(key):
                    self.refresh_images(key)
                    continue
                # Revision attachment IDs are data, never filesystem paths.
                target = self.folder / f'{uuid4().hex}.json'
                self.scene = target
                try:
                    await asyncio.get_running_loop().run_in_executor(PREPARER, prepare_thumbnail_scene, items, target)
                except Exception as error:
                    print(f'Thumbnail preparation failed: {error}')
                    self.remove_scene()
                    continue
                if self.closed:
                    shutil.rmtree(self.folder, ignore_errors=True)
                    return
                self._props['job'] = dict(key=key, url=f'/thumbnail-scenes/{self.folder.name}/{target.name}')
                self.update()
                return  # Browser completion advances the queue.
            self.current = None
            self._props['job'] = None
            self.update()
        finally:
            self.busy = False

    def refresh_images(self, key):
        self.views[key] = [(view, items) for view, items in self.views[key] if not view.is_deleted]
        for view, items in self.views[key]:
            current_key = preview_key(items, self.garments, self.outfits,
                                      key.split(':', 1)[1] if key.startswith('outfit:') else None)
            view.set_content(self.markup(items, current_key))

    async def received(self, event):
        if self.closed or not self.current or event.args.get('key') != self.current[0] or event.args.get('url') != (self._props.get('job') or {}).get('url'):
            return
        key = self.current[0]
        try:
            kind, revision_id = key.split(':', 1)
            self.images[key] = self.store.save_thumbnail(kind, revision_id, event.args.get('image'), items=self.current[1])
            self.refresh_images(key)
        except ValueError as error:
            print(f'Thumbnail was not saved: {error}')
        finally:
            self.remove_scene()
            self.current = None
        self.enqueue_library()
        await self.next()

    async def failed(self, event):
        if self.current and event.args.get('key') == self.current[0] and event.args.get('url') == (self._props.get('job') or {}).get('url'):
            print(f'Browser thumbnail failed: {event.args.get("message", "Unknown error")}')
            self.remove_scene()
            self.current = None
            if event.args.get('fatal'):
                self.online = False
            await self.next()

    def remove_scene(self):
        if self.scene is None:
            return
        try:
            self.scene.unlink(missing_ok=True)
        except PermissionError:
            # Windows can still have an HTTP response holding the file open
            # when the browser reports a fetch failure. Page cleanup retries.
            pass
        self.scene = None

    def close(self):
        self.closed = True
        self.pending.clear()
        if not self.busy:
            shutil.rmtree(self.folder, ignore_errors=True)
