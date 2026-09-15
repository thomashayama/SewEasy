"""Home/studio navigation keeps saved garment versions and working drafts separate."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from webapp.garment_catalog import STARTERS, draft_items, library_matches, starter_item, studio_snapshot, thumbnail
from webapp.wardrobe import Wardrobe


class HomeLibraryTest(unittest.TestCase):
    def test_open_outfit_copies_all_versions_and_retains_measurements(self):
        storage = {}
        store = Wardrobe(storage=storage)
        shirt, pants = starter_item('DressShirt'), starter_item('Pants')
        shirt['appearance']['panel_fabrics'] = {'right_ftorso': {'kind': 'gingham', 'fg': '#123456'}}
        versions = [store.save_garment(g['name'], g['params'], g['appearance']) for g in (shirt, pants)]
        outfit = store.save_outfit('Oxford look', [g['id'] for g in versions])
        old = dict(body={'height': 180, 'neck_w': 20}, skin='#abcabc', active_garment=4)
        opened = studio_snapshot(outfit['garments'], outfit['name'], old)
        self.assertEqual(opened['body'], old['body'])
        self.assertEqual(opened['outfit_name'], 'Oxford look')
        self.assertEqual(opened['active_garment'], 0)
        self.assertEqual(opened['appearance'], shirt['appearance'])
        opened['outfit'][0]['appearance']['panel_fabrics']['right_ftorso']['fg'] = '#ffffff'
        opened['body']['height'] = 190
        self.assertEqual(old['body']['height'], 180)
        self.assertEqual(store.read()['outfits'][0]['garments'][0]['appearance'], shirt['appearance'])
        self.assertEqual(store.read()['garments'][0]['appearance'], shirt['appearance'])

    def test_starters_are_independent_and_set_the_correct_garment_sections(self):
        for kind, _, _, _ in STARTERS:
            first, second = starter_item(kind), starter_item(kind)
            self.assertEqual(first, second)
            meta = first['params']['meta']
            self.assertEqual(meta['bottom' if kind in ('Pants', 'SkirtCircle') else 'upper']['v'], kind)
            self.assertEqual(meta['upper' if kind in ('Pants', 'SkirtCircle') else 'bottom']['v'], None)
            first['params']['meta']['upper']['v'] = 'changed'
            self.assertNotEqual(first['params'], second['params'])
        with self.assertRaises(ValueError):
            starter_item('../../private')

    def test_home_accepts_single_garment_and_outfit_draft_snapshots(self):
        garment = starter_item('DressShirt')
        single = dict(design=garment['params'], fabric='#123456', appearance={'fabric_color': '#123456'})
        items = draft_items(single)
        self.assertEqual(items[0]['appearance']['fabric_color'], '#123456')
        multiple = studio_snapshot([garment, starter_item('Pants')])
        self.assertEqual(len(draft_items(multiple)), 2)
        self.assertEqual(draft_items({}), [])

    def test_search_matches_outfit_contents_and_preserves_versions(self):
        rows = [dict(id='1', name='Monday', garments=[{'name': 'Oxford'}]),
                dict(id='2', name='Weekend', garments=[{'name': 'Trousers'}])]
        self.assertEqual([r['id'] for r in library_matches(rows, '  OXFORD ')], ['1'])
        self.assertEqual([r['id'] for r in library_matches(rows, '')], ['2', '1'])
        self.assertEqual(library_matches(rows, 'missing'), [])

    def test_library_svg_uses_valid_colors_and_unique_print_ids(self):
        item = starter_item('DressShirt')
        item['params']['fabric']['kind']['v'] = 'gingham'
        item['params']['fabric']['fg']['v'] = '"><script>alert(1)</script>'
        item['params']['fabric']['bg']['v'] = '#123456'
        svg = thumbnail(item)
        self.assertNotIn('<script>', svg)
        self.assertIn('#123456', svg)
        self.assertNotEqual(svg, thumbnail(item))
        ET.fromstring(svg)


class HomeNavigationTest(unittest.TestCase):
    def test_logo_stashes_before_navigating_and_keeps_failed_stash_in_studio(self):
        from gui.callbacks import GUIState
        state = GUIState.__new__(GUIState)
        calls = []
        state.stash_pending_design = lambda: calls.append('stash') or True
        with patch('gui.callbacks.ui.navigate.to', side_effect=lambda url: calls.append(url)):
            state.go_home()
        self.assertEqual(calls, ['stash', '/'])
        state.stash_pending_design = lambda: False
        with patch('gui.callbacks.ui.navigate.to') as navigate, patch('gui.callbacks.ui.notify'):
            state.go_home()
            navigate.assert_not_called()

    def test_resume_does_not_consume_home_draft_or_mutate_saved_storage(self):
        from gui.callbacks import GUIState
        snapshot = studio_snapshot([starter_item('DressShirt')], 'Test outfit', {'body': {'height': 181}})
        storage = {'pending_design': deepcopy(snapshot)}
        state = GUIState.__new__(GUIState)
        state.pattern_state = Mock()
        with patch('gui.callbacks.app', SimpleNamespace(storage=SimpleNamespace(user=storage))):
            state._restore_pending_design()
            state._restore_pending_design()
        self.assertEqual(storage['pending_design'], snapshot)
        self.assertEqual(state._outfit_name, 'Test outfit')
        state.pattern_state.load_outfit.assert_called_with(snapshot['outfit'], 0)
        state.pattern_state.set_new_body_params.assert_called_with({'height': 181})


if __name__ == '__main__':
    unittest.main()
