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
        mesh, _ = fit_body(profile({'height':180, 'arm_length':62, 'arm_pose_angle':60}))
        original, _ = fit_body(BASE)
        self.assertGreater(np.ptp(mesh.vertices[:, 0]), np.ptp(original.vertices[:, 0]))
        self.assertAlmostEqual(mesh.vertices[:, 1].max(), 1.8, places=4)

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
