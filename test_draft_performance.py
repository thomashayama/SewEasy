"""Geometry-preserving optimizations in the interactive drafting path."""
import unittest
from unittest.mock import patch

import numpy as np
import svgpathtools as svgpath

from assets.garment_programs import sleeves
from seweasy.garmentcode.operators import _max_curvature


class CurvatureTest(unittest.TestCase):
    def test_vectorized_samples_match_svg_curvature(self):
        rng = np.random.default_rng(42)
        curves = [svgpath.CubicBezier(*[complex(*p) for p in rng.normal(size=(4, 2))])
                  for _ in range(20)]
        # Include a stationary endpoint and the non-cubic fallback.
        curves += [svgpath.CubicBezier(0j, 0j, 1+0j, 2+0j),
                   svgpath.QuadraticBezier(0j, 1+2j, 3+0j)]
        for curve in curves:
            with self.subTest(curve=curve):
                expected = max(curve.curvature(t) for t in np.linspace(0, 1, 70))
                np.testing.assert_allclose(_max_curvature(curve, 70), expected, rtol=1e-12)

    def test_undefined_curvature_retains_the_existing_error(self):
        curve = svgpath.CubicBezier(0j, 0j, 1+1j, 2+0j)
        with self.assertRaises(ValueError):
            curve.curvature(0)
        with self.assertRaises(ValueError):
            _max_curvature(curve, 70)


class SleeveCacheTest(unittest.TestCase):
    def test_cache_reuses_fit_without_sharing_mutable_edges(self):
        sleeves._cached_armhole_curve.cache_clear()
        self.addCleanup(sleeves._cached_armhole_curve.cache_clear)
        args = (5., 20., .3)
        with patch.object(sleeves, '_fit_armhole_curve', wraps=sleeves._fit_armhole_curve) as fit:
            first = sleeves.ArmholeCurve(*args)
            reference = sleeves.ArmholeCurve(*args)
            first[0][0].start[0] += 100
            first[1][0].end[1] -= 100
            third = sleeves.ArmholeCurve(*args)
            self.assertEqual(fit.call_count, 1)
            for expected, actual in zip(reference, third):
                np.testing.assert_allclose(expected.verts(), actual.verts())
                self.assertAlmostEqual(expected.length(), actual.length())
            sleeves.ArmholeCurve(5., 21., .3)
            sleeves.ArmholeCurve(*args, bottom_angle_mix=.2)
            cut, inverse = sleeves.ArmholeCurve(*args, invert=False)
            self.assertEqual(fit.call_count, 4)
            self.assertIsNone(inverse)


if __name__ == '__main__':
    unittest.main()
