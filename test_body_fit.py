"""Dimension and integration checks for CPU mannequin fitting."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial import ConvexHull
import trimesh
import yaml

from seweasy.meshgen.body_fit import fit_body, levels, section_rings
from webapp.measurement_guide import scale_coupled

ROOT = Path(__file__).resolve().parent
BASE = yaml.safe_load((ROOT / 'assets/bodies/mean_all.yaml').read_text())['body']
PROFILES = [
    dict(height=160, bust=88, underbust=76, waist=68, hips=94, shoulder_w=34,
         waist_line=34, hips_line=21, arm_length=50, wrist=15, leg_circ=54),
    dict(height=185, bust=120, underbust=107, waist=104, hips=124, shoulder_w=43,
         waist_line=42, hips_line=25, arm_length=62, wrist=20, leg_circ=70),
]


def profile(edits):
    values = {**BASE, **edits}
    values.update(scale_coupled(BASE, values))
    return values


class BodyFitTest(unittest.TestCase):
    def test_default_retains_original_geometry(self):
        original = trimesh.load(ROOT / 'assets/bodies/mean_all.obj', process=False)
        mesh, report = fit_body(BASE)
        np.testing.assert_array_equal(mesh.vertices, original.vertices)
        np.testing.assert_array_equal(mesh.faces, original.faces)
        self.assertEqual(report['kind'], 'default')

    def test_default_man_and_woman_are_their_own_unchanged_mannequins(self):
        from seweasy.meshgen.body_fit import MANNEQUINS, mannequin_measurements
        from webapp import profiles
        heights = {}
        for name, note in MANNEQUINS.items():
            original = trimesh.load(ROOT / f'assets/bodies/mean_{name}.obj', process=False)
            mesh, report = fit_body(mannequin_measurements(name))
            np.testing.assert_array_equal(mesh.vertices, original.vertices)      # drawn as it is, not refitted
            self.assertEqual((report['kind'], report['mannequin'], report['note']), ('default', name, note))
            self.assertEqual(report['max_error_cm'], max(r['error_cm'] for r in report['measurements'].values()))
            heights[name] = mesh.bounds[1][1]
            # The studio's presets are the same numbers, as a detached copy.
            preset = profiles.default_measurements(name)
            self.assertEqual(preset, mannequin_measurements(name))
            preset['height'] = 1
            self.assertNotEqual(profiles.default_measurements(name)['height'], 1)
        self.assertLess(heights['female'], heights['all'])
        self.assertLess(heights['all'], heights['male'])
        self.assertEqual(set(profiles.DEFAULT_BODIES), set(MANNEQUINS))
        with self.assertRaises(ValueError):
            profiles.default_measurements('child')

    def test_custom_measurements_are_fitted_from_the_closest_mannequin(self):
        from seweasy.meshgen.body_fit import mannequin_measurements
        for name in ('male', 'female'):
            base = mannequin_measurements(name)
            edited = {**base, 'waist': base['waist'] + 4, 'hips': base['hips'] + 2}
            edited.update(scale_coupled(base, edited))
            mesh, report = fit_body(edited)
            with self.subTest(name=name):
                self.assertEqual((report['kind'], report['mannequin']), ('custom', name))
                self.assertLessEqual(report['max_error_cm'], 1)
                self.assertAlmostEqual(report['measurements']['waist']['target_cm'], base['waist'] + 4, places=2)
                self.assertTrue(np.isfinite(mesh.vertices).all())
        # A small edit of the neutral body still starts from the neutral body.
        self.assertEqual(fit_body(profile(dict(waist=BASE['waist'] + 3)))[1]['mannequin'], 'all')

    def test_small_and_large_profiles_match_dimensions(self):
        for edits in PROFILES:
            with self.subTest(height=edits['height']):
                values = profile(edits)
                mesh, report = fit_body(values)
                self.assertLess(report['max_error_cm'], .3)
                self.assertTrue(mesh.is_watertight)
                self.assertGreater(mesh.volume, 0)
                self.assertGreater(mesh.area_faces.min(), 1e-12)
                self.assertTrue(np.isfinite(mesh.vertex_normals).all())
                self.assertAlmostEqual(np.ptp(mesh.vertices[:, 1])*100, values['height'], places=3)
                # Independent tape-style check: convex section hull perimeter,
                # rather than the segment-length sum used by the fitter.
                metres = {k: v/100 for k, v in values.items()}
                for key in ('bust', 'underbust', 'waist', 'hips'):
                    rings = section_rings(mesh, [0, levels(metres)[key], 0])
                    ring = min(rings, key=lambda r: abs(r.mean((0, 1))[0]))
                    hull = ConvexHull(ring.reshape(-1, 3)[:, [0, 2]])
                    self.assertLess(abs(hull.area*100-values[key]), 1.5, key)

    def test_arm_length_pose_and_height_change_geometry(self):
        # The arm pose is measured below horizontal, as sleeves are placed:
        # lowering the arms (a larger angle) narrows the span, raising widens it.
        original, _ = fit_body(BASE)
        lowered, _ = fit_body(profile({'height':180, 'arm_length':62, 'arm_pose_angle':60}))
        raised, _ = fit_body(profile({'arm_pose_angle':30}))
        self.assertLess(np.ptp(lowered.vertices[:, 0]), np.ptp(original.vertices[:, 0]))
        self.assertGreater(np.ptp(raised.vertices[:, 0]), np.ptp(original.vertices[:, 0]))
        self.assertAlmostEqual(lowered.vertices[:, 1].max(), 1.8, places=4)

    def test_mannequin_arms_follow_the_sleeves(self):
        """The fitted arm and a drafted sleeve point the same way at any pose."""
        from scipy.spatial.transform import Rotation
        from gui.gui_pattern import GUIPattern
        from seweasy.meshgen.body_fit import arm_frame

        def below_horizontal(direction):
            d = direction if direction[0] > 0 else -direction
            return np.degrees(np.arctan2(-d[1], d[0]))
        pattern = GUIPattern(draft=False)
        try:
            offsets = []
            for pose in (30, 45, 60):
                pattern.set_arm_pose(pose)
                pattern.reload_garment()
                panels = pattern.sew_pattern.assembly().pattern['panels']
                panel = next(p for name, p in panels.items() if name.startswith('left_sleeve'))
                flat = np.c_[np.asarray(panel['vertices'], float), np.zeros(len(panel['vertices']))]
                world = Rotation.from_euler('XYZ', panel['rotation'], degrees=True).apply(flat)
                sleeve = np.linalg.svd(world - world.mean(0))[2][0]
                _, axis, _ = arm_frame(dict(BASE, arm_pose_angle=pose), 1)
                offsets.append(below_horizontal(sleeve) - below_horizontal(axis))
            # A sleeve's taper tilts its own axis a little; the pose must not add to that.
            self.assertLess(np.ptp(offsets), 1.0, offsets)
        finally:
            pattern.release()

    def test_cache_isolation_and_invalid_values(self):
        first, report = fit_body(profile(PROFILES[0]))
        first.vertices[:] = 0
        report['measurements'].clear()
        second, report = fit_body(profile(PROFILES[0]))
        self.assertGreater(second.volume, 0)
        self.assertIn('waist', report['measurements'])
        for edits in ({'waist':float('nan')}, {'height':-1}, {'arm_pose_angle':float('inf')},
                      {'waist_line':200}):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                fit_body({**BASE, **edits})

    def test_scene_uses_the_fitted_surface_for_rendering_and_collision(self):
        from gui.gui_pattern import GUIPattern
        from gui.browser_drape import prepare_scene
        pattern = GUIPattern(draft=False)
        try:
            values = profile(PROFILES[1])
            pattern._load_design_file(ROOT / 'assets/design_params/t-shirt.yaml')
            pattern.set_new_body_params(values)
            pattern.reload_garment()
            expected, _ = fit_body(values)
            with TemporaryDirectory() as work:
                scene = json.loads(prepare_scene(pattern, Path(work)/'custom.json').read_text())
            np.testing.assert_allclose(scene['body_vertices'], expected.vertices, atol=1e-8)
            np.testing.assert_allclose(scene['body_normals'], expected.vertex_normals, atol=1e-8)
            np.testing.assert_allclose(scene['body_bvh'][0]['lo'], expected.bounds[0])
            np.testing.assert_allclose(scene['body_bvh'][0]['hi'], expected.bounds[1])
            self.assertEqual(scene['body_fit']['kind'], 'custom')
            self.assertEqual(len(scene['body_faces']), len(expected.faces))
        finally:
            pattern.release()

    def test_account_preview_exports_the_same_custom_body(self):
        from webapp.body_display import profile_body_glb_url
        values = profile(PROFILES[0])
        expected, _ = fit_body(values)
        with TemporaryDirectory() as work, patch('webapp.body_display.BODY_TONE_CACHE', Path(work)):
            url = profile_body_glb_url('#c49b78', values)
            stored = trimesh.load(Path(work) / url.rsplit('/', 1)[-1])
            np.testing.assert_allclose(stored.bounds, expected.bounds, atol=1e-6)
            self.assertEqual(sum(len(g.faces) for g in stored.geometry.values()), len(expected.faces))


if __name__ == '__main__':
    unittest.main()
