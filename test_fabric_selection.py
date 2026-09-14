"""Selection edits preserve independent material fields and garment ownership."""
import json
import unittest
from copy import deepcopy
from unittest.mock import Mock

from gui.gui_pattern import GUIPattern
from gui.outfit import OutfitProgram
from gui.fabric_library import FABRICS_BY_ID
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

    def test_presets_preserve_prints_and_custom_edits_clear_preset_identity(self):
        p = self.pattern
        p.edit_panel_fabrics(self.panels, 'kind', 'gingham')
        p.edit_panel_fabrics([self.panels[0]], 'bg', '#112233')
        before = p.display_panel_fabrics()
        for material, preset in FABRICS_BY_ID.items():
            p.edit_panel_fabrics(self.panels, 'material', material)
            settings = p.panel_fabric_settings(self.panels)
            self.assertTrue(all(s['material'] == material and s['stiffness'] == preset['stiffness']
                                for s in settings.values()))
            self.assertEqual(p.display_panel_fabrics(), before)
        p.edit_panel_fabrics([self.panels[0]], 'stiffness', 7)
        self.assertEqual(p.panel_material_of(self.panels[0]), 'custom')
        self.assertEqual(p.panel_material_of(self.panels[1]), 'canvas')
        snapshot = p.garment_appearance()
        with self.assertRaises(ValueError):
            p.edit_panel_fabrics(self.panels, 'material', 'unknown')
        self.assertEqual(p.garment_appearance(), snapshot)

    def test_default_restores_construction_stiffness_without_losing_color(self):
        p = self.pattern
        collar = 'right_collar_front'
        default = p.sew_pattern.assembly().pattern['panel_stiffness'][collar]
        self.assertGreater(default, 1)
        self.assertEqual(p.panel_stiffness_of(collar), default)
        p.edit_panel_fabrics([collar], 'bg', '#112233')
        p.edit_panel_fabrics([collar], 'material', 'chiffon')
        self.assertEqual(p.panel_stiffness_of(collar), 0.5)
        p.edit_panel_fabrics([collar], 'material', 'default')
        settings = p.panel_fabric_settings([collar])[collar]
        self.assertEqual((settings['material'], settings['stiffness'], settings['bg']),
                         ('default', default, '#112233'))
        p.edit_panel_fabrics([collar], 'material', 'denim')
        p.edit_panel_fabrics([collar], 'reset')
        self.assertEqual(p.panel_material_of(collar), 'default')
        self.assertEqual(p.panel_stiffness_of(collar), default)
        self.assertNotIn(collar, p.panel_materials)

    def test_saved_outfit_keeps_per_garment_materials_and_solver_values(self):
        p = self.pattern
        item = dict(name='Shirt', params=deepcopy(p.design_params), appearance=p.garment_appearance())
        p.load_outfit([item, deepcopy(item)])
        p.reload_garment()
        first, second = 'g0__right_ftorso', 'g1__right_ftorso'
        p.edit_panel_fabrics([first, second], 'material', 'linen')
        p.edit_panel_fabrics([second], 'material', 'denim')
        store = Wardrobe(storage={})
        versions = [store.save_garment(str(i), item['params'], item['appearance'])
                    for i, item in enumerate(p.outfit_items)]
        outfit = store.save_outfit('Materials', [g['id'] for g in versions])
        p.load_outfit(outfit['garments'], active=1)
        p.reload_garment()
        self.assertEqual(p.panel_material_of(first), 'linen')
        self.assertEqual(p.panel_material_of(second), 'denim')
        assembled = p.sew_pattern.assembly().pattern
        self.assertEqual(assembled['panel_stiffness'][first], 2.5)
        self.assertEqual(assembled['panel_stiffness'][second], 6)
        folder = p.save(pack=False)
        exported = json.loads(next(folder.glob('*_specification.json')).read_text())['pattern']
        self.assertTrue(set(exported['panel_stiffness']).issubset(exported['panels']))
        self.assertEqual(exported['panel_stiffness'][second], 6)
        self.assertEqual(p.panel_stiffness_of('g1__right_collar_front'),
                         assembled['panel_stiffness']['g1__right_collar_front'])
        p.edit_panel_fabrics([second], 'stiffness', 8)
        self.assertEqual(store.read()['outfits'][0]['garments'][1]['appearance']['panel_stiffness']['right_ftorso'], 6)


if __name__ == '__main__':
    unittest.main()
