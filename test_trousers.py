"""Trouser waistband geometry and body-dependent rise regression checks."""
from copy import deepcopy
import unittest

import numpy as np

from assets.bodies.body_params import BodyParameters
from assets.garment_programs.meta_garment import MetaGarment
from webapp.garment_catalog import starter_item


class TrouserTest(unittest.TestCase):
    def test_waistband_occupies_the_rise_and_matches_its_sewing_edge(self):
        for hips_depth in (20, 23.4837, 28):
            for rise in (.65, 1):
                with self.subTest(hips_depth=hips_depth, rise=rise):
                    body = BodyParameters('assets/bodies/mean_all.yaml')
                    body['hips_line'] = hips_depth
                    params = starter_item('Pants')['params']
                    params['pants']['rise']['v'] = rise
                    original = deepcopy(params)
                    garment = MetaGarment('pants', body, params)
                    belt, pants = garment.subs
                    self.assertAlmostEqual(pants.get_rise(), belt.rise)
                    self.assertLessEqual(pants.get_rise() + belt.width / hips_depth, 1)
                    self.assertAlmostEqual(belt.interfaces['bottom'].edges.length(),
                                           pants.interfaces['top'].edges.length(), places=3)
                    a = np.mean(belt.interfaces['bottom'].bbox_3d(), axis=0)
                    b = np.mean(pants.interfaces['top'].bbox_3d(), axis=0)
                    self.assertAlmostEqual(a[1], b[1], places=5)
                    self.assertEqual(params, original)

    def test_unbanded_trousers_keep_the_requested_rise_and_shorts_stay_short(self):
        body = BodyParameters('assets/bodies/mean_all.yaml')
        params = starter_item('Pants')['params']
        params['meta']['wb']['v'] = None
        params['pants']['rise']['v'] = .7
        full = MetaGarment('full', body, params).subs[0]
        self.assertEqual(full.get_rise(), .7)
        params['pants']['length']['v'] = .3
        shorts = MetaGarment('shorts', body, params).subs[0]
        self.assertLess(shorts.length(), full.length() * .6)


if __name__ == '__main__':
    unittest.main()
