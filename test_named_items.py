"""Named editing, independent copies, migration and stable thumbnail attachments."""
from copy import deepcopy
import unittest

from webapp.wardrobe import Wardrobe, normalize_library
from webapp.garment_catalog import standard_garments, studio_snapshot
from test_wardrobe import PARAMS, LOOK
from test_thumbnails import raster


class NamedItemsTest(unittest.TestCase):
    def test_save_updates_id_copy_defaults_are_unique_and_names_do_not_overwrite(self):
        store = Wardrobe(storage={})
        shirt = store.save_garment('Dress shirt', PARAMS, LOOK)
        renamed = store.save_garment('Pinstripe dress shirt', PARAMS, LOOK, parent_id=shirt['id'])
        self.assertEqual(renamed['id'], shirt['id'])
        copies = [store.import_fork('garment', renamed, {'name': renamed['name']}) for _ in range(2)]
        self.assertEqual([g['name'] for g in copies], ['Pinstripe dress shirt (copy)', 'Pinstripe dress shirt (copy 2)'])
        self.assertEqual(len(store.read()['garments']), 3)
        for name in ('Pinstripe dress shirt', ' PINSTRIPE DRESS SHIRT '):
            with self.assertRaisesRegex(ValueError, 'already in use'):
                store.save_garment(name, PARAMS, LOOK, new=True)
        with self.assertRaisesRegex(ValueError, 'name'):
            store.import_fork('garment', renamed, {}, name='')
        with self.assertRaisesRegex(ValueError, 'not in your library'):
            Wardrobe(storage={}).save_garment('Stolen', PARAMS, LOOK, parent_id=shirt['id'])
        self.assertEqual(store.revision('garment', shirt['id']), renamed)

    def test_outfit_adjustments_do_not_change_or_add_library_garments(self):
        store = Wardrobe(storage={})
        shirt = store.save_garment('Dress shirt', PARAMS, LOOK)
        outfit = store.save_outfit('Work', [shirt['id']])
        changed = deepcopy(outfit['garments'])
        changed[0]['appearance']['fabric_color'] = '#ff0000'
        changed.append(standard_garments()[3])
        saved = store.save_outfit('Work', items=changed, parent_id=outfit['id'])
        self.assertEqual(saved['id'], outfit['id'])
        self.assertEqual(len(store.read()['outfits']), 1)
        self.assertEqual(store.read()['garments'], [shirt])
        copied = store.import_fork('outfit', saved, {'name': 'Work'})
        self.assertEqual(copied['name'], 'Work (copy)')
        self.assertNotEqual(copied['id'], saved['id'])
        store.save_outfit('Work', [shirt['id']], parent_id=saved['id'])
        self.assertEqual(store.revision('outfit', copied['id'])['garments'], saved['garments'])
        self.assertEqual(store.read()['garments'], [shirt])

    def test_thumbnail_survives_rename_but_not_design_change_or_late_render(self):
        store = Wardrobe(storage={})
        shirt = store.save_garment('Dress shirt', PARAMS, LOOK)
        image = store.save_thumbnail('garment', shirt['id'], raster(), items=[shirt])
        key = 'garment:' + shirt['id']
        rename = store.save_garment('Oxford', PARAMS, LOOK, parent_id=shirt['id'])
        self.assertEqual(store.read()['thumbnails'][key], image)
        updated = store.save_garment('Oxford', PARAMS, dict(LOOK, fabric_color='#ff0000'), parent_id=rename['id'])
        self.assertNotIn(key, store.read()['thumbnails'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            store.save_thumbnail('garment', shirt['id'], raster(), items=[shirt])
        store.save_thumbnail('garment', updated['id'], raster(color='#ff0000'), items=[updated])
        self.assertIn(key, store.read()['thumbnails'])

    def test_legacy_outfit_revisions_become_named_items_without_losing_images(self):
        g = dict(id='g', lineage_id='g', name='Shirt', version=1, params=PARAMS, appearance=LOOK)
        first = dict(id='outfit', revision_id='r1', version=1, name='Work', garments=[g])
        latest = dict(first, revision_id='r2', version=2)
        legacy = dict(garments=[g], outfits=[latest], outfit_revisions=[first, latest],
                      thumbnails={'outfit:r1': 'old-image', 'outfit:r2': 'new-image'})
        store = Wardrobe(storage={'wardrobe': legacy})
        data = store.read()
        self.assertEqual([o['id'] for o in data['outfits']], ['r1', 'r2'])
        self.assertEqual([o['name'] for o in data['outfits']], ['Work (copy)', 'Work'])
        self.assertEqual(data['thumbnails'], legacy['thumbnails'])
        self.assertEqual(data, normalize_library(data))
        self.assertEqual(store.revision('outfit', 'r1')['garments'][0]['params'], PARAMS)

    def test_single_garment_outfit_and_garment_editing_remain_distinct_on_reload(self):
        g = standard_garments()[0]
        garment = studio_snapshot([g], editor_mode='garment')
        outfit = studio_snapshot([g], editor_mode='outfit', outfit_revision_id='outfit-id', outfit_updated_at='saved-time')
        self.assertEqual(garment['editor_mode'], 'garment')
        self.assertEqual(outfit['editor_mode'], 'outfit')
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from gui.callbacks import GUIState
        state = GUIState.__new__(GUIState)
        state.pattern_state = Mock()
        with patch('gui.callbacks.app', SimpleNamespace(storage=SimpleNamespace(user={'pending_design': outfit}))):
            state._restore_pending_design()
        self.assertEqual(state._editor_mode, 'outfit')
        self.assertEqual(state._outfit_updated_at, 'saved-time')
        other = studio_snapshot([g], previous=outfit, source_share='shared-source')
        self.assertEqual(other['source_share'], 'shared-source')
        self.assertIsNone(other['outfit_revision_id'])


if __name__ == '__main__':
    unittest.main()
