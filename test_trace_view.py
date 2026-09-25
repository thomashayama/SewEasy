"""Pattern projector: true-scale pieces handed to /trace, and the calibration maths behind it."""
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from svgpathtools import CubicBezier, Line, Path as SvgPath

from gui import trace_view

ROOT = Path(__file__).parent


class HandoffTest(unittest.TestCase):
    def test_straight_edges_keep_exact_corners_and_curves_are_finely_sampled(self):
        curve = CubicBezier(10 + 10j, 20 + 0j, 30 + 20j, 40 + 10j)
        path = SvgPath(Line(0j, 10 + 10j), curve, Line(40 + 10j, 40 + 30j), Line(40 + 30j, 0j))
        points = trace_view.polyline(path)
        for corner in ([0, 0], [10, 10], [40, 10], [40, 30]):
            self.assertIn(corner, points)
        between = points[points.index([10, 10]):points.index([40, 10]) + 1]
        steps = [abs(complex(*b) - complex(*a)) for a, b in zip(between, between[1:])]
        self.assertLessEqual(max(steps), trace_view.SAMPLE_CM + 0.01)
        def to_segment(z, a, b):
            t = max(0, min(1, ((z - a) * (b - a).conjugate()).real / abs(b - a) ** 2))
            return abs(z - (a + t * (b - a)))
        chords = [(complex(*a), complex(*b)) for a, b in zip(between, between[1:])]
        for i in range(1, 50):
            on_curve = curve.point(i / 50)
            # The traced line stays within 0.05 mm of the true curve.
            self.assertLess(min(to_segment(on_curve, a, b) for a, b in chords), 0.005)

    def test_marks_skip_fabric_fills_and_follow_the_piece_that_holds_them(self):
        with TemporaryDirectory() as folder:
            svg = Path(folder) / 'studio.svg'
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><defs><pattern id="p"><circle cx="1" cy="1" r="1"/>'
                '<line x1="0" y1="0" x2="1" y2="1"/></pattern></defs>'
                '<path d="M0 0H50V50H0Z"/><circle cx="5" cy="5" r="0.4" fill="none"/><circle cx="5" cy="5" r="0.35" fill="rgb(80,80,80)"/>'
                '<line x1="60" y1="60" x2="62" y2="60"/><rect x="61" y="70" width="1" height="1"/>'
                '<circle cx="500" cy="500" r="1"/></svg>', encoding='utf-8')
            found = trace_view.markers(svg)
        # A small button's outline stays an outline; only the filled centre is a dot.
        self.assertEqual([m['kind'] for m in found], ['circle', 'dot', 'line', 'rect', 'circle'])
        big = dict(id='big', bbox=[0, 0, 100, 100], markers=[])
        small = dict(id='small', bbox=[55, 55, 70, 75], markers=[])
        trace_view.assign_markers([big, small], found)
        self.assertEqual([m['kind'] for m in big['markers']], ['circle', 'dot'])
        self.assertEqual([m['kind'] for m in small['markers']], ['line', 'rect'])   # smallest holder wins

    def test_page_data_cannot_close_its_script_element(self):
        data = dict(title='</script><script>alert(1)</script>', pieces=[dict(label='A & <B>')])
        text = trace_view._script_json(data)
        self.assertNotIn('<', text)
        self.assertNotIn('&', text)
        self.assertEqual(json.loads(text), data)

    def test_a_drafted_pattern_arrives_at_true_size(self):
        from gui.gui_pattern import GUIPattern
        pattern = GUIPattern(draft=False)
        try:
            pattern.reload_garment()
            pattern._view_serialize()
            state = SimpleNamespace(pattern_state=pattern, panel_label=lambda name: name.upper(),
                                    ui_outfit_title=SimpleNamespace(text='Default dress'), user=None)
            data = trace_view.payload(state)
            self.assertEqual(data['title'], 'Default dress')
            self.assertIsNone(data['units'])
            self.assertEqual(data['key'], '|'.join(sorted(pattern.panel_svg_paths)))
            self.assertEqual({p['id'] for p in data['pieces']}, set(pattern.panel_svg_paths))
            for piece in data['pieces']:
                x0, x1, y0, y1 = pattern.panel_svg_paths[piece['id']].bbox()
                xs, ys = [p[0] for p in piece['outline']], [p[1] for p in piece['outline']]
                # Centimetres in, centimetres out: the outline spans exactly its panel.
                for got, want in ((min(xs), x0), (max(xs), x1), (min(ys), y0), (max(ys), y1)):
                    self.assertAlmostEqual(got, want, delta=0.02)
                self.assertEqual(piece['label'], piece['id'].upper())
            json.dumps(data)   # storable in the browser's user storage as is
        finally:
            pattern.release()

    def test_nothing_to_project_before_a_draft(self):
        state = SimpleNamespace(pattern_state=SimpleNamespace(svg_filename='', panel_svg_paths={}))
        self.assertIsNone(trace_view.payload(state))


GEOMETRY_CHECKS = '''
import {apply, fittedQuad, invert, isConvex, localScale, pieceMatrix, rectToQuad} from '%s';
const fail = message => { throw new Error(message); };
const near = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol || fail(`${a} is not ${b}`);
const same = (p, q, tol) => { near(p[0], q[0], tol); near(p[1], q[1], tol); };

// Keystone: a 60 x 40 cm table rectangle onto an uneven quad hits every corner.
const quad = [[100, 80], [900, 120], [860, 700], [140, 640]];
const H = rectToQuad(60, 40, quad);
[[0, 0], [60, 0], [60, 40], [0, 40]].forEach(([x, y], i) => same(apply(H, x, y), quad[i]));
// Perspective, not an average: the table's centre is where the quad's diagonals cross.
const cross = (a, b, c, d) => {
  const t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0]))
          / ((b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0]));
  return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
};
same(apply(H, 30, 20), cross(quad[0], quad[2], quad[1], quad[3]));
// Screen back to table.
same(apply(invert(H), ...apply(H, 12.3, 7.7)), [12.3, 7.7]);

// A screen facing you squarely: a plain scale, 10 px per cm everywhere.
const flat = rectToQuad(50, 30, [[10, 20], [510, 20], [510, 320], [10, 320]]);
same(localScale(flat, 3, 29), [10, 10]);
same(apply(flat, 5, 5), [60, 70]);

// Crossed markers cannot be traced from.
isConvex(quad) || fail('uneven quad is convex');
isConvex([[0, 0], [100, 0], [0, 100], [100, 100]]) && fail('crossed quad accepted');

// Pieces turn about their centre (clockwise on a y-down screen) and mirror left-right.
const turned = pieceMatrix([10, 5], {x: 50, y: 30, rotation: 90, flip: false});
same(apply(turned, 10, 5), [50, 30]);
same(apply(turned, 12, 5), [50, 32]);
same(apply(pieceMatrix([10, 5], {x: 50, y: 30, rotation: 0, flip: true}), 12, 5), [48, 30]);

// The starting rectangle keeps its proportions and stays inside the window.
const start = fittedQuad(60, 40, 1920, 1080);
near((start[1][0] - start[0][0]) / (start[3][1] - start[0][1]), 1.5);
start.flat().forEach(v => (v >= 0 && v <= 1920) || fail('outside the window'));
console.log('ok');
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js runs the browser maths')
class CalibrationMathsTest(unittest.TestCase):
    def test_homography_scale_keystone_and_piece_moves(self):
        module = (ROOT / 'gui' / 'trace_geometry.js').as_uri()
        result = subprocess.run(['node', '--input-type=module', '-e', GEOMETRY_CHECKS % module],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_the_page_script_parses(self):
        for name in ('trace_view.js', 'trace_geometry.js'):
            result = subprocess.run(['node', '--check', str(ROOT / 'gui' / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
