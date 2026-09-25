"""Hair on the 3D preview's mannequin: its shape (gui/webgpu/hair.js, run in Node) and the saved choice."""
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp import profiles
from webapp.db import Base
from webapp.models import User

ROOT = Path(__file__).parent

# Builds hair on the neutral mannequin the preview drapes over and reports what
# the Python side checks: where the hair lies relative to the head.
HAIR_CHECKS = r'''
import fs from 'fs';
const hair = await import(%(module)s);
const vertices = [], faces = [];
for (const line of fs.readFileSync(%(obj)s, 'utf8').split('\n')) {
  const f = line.trim().split(/\s+/);
  if (f[0] === 'v') vertices.push(f.slice(1, 4).map(Number));
  if (f[0] === 'f') {
    const i = f.slice(1).map(s => parseInt(s, 10) - 1);
    for (let k = 1; k + 1 < i.length; k++) faces.push([i[0], i[k], i[k + 1]]);
  }
}
const normals = vertices.map(() => [0, 0, 0]);
for (const [a, b, c] of faces) {
  const u = [0, 1, 2].map(k => vertices[b][k] - vertices[a][k]), v = [0, 1, 2].map(k => vertices[c][k] - vertices[a][k]);
  const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
  for (const i of [a, b, c]) for (let k = 0; k < 3; k++) normals[i][k] += n[k];
}
for (const n of normals) { const l = Math.hypot(...n) || 1; for (let k = 0; k < 3; k++) n[k] /= l; }
const scene = {body_vertices: vertices, body_normals: normals, body_faces: faces, vertex_panels: ['front', 'back']};
const head = hair.headFrame(vertices);
const near = vertices.map((p, i) => i).filter(i => head.top - vertices[i][1] < .3);
// Every style cuts the same scalp first; a bun adds its swirl after it, tucked into the head.
const scalp = hair.hairMesh(scene, 'short').count;
const report = {head, styles: {}, constants: {styles: Object.keys(hair.HAIR_STYLES), colors: Object.keys(hair.HAIR_COLORS),
                                              default: hair.DEFAULT_HAIR, strand: hair.STRAND_M}};
for (const style of ['short', 'bun']) {
  const mesh = hair.hairMesh(scene, style), points = [];
  for (let i = 0; i < mesh.count; i++) points.push(Array.from(mesh.positions.subarray(i * 4, i * 4 + 3)));
  const [cx, , cz] = head.centre, s = head.scale;
  const depth = p => head.top - p[1], theta = p => Math.abs(Math.atan2(p[0] - cx, p[2] - cz));
  // How far each scalp point sits out along the normal of the nearest skin vertex.
  const lift = points.slice(0, scalp).map(p => {
    let best = Infinity, out = 0;
    for (const i of near) {
      const q = vertices[i], d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2;
      if (d < best) { best = d; out = [0, 1, 2].reduce((t, k) => t + (p[k] - q[k]) * normals[i][k], 0); }
    }
    return out;
  });
  lift.sort((a, b) => a - b);
  report.styles[style] = {
    count: mesh.count, triangles: mesh.faces.length / 3,
    faceIndexOk: mesh.faces.every(i => i < mesh.count),
    finite: [mesh.positions, mesh.normals, mesh.uv].every(a => a.every(Number.isFinite)),
    normalError: Math.max(...points.map((p, i) => Math.abs(Math.hypot(...mesh.normals.subarray(i * 4, i * 4 + 3)) - 1))),
    maxY: Math.max(...points.map(p => p[1])), minZ: Math.min(...points.map(p => p[2])),
    deepest: Math.max(...points.map(depth)) / s,
    onFace: points.filter(p => p[2] > cz + .05 && Math.abs(p[0] - cx) < .045 * s && depth(p) > .075 * s).length,
    onEars: points.filter(p => theta(p) > 1.45 && theta(p) < 1.95 && depth(p) > .12 * s).length,
    insideFraction: lift.filter(t => t < 0).length / lift.length, lowLift: lift[Math.floor(lift.length * .02)],
  };
}
report.none = hair.hairMesh(scene, 'none'), report.unknown = hair.hairMesh(scene, 'mohawk');
report.hooded = hair.coveredHead({vertex_panels: ['front', 'hood_left']});
report.bare = [hair.coveredHead(scene), hair.coveredHead({})];
console.log(JSON.stringify(report));
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js runs the browser geometry')
class HairShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = HAIR_CHECKS % {'module': json.dumps((ROOT / 'gui' / 'webgpu' / 'hair.js').as_uri()),
                                'obj': json.dumps(str(ROOT / 'assets' / 'bodies' / 'mean_all.obj'))}
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        cls.report = json.loads(result.stdout)

    def test_head_is_found_on_the_mannequin(self):
        head = self.report['head']
        self.assertAlmostEqual(head['scale'], 1, delta=.2)
        self.assertLess(head['centre'][1], head['top'])
        self.assertLess(head['back'], head['centre'][2])

    def test_meshes_are_well_formed(self):
        for style, mesh in self.report['styles'].items():
            with self.subTest(style):
                self.assertTrue(mesh['faceIndexOk'])
                self.assertTrue(mesh['finite'])
                self.assertLess(mesh['normalError'], 1e-4)
                self.assertLess(mesh['count'], 8000)     # cheap enough to rebuild on every re-mesh

    def test_hair_covers_the_scalp_but_leaves_face_ears_and_neck_bare(self):
        for style, mesh in self.report['styles'].items():
            with self.subTest(style):
                self.assertEqual(mesh['onFace'], 0)
                self.assertEqual(mesh['onEars'], 0)
                self.assertLess(mesh['deepest'], .2)     # stops at the nape, clear of collars

    def test_hair_sits_on_the_head_not_inside_it(self):
        for style, mesh in self.report['styles'].items():
            with self.subTest(style):
                self.assertLess(mesh['insideFraction'], .01)
                self.assertGreater(mesh['lowLift'], 0)

    def test_short_hair_has_volume_on_top_and_a_bun_sits_behind_the_head(self):
        top, back = self.report['head']['top'], self.report['head']['back']
        short, bun = self.report['styles']['short'], self.report['styles']['bun']
        self.assertGreater(short['maxY'] - top, .01)
        self.assertLess(bun['maxY'] - top, short['maxY'] - top)   # swept back, close to the crown
        self.assertLess(bun['minZ'], back - .03)
        self.assertGreater(short['minZ'], back - .03)

    def test_no_hair_for_none_unknown_styles_or_under_a_hood(self):
        self.assertIsNone(self.report['none'])
        self.assertIsNone(self.report['unknown'])
        self.assertTrue(self.report['hooded'])
        self.assertEqual(self.report['bare'], [False, False])

    def test_choices_match_what_the_account_accepts(self):
        constants = self.report['constants']
        self.assertEqual(tuple(constants['styles']), profiles.HAIR_STYLES)
        self.assertEqual(constants['default'], profiles.DEFAULT_HAIR)
        self.assertIn(profiles.DEFAULT_HAIR['color'], constants['colors'])
        for color in constants['colors']:
            self.assertEqual(profiles.clean_hair('short', color)['color'], color)

    def test_the_scripts_parse(self):
        for name in ('webgpu/hair.js', 'webgpu/render.js', 'browser_drape.js'):
            result = subprocess.run(['node', '--check', str(ROOT / 'gui' / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


class HairPreferenceTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(TemporaryDirectory())
        engine = create_engine('sqlite:///' + str(Path(folder) / 'h.db'), connect_args={'check_same_thread': False})
        self.stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        self.stack.enter_context(patch('webapp.profiles.SessionLocal', sessionmaker(bind=engine)))
        with sessionmaker(bind=engine)() as db:
            db.add(User(email='alice@example.test', name='Alice'))
            db.commit()

    def test_unknown_values_fall_back_to_the_default(self):
        self.assertEqual(profiles.clean_hair(None, None), profiles.DEFAULT_HAIR)
        self.assertEqual(profiles.clean_hair('mohawk', 'red'), profiles.DEFAULT_HAIR)
        self.assertEqual(profiles.clean_hair('bun', '#C9A36B'), {'style': 'bun', 'color': '#c9a36b'})
        self.assertEqual(profiles.clean_hair('none', '#12345'), {'style': 'none', 'color': profiles.DEFAULT_HAIR['color']})

    def test_choice_is_kept_on_the_account(self):
        alice = 'alice@example.test'
        self.assertEqual(profiles.get_hair(alice), profiles.DEFAULT_HAIR)
        self.assertEqual(profiles.set_hair(alice, 'bun', '#8C4A2F'), {'style': 'bun', 'color': '#8c4a2f'})
        self.assertEqual(profiles.get_hair(alice), {'style': 'bun', 'color': '#8c4a2f'})
        profiles.set_hair(alice, 'none', 'not a colour')
        self.assertEqual(profiles.get_hair(alice), {'style': 'none', 'color': profiles.DEFAULT_HAIR['color']})
        self.assertEqual(profiles.get_hair('nobody@example.test'), profiles.DEFAULT_HAIR)
        self.assertEqual(profiles.set_hair('nobody@example.test', 'bun', '#1f1a17')['style'], 'bun')   # no row: not saved

    def test_a_signed_out_choice_lives_in_browser_storage(self):
        from gui.callbacks import GUIState
        state = GUIState.__new__(GUIState)
        state.user = None
        with patch('gui.callbacks.app') as app:
            app.storage.user = {'hair': {'style': 'bun', 'color': '#6b4a33'}}
            self.assertEqual(state._hair_preference(), {'style': 'bun', 'color': '#6b4a33'})
            app.storage.user = {}
            self.assertEqual(state._hair_preference(), profiles.DEFAULT_HAIR)


if __name__ == '__main__':
    unittest.main()
