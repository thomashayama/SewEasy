"""Selection edits preserve independent material fields and garment ownership."""
import unittest
from copy import deepcopy
from unittest.mock import Mock

from gui.gui_pattern import GUIPattern
from gui.outfit import OutfitProgram
from webapp.wardrobe import Wardrobe


class FabricSelectionTests(unittest.TestCase):
    def setUp(self):
        self.pattern = GUIPattern(draft=False)
        self.pattern.reload_garment()
        self.panels = list(self.pattern.panel_svg_paths)[:2]
        self.assertEqual(len(self.panels), 2)

    def tearDown(self):
        self.pattern.release()

    def test_bulk_edits_preserve_unedited_fields_and_render_once(self):
        p = self.pattern
        p.edit_panel_fabrics([self.panels[0]], 'bg', '#112233')
        p.edit_panel_fabrics([self.panels[1]], 'bg', '#abcdef')
        serialize = p._view_serialize
        p._view_serialize = Mock(wraps=serialize)
        p.edit_panel_fabrics(self.panels, 'kind', 'gingham')
        self.assertEqual(p._view_serialize.call_count, 1)
        settings = p.panel_fabric_settings(self.panels)
        self.assertEqual([settings[n]['bg'] for n in self.panels], ['#112233', '#abcdef'])
        self.assertTrue(all(settings[n]['kind'] == 'gingham' for n in self.panels))
        svg = p.svg_path().read_text(encoding='utf-8')
        self.assertIn('seweasy_fabric_', svg)
        p.edit_panel_fabrics([self.panels[0]], 'reset')
        self.assertNotIn(self.panels[0], p.panel_fabrics)
        self.assertEqual(p.panel_fabrics[self.panels[1]]['kind'], 'gingham')

    def test_cross_garment_selection_and_saved_version_preserve_prints(self):
        p = self.pattern
        item = dict(name='Shirt', params=deepcopy(p.design_params), appearance=p.garment_appearance())
        p.load_outfit([item, deepcopy(item)])
        self.assertEqual(p.panel_fabric_settings([]), {})  # Before the outfit has redrafted.
        p.reload_garment()
        first = next(n for n in p.panel_svg_paths if n.startswith('g0__'))
        second = first.replace('g0__', 'g1__', 1)
        p.edit_panel_fabrics([first, second], 'kind', 'stripe')
        p.edit_panel_fabrics([second], 'bg', '#884422')
        self.assertNotEqual(p.panel_fabric_settings([first])[first]['bg'], '#884422')
        self.assertEqual(p.display_panel_fabrics()[second]['bg'], '#884422')
        p.sync_outfit_garment()
        assembled = OutfitProgram(p.body_params, p.outfit_items).assembly().pattern
        self.assertEqual(assembled['panel_fabrics'][first]['kind'], 'stripe')
        store = Wardrobe(storage={})
        version = store.save_garment('Fabric test', p.design_params, p.garment_appearance())
        p.load_outfit([version])
        self.assertEqual(p.panel_fabrics[first.split('__',1)[1]]['kind'], 'stripe')

    def test_invalid_edit_is_atomic_and_stale_sections_are_ignored(self):
        p = self.pattern
        with self.assertRaises(ValueError):
            p.edit_panel_fabrics(self.panels, 'bg', 'red<script>')
        with self.assertRaises(ValueError):
            p.edit_panel_fabrics(self.panels, 'scale', float('nan'))
        p.edit_panel_fabrics(['removed_panel'], 'kind', 'stripe')
        self.assertEqual(p.panel_fabrics, {})
        p.edit_panel_fabrics(self.panels, 'stiffness', 8)
        self.assertTrue(all(p.panel_stiffness_of(n) == 8 for n in self.panels))


if __name__ == '__main__':
    unittest.main()
