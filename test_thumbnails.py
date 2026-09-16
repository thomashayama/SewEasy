"""Thumbnail identity, private persistence, default-body drafting and image validation."""
import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User
from webapp.wardrobe import Wardrobe
from webapp.garment_catalog import standard_garments, starter_item
from webapp.thumbnail_cache import ROOT, _default_body_key, bundled_thumbnail, cached_thumbnail, normalize_image, prepare_thumbnail_scene, thumbnail_key, SIZE


def raster(size=SIZE):
    out = BytesIO()
    Image.new('RGB', size, '#a6bfd7').save(out, format='WEBP')
    return 'data:image/webp;base64,' + base64.b64encode(out.getvalue()).decode()


class ThumbnailTest(unittest.TestCase):
    def test_windows_and_linux_checkouts_use_the_same_six_bundled_images(self):
        body = (ROOT / 'assets/bodies/mean_all.yaml').read_bytes().replace(b'\r\n', b'\n')
        keys = []
        try:
            for contents in (body, body.replace(b'\n', b'\r\n')):
                _default_body_key.cache_clear()
                with patch('webapp.thumbnail_cache.Path.read_bytes', return_value=contents):
                    current = [thumbnail_key([g]) for g in standard_garments()]
                    self.assertTrue(all(bundled_thumbnail(key) for key in current))
                    keys.append(current)
            self.assertEqual(keys[0], keys[1])
        finally:
            _default_body_key.cache_clear()

    def test_existing_windows_images_are_reused_and_retained_on_the_next_save(self):
        store = Wardrobe(storage={})
        source = starter_item('Pants')
        one = store.save_garment('Navy trousers', source['params'], source['appearance'])
        source['appearance']['fabric_color'] = '#123456'
        two = store.save_garment('Other trousers', source['params'], source['appearance'])
        image = raster()
        old_key = thumbnail_key([one], legacy_windows=True)
        with store._edit() as library:
            library['thumbnails'] = {old_key: image}
        self.assertEqual(cached_thumbnail(store.read()['thumbnails'], [one]), image)
        store.save_thumbnail(thumbnail_key([two]), image)
        images = store.read()['thumbnails']
        self.assertIn(thumbnail_key([one]), images)
        self.assertNotIn(old_key, images)
        self.assertIn(thumbnail_key([two]), images)

    def test_every_standard_has_a_current_nonblank_bundled_render(self):
        from PIL import ImageStat
        for item in standard_garments():
            with self.subTest(garment=item['name']):
                key = thumbnail_key([item])
                self.assertIsNotNone(bundled_thumbnail(key))
                with Image.open(ROOT / 'assets/garment_thumbnails' / f'{key}.webp') as image:
                    self.assertEqual(image.size, SIZE)
                    self.assertGreater(min(ImageStat.Stat(image.convert('RGB')).stddev), 5)

    def test_identity_ignores_names_versions_and_body_but_tracks_colors_and_outfit_order(self):
        shirt, pants = starter_item('DressShirt'), starter_item('Pants')
        key = thumbnail_key([shirt])
        shirt.update(name='Renamed', version=5, id='saved', body={'height': 200})
        shirt['appearance']['panel_colors'] = {}
        self.assertEqual(thumbnail_key([shirt]), key)
        shirt['appearance']['panel_colors']['left_collar'] = '#ff0000'
        self.assertNotEqual(thumbnail_key([shirt]), key)
        self.assertNotEqual(thumbnail_key([shirt, pants]), thumbnail_key([pants, shirt]))
        self.assertNotEqual(thumbnail_key([shirt, pants]), thumbnail_key([shirt]))

    def test_cache_survives_reload_without_changing_versions_or_outfits(self):
        storage = {}
        store = Wardrobe(storage=storage)
        source = starter_item('Pants')
        garment = store.save_garment('Navy trousers', source['params'], source['appearance'])
        outfit = store.save_outfit('Work', [garment['id']])
        key = thumbnail_key([garment])
        store.save_thumbnail(key, raster())
        loaded = Wardrobe(storage=storage).read()
        self.assertTrue(loaded['thumbnails'][key].startswith('data:image/webp;base64,'))
        self.assertEqual(loaded['garments'], [garment])
        self.assertEqual(loaded['outfits'], [outfit])
        self.assertEqual(thumbnail_key(outfit['garments']), key)

    def test_outdated_outfit_result_is_rejected_and_account_images_are_private(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        with sessions() as db:
            db.add_all([User(email='a@example.com'), User(email='b@example.com')]); db.commit()
        with patch('webapp.wardrobe.SessionLocal', sessions):
            store = Wardrobe('a@example.com')
            first, second = starter_item('DressShirt'), starter_item('Pants')
            first['appearance']['fabric_color'] = '#102030'
            garments = [store.save_garment(g['name'], g['params'], g['appearance']) for g in (first, second)]
            outfit = store.save_outfit('Work', [g['id'] for g in garments])
            key = thumbnail_key(outfit['garments'])
            store.save_thumbnail(key, raster())
            self.assertIn(key, Wardrobe('a@example.com').read()['thumbnails'])
            self.assertNotIn('thumbnails', Wardrobe('b@example.com').read())
            with self.assertRaises(ValueError):
                Wardrobe('b@example.com').save_thumbnail(key, raster())
            store.save_outfit('Work', [garments[0]['id']])
            with self.assertRaises(ValueError):
                store.save_thumbnail(key, raster())
        engine.dispose()

    def test_invalid_or_oversize_uploads_are_rejected(self):
        for value in ('data:image/svg+xml,<svg/>', 'data:image/webp;base64,!!!', raster((32, 32)),
                      'data:image/webp;base64,' + 'a' * 400_000):
            with self.subTest(value=value[:35]), self.assertRaises(ValueError):
                normalize_image(value)

    def test_preparation_uses_default_body_and_preserves_panel_appearance(self):
        from gui.gui_pattern import GUIPattern
        from gui.browser_drape import snapshot_scene
        item = starter_item('DressShirt')
        item['body'] = {'height': 210}  # Must never enter the standardized scene.
        item['appearance']['panel_colors'] = {'right_ftorso': '#123456'}
        original = deepcopy(item)
        captured = []
        def prepared(pattern, target):
            captured.append(snapshot_scene(pattern))
            return target
        with TemporaryDirectory() as tmp, patch('gui.browser_drape.prepare_scene', side_effect=prepared):
            prepare_thumbnail_scene([item], Path(tmp) / 'scene.json')
        default = GUIPattern(draft=False)
        try:
            self.assertEqual(captured[0].measurements, default.body_params.params)
            self.assertEqual(captured[0].colors['g0__right_ftorso'], '#123456')
            self.assertTrue(captured[0].pattern.pattern['panels'])
            self.assertEqual(item, original)
        finally:
            default.release()


if __name__ == '__main__':
    unittest.main()
