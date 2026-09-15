"""The studio sheet must preserve real geometry, materials, and fastener seats."""
from copy import deepcopy
from itertools import combinations
import unittest
import xml.etree.ElementTree as ET

from gui.gui_pattern import GUIPattern
from gui.pattern_layout import pack_panels, studio_svg


class PatternLayoutTests(unittest.TestCase):
    def setUp(self):
        self.gui = GUIPattern(draft=False)
        self.gui.reload_garment()
        self.pattern = self.gui.sew_pattern.assembly()

    def tearDown(self):
        self.gui.release()

    def test_packing_keeps_every_curve_at_its_original_size_and_does_not_overlap(self):
        original = {name: self.pattern._draw_a_panel(name, apply_transform=False)[0]
                    for name in self.pattern.panel_order()}
        packed, labels, size = pack_panels(original)
        self.assertEqual(set(original), set(packed))
        for name, path in packed.items():
            delta = path[0].start - original[name][0].start
            for source, target in zip(original[name], path):
                for t in (0, .25, .5, .75, 1):
                    self.assertAlmostEqual(abs(target.point(t) - source.point(t) - delta), 0, places=7)
            x0, x1, y0, y1 = path.bbox()
            self.assertTrue(0 <= x0 <= x1 <= size[0])
            self.assertTrue(0 <= y0 <= y1 < labels[name]['y'] < size[1])
        for a, b in combinations(packed.values(), 2):
            ax0, ax1, ay0, ay1 = a.bbox()
            bx0, bx1, by0, by1 = b.bbox()
            self.assertTrue(ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)

    def test_sheet_repositions_buttons_and_keeps_assembly_and_fabric_definitions(self):
        first = self.pattern.panel_order()[0]
        spec = deepcopy(self.pattern.pattern)
        drawing, paths, _, size = studio_svg(self.pattern, 'unused.svg', panel_fabrics={
            first: {'kind': 'stripe', 'bg': '#112233', 'fg': '#abcdef', 'scale': .6}})
        self.assertEqual(self.pattern.pattern, spec)
        root = ET.fromstring(drawing.tostring())
        ns = {'s': 'http://www.w3.org/2000/svg'}
        fills = [p.get('fill', '') for p in root.findall('s:path', ns)]
        self.assertEqual(len(fills), len(paths))
        self.assertTrue(any('url(#seweasy_fabric_' in fill for fill in fills))
        self.assertIsNotNone(root.find('s:defs/s:pattern', ns))
        circles = root.findall('s:circle', ns)
        self.assertEqual(len(circles), 2 * len(spec['fasteners']))
        for circle in circles:
            x, y = float(circle.get('cx')), float(circle.get('cy'))
            self.assertTrue(0 <= x <= size[0] and 0 <= y <= size[1])
            self.assertTrue(any(b[0] <= x <= b[1] and b[2] <= y <= b[3]
                                for b in (p.bbox() for p in paths.values())))


if __name__ == '__main__':
    unittest.main()
