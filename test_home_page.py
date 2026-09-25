"""Home/studio navigation keeps saved garment versions and working drafts separate."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from webapp.garment_catalog import STARTERS, draft_items, library_matches, standard_garments, starter_item, studio_snapshot, thumbnail
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
            self.assertEqual(meta['bottom' if kind in ('Pants', 'SkirtCircle', 'PencilSkirt') else 'upper']['v'], kind)
            self.assertEqual(meta['upper' if kind in ('Pants', 'SkirtCircle', 'PencilSkirt') else 'bottom']['v'], None)
            first['params']['meta']['upper']['v'] = 'changed'
            self.assertNotEqual(first['params'], second['params'])
        with self.assertRaises(ValueError):
            starter_item('../../private')

    def test_standard_library_is_available_without_seeding_or_mutating_user_saves(self):
        storage = {}
        store = Wardrobe(storage=storage)
        catalog = standard_garments()
        self.assertEqual(len(catalog), 6)
        self.assertEqual(len({g['id'] for g in catalog}), 6)
        item = next(g for g in catalog if g['standard'] == 'Shirt')
        self.assertLess(item['params']['sleeve']['length']['v'], .4)
        self.assertIsNone(item['params']['sleeve']['cuff']['type']['v'])
        saved = store.save_garment('My tee', item['params'], item['appearance'])
        saved['params']['shirt']['width']['v'] = 1.3
        self.assertNotEqual(saved['params'], standard_garments()[1]['params'])
        self.assertEqual(len(store.read()['garments']), 1)
        self.assertEqual(len(library_matches(catalog, 'pencil')), 1)

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


class GarmentDetailsTest(unittest.TestCase):
    def setUp(self):
        from gui.gui_pattern import GUIPattern
        self.pattern = GUIPattern(draft=False)

    def tearDown(self):
        self.pattern.release()

    def test_reset_and_randomize_keep_composition_and_fabric_on_active_outfit_item(self):
        p = self.pattern
        items = [starter_item('DressShirt'), starter_item('Pants')]
        p.load_outfit(items, 1)
        p.design_params['fabric']['kind']['v'] = 'gingham'
        meta, fabric = deepcopy(p.design_params['meta']), deepcopy(p.design_params['fabric'])
        defaults = deepcopy(p.design_sampler.default())
        for operation in (p.sample_design, p.restore_design):
            operation(reload=False, preserve_composition=True)
            p.sync_outfit_garment()
            self.assertEqual(p.design_params['meta'], meta)
            self.assertEqual(p.design_params['fabric'], fabric)
            self.assertEqual(p.outfit_items[0], items[0])
            self.assertEqual(p.outfit_items[1]['params']['meta'], meta)
            self.assertEqual(p.design_sampler.default(), defaults)
        self.assertEqual(p.design_params['pants']['length']['v'], .9)
        p.load_outfit([starter_item('Shirt')])
        p.design_params['sleeve']['length']['v'] = 1.0
        p.restore_design(reload=False, preserve_composition=True)
        self.assertEqual(p.design_params['sleeve']['length']['v'], .28)
        self.assertIsNone(p.design_params['sleeve']['cuff']['type']['v'])

    def test_import_cannot_add_another_garment_to_active_piece(self):
        p = self.pattern
        p.load_outfit([starter_item('Pants')])
        original = deepcopy(p.design_params)
        with self.assertRaisesRegex(ValueError, 'same garment type'):
            p.set_garment_design(starter_item('DressShirt')['params'])
        self.assertEqual(p.design_params, original)
        p.set_garment_design({'pants': {'length': {'v': .8}}})
        self.assertEqual(p.design_params['pants']['length']['v'], .8)
        self.assertEqual(p.design_params['meta'], original['meta'])

    def test_all_standard_garments_draft_nonempty_patterns(self):
        for item in standard_garments():
            with self.subTest(garment=item['name']):
                self.pattern.load_outfit([item])
                self.pattern.reload_garment()
                self.assertTrue(self.pattern.panel_svg_paths)
                self.assertTrue(self.pattern.svg_path().exists())


class HomeNavigationTest(unittest.TestCase):
    def test_opening_an_outfit_retains_its_revision_but_new_compositions_detach(self):
        from gui.callbacks import GUIState
        snapshot = studio_snapshot([starter_item('DressShirt')], 'Versioned outfit',
                                   outfit_revision_id='saved-revision')
        state = GUIState.__new__(GUIState)
        state.pattern_state = Mock()
        with patch('gui.callbacks.app', SimpleNamespace(storage=SimpleNamespace(user={'pending_design': snapshot}))):
            state._restore_pending_design()
        self.assertEqual(state._outfit_revision_id, 'saved-revision')
        new = studio_snapshot([starter_item('Pants')], previous=snapshot)
        self.assertIsNone(new['outfit_revision_id'])

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
        state.user = None
        with patch('gui.callbacks.app', SimpleNamespace(storage=SimpleNamespace(user=storage))):
            state._restore_pending_design()
            state._restore_body(state._restore_pending_design())
        self.assertEqual(storage['pending_design'], snapshot)
        self.assertEqual(state._outfit_name, 'Test outfit')
        state.pattern_state.load_outfit.assert_called_with(snapshot['outfit'], 0)
        state.pattern_state.set_new_body_params.assert_called_with({'height': 181})


if __name__ == '__main__':
    unittest.main()
