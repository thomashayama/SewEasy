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
from webapp.thumbnail_cache import ROOT, bundled_thumbnail, normalize_image, prepare_thumbnail_scene, preview_key, thumbnail_key, SIZE
from webapp.thumbnail_migration import LEGACY_BODIES, legacy_key


def raster(size=SIZE, color='#a6bfd7'):
    out = BytesIO()
    Image.new('RGB', size, color).save(out, format='WEBP')
    return 'data:image/webp;base64,' + base64.b64encode(out.getvalue()).decode()


class ThumbnailTest(unittest.TestCase):
    def test_legacy_images_attach_to_all_matching_revisions_once(self):
        for body in LEGACY_BODIES:
            with self.subTest(body=body):
                storage = {}
                store = Wardrobe(storage=storage)
                source = starter_item('Pants')
                one = store.save_garment('Navy trousers', source['params'], source['appearance'])
                two = store.save_garment('Other trousers', source['params'], source['appearance'])
                outfit = store.save_outfit('Work', [one['id']])
                image = raster()
                old_key = legacy_key([one], body)
                storage['wardrobe']['thumbnails'] = {old_key: image}
                images = store.read()['thumbnails']
                self.assertEqual(images[thumbnail_key('garment', one['id'])], image)
                self.assertEqual(images[thumbnail_key('garment', two['id'])], image)
                self.assertEqual(images[thumbnail_key('outfit', outfit['revision_id'])], image)
                self.assertNotIn(old_key, images)
                self.assertEqual(storage['wardrobe']['thumbnails'], images)
                with patch('webapp.thumbnail_migration.legacy_key', side_effect=AssertionError('Rehashed after migration')):
                    self.assertEqual(store.read()['thumbnails'], images)

    def test_every_standard_has_a_current_nonblank_bundled_render(self):
        from PIL import ImageStat
        for item in standard_garments():
            with self.subTest(garment=item['name']):
                key = thumbnail_key('garment', item['id'])
                with patch('webapp.thumbnail_cache.Path.read_bytes', side_effect=AssertionError('Read body file')):
                    self.assertEqual(bundled_thumbnail(key), f'/garment-thumbnails/{item["standard"]}.webp')
                with Image.open(ROOT / 'assets/garment_thumbnails' / f'{item["standard"]}.webp') as image:
                    self.assertEqual(image.size, SIZE)
                    self.assertGreater(min(ImageStat.Stat(image.convert('RGB')).stddev), 5)

    def test_saved_ids_keep_images_separate_even_when_designs_are_identical(self):
        store = Wardrobe(storage={})
        source = starter_item('Pants')
        one = store.save_garment('Trousers', source['params'], source['appearance'])
        two = store.save_garment('Trousers', source['params'], source['appearance'])
        outfit = store.save_outfit('Work', [one['id']])
        first = store.save_thumbnail('garment', one['id'], raster())
        second = store.save_thumbnail('garment', two['id'], raster(color='#ff0000'))
        images = store.read()['thumbnails']
        self.assertEqual(images[thumbnail_key('garment', one['id'])], first)
        self.assertEqual(images[thumbnail_key('garment', two['id'])], second)
        self.assertNotEqual(first, second)
        self.assertNotIn(thumbnail_key('outfit', outfit['revision_id']), images)

    def test_unsaved_edits_and_reordered_outfits_do_not_show_an_old_revision_image(self):
        store = Wardrobe(storage={})
        records = [store.save_garment(g['name'], g['params'], g['appearance']) for g in
                   (starter_item('DressShirt'), starter_item('Pants'))]
        outfit = store.save_outfit('Work', [g['id'] for g in records])
        garments = {g['id']: g for g in records}
        outfits = {outfit['revision_id']: outfit}
        self.assertEqual(preview_key([records[0]], garments, outfits), thumbnail_key('garment', records[0]['id']))
        self.assertEqual(preview_key(records, garments, outfits, outfit['revision_id']),
                         thumbnail_key('outfit', outfit['revision_id']))
        edited = deepcopy(records[0])
        edited['appearance']['fabric_color'] = '#ff0000'
        self.assertIsNone(preview_key([edited], garments, outfits))
        self.assertIsNone(preview_key([edited, records[1]], garments, outfits, outfit['revision_id']))
        self.assertIsNone(preview_key(list(reversed(records)), garments, outfits, outfit['revision_id']))
        self.assertIsNone(preview_key([starter_item('Shirt')], garments, outfits))

    def test_cache_survives_reload_without_changing_versions_or_outfits(self):
        storage = {}
        store = Wardrobe(storage=storage)
        source = starter_item('Pants')
        garment = store.save_garment('Navy trousers', source['params'], source['appearance'])
        outfit = store.save_outfit('Work', [garment['id']])
        key = thumbnail_key('garment', garment['id'])
        store.save_thumbnail('garment', garment['id'], raster())
        loaded = Wardrobe(storage=storage).read()
        self.assertTrue(loaded['thumbnails'][key].startswith('data:image/webp;base64,'))
        self.assertEqual(loaded['garments'], [garment])
        self.assertEqual(loaded['outfits'], [outfit])
        self.assertNotEqual(thumbnail_key('outfit', outfit['revision_id']), key)

    def test_late_render_attaches_to_its_revision_and_account_images_are_private(self):
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
            key = thumbnail_key('outfit', outfit['revision_id'])
            store.save_thumbnail('outfit', outfit['revision_id'], raster())
            self.assertIn(key, Wardrobe('a@example.com').read()['thumbnails'])
            self.assertNotIn('thumbnails', Wardrobe('b@example.com').read())
            with self.assertRaises(ValueError):
                Wardrobe('b@example.com').save_thumbnail('outfit', outfit['revision_id'], raster())
            current = store.save_outfit('Work', [garments[0]['id']])
            current_image = store.save_thumbnail('outfit', current['revision_id'], raster(color='#ff0000'))
            store.save_thumbnail('outfit', outfit['revision_id'], raster())
            self.assertEqual(store.read()['thumbnails'][thumbnail_key('outfit', current['revision_id'])], current_image)
            self.assertIn(key, store.read()['thumbnails'])
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
