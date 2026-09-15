"""One background browser renderer per page; durable images in the owner's library."""
import asyncio
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import shutil
from uuid import uuid4

from nicegui import app, ui
from nicegui.element import Element

from webapp.garment_catalog import standard_garments, thumbnail
from webapp.thumbnail_cache import ROOT, bundled_thumbnail, prepare_thumbnail_scene, thumbnail_key

SCENES = ROOT / 'tmp_gui/thumbnail-scenes'
SCENES.mkdir(parents=True, exist_ok=True)
app.add_static_files('/thumbnail-scenes', SCENES, max_cache_age=0)
(ROOT / 'assets/garment_thumbnails').mkdir(parents=True, exist_ok=True)
app.add_static_files('/garment-thumbnails', ROOT / 'assets/garment_thumbnails')
PREPARER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='thumbnail-mesh')


class ThumbnailQueue(Element, component='thumbnail_renderer.js'):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.images = store.read().get('thumbnails', {})
        self.pending, self.seen, self.views = deque(), set(), defaultdict(list)
        self.current = None
        self.busy = False
        self.online = False
        self.closed = False
        self.folder = SCENES / uuid4().hex
        ui.add_css('''
            .se-thumbnail {min-width:0; overflow:hidden;}
            .se-render-thumbnail {display:block; width:100%; height:100%; object-fit:contain; background:#e8f0f5;}
            .se-thumbnail-fallback {display:flex; justify-content:center; align-items:center; width:100%; height:100%; padding:10px;}
            .se-thumbnail-fallback svg {min-width:0; height:100%; max-width:100%; flex:1;}
        ''')
        self._props.update(job=None)
        self.on('available', self.available)
        self.on('thumbnail', self.received)
        self.on('failed', self.failed)
        self.client.on_disconnect(self.close)

    def image(self, items):
        key = thumbnail_key(items)
        return bundled_thumbnail(key) or self.images.get(key)

    def markup(self, items):
        image = self.image(items)
        if image:
            return f'<img src="{image}" alt="3D render on the default mannequin" class="se-render-thumbnail" draggable="false">'
        # The lightweight flat remains usable while its real render is queued.
        return '<div class="se-thumbnail-fallback">' + ''.join(thumbnail(g) for g in items[:3]) + '</div>'

    def visual(self, items, classes=''):
        # Studio edits replace sidebar elements often; don't retain old design
        # snapshots just because a thumbnail view once referred to them.
        for key in list(self.views):
            live = [(view, snapshot) for view, snapshot in self.views[key] if not view.is_deleted]
            if live:
                self.views[key] = live
            else:
                del self.views[key]
        element = ui.html(self.markup(items)).classes('se-thumbnail ' + classes)
        self.views[thumbnail_key(items)].append((element, deepcopy(items)))
        return element

    def enqueue(self, items):
        key = thumbnail_key(items)
        if key not in self.seen and not self.image(items):
            self.seen.add(key)
            self.pending.append((key, deepcopy(items)))

    def enqueue_library(self, standards=False):
        library = self.store.read()
        # Backfill both tabs, not only the currently visible cards.
        for garment in library['garments'] + (standard_garments() if standards else []):
            self.enqueue([garment])
        for outfit in library['outfits']:
            self.enqueue(outfit['garments'])
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
                self.images.update(self.store.read().get('thumbnails', {}))
                if self.image(items):
                    self.refresh_images(key)
                    continue
                target = self.folder / f'{key}.json'
                try:
                    await asyncio.get_running_loop().run_in_executor(PREPARER, prepare_thumbnail_scene, items, target)
                except Exception as error:
                    print(f'Thumbnail preparation failed: {error}')
                    continue
                if self.closed:
                    shutil.rmtree(self.folder, ignore_errors=True)
                    return
                self._props['job'] = dict(key=key, url=f'/thumbnail-scenes/{self.folder.name}/{key}.json')
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
            view.set_content(self.markup(items))

    async def received(self, event):
        if self.closed or not self.current or event.args.get('key') != self.current[0]:
            return
        key = self.current[0]
        try:
            self.images[key] = self.store.save_thumbnail(key, event.args.get('image'))
            self.refresh_images(key)
        except ValueError as error:
            print(f'Thumbnail was not saved: {error}')
        finally:
            (self.folder / f'{key}.json').unlink(missing_ok=True)
            self.current = None
        await self.next()

    async def failed(self, event):
        if self.current and event.args.get('key') == self.current[0]:
            print(f'Browser thumbnail failed: {event.args.get("message", "Unknown error")}')
            (self.folder / f'{self.current[0]}.json').unlink(missing_ok=True)
            self.current = None
            if event.args.get('fatal'):
                self.online = False
            await self.next()

    def close(self):
        self.closed = True
        self.pending.clear()
        if not self.busy:
            shutil.rmtree(self.folder, ignore_errors=True)
