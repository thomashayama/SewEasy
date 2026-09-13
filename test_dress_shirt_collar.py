"""CPU draft/topology regressions; GPU settling uses benchmarks/webgpu/collar.html."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import trimesh
import yaml

from assets.bodies.body_params import BodyParameters
from assets.garment_programs.dress_shirt import DressShirt, CollarLeafPanel
from seweasy.meshgen.boxmeshgen import BoxMesh
from seweasy.meshgen.webgpu import build_scene, panel_mesh_data
from seweasy.pattern.core import BasicPattern


class CollarTest(unittest.TestCase):
    def setUp(self):
        self.body = BodyParameters('assets/bodies/mean_all.yaml')
        self.design = yaml.safe_load(Path('assets/design_params/dress-shirt.yaml').read_text())['design']

    def test_point_changes_free_edge_without_changing_seams(self):
        short = CollarLeafPanel('short', 22, 4.5, .8, 0)
        long = CollarLeafPanel('long', 22, 4.5, .8, 5)
        for name in ('top', 'right'):
            self.assertAlmostEqual(short.interfaces[name].edges.length(), long.interfaces[name].edges.length())
        self.assertGreater(long.interfaces['left'].edges.length(), short.interfaces['left'].edges.length()+3)
        self.assertFalse(long.is_self_intersecting())

    def test_mirrored_leaves_and_roll_line_placement(self):
        for stand, depth, point in [(3,4.5,3),(2,3,0),(4.5,7,5)]:
            with self.subTest(stand=stand, depth=depth, point=point):
                design=deepcopy(self.design)
                for key,value in [('stand_height',stand),('collar_depth',depth),('collar_point',point)]:
                    design['dress_shirt'][key]['v']=value
                shirt=DressShirt(self.body,design)
                right,left=shirt.right.collar_comp,shirt.left.collar_comp
                np.testing.assert_allclose(left.leaf_f.norm(),right.leaf_f.norm()*[-1,1,1],atol=1e-8)
                for half in (right,left):
                    a=half.stand_f.interfaces['bottom'].edges[0]
                    b=half.leaf_f.interfaces['top'].edges[0]
                    # Fold-axis endpoints must coincide before any sewing.
                    stand_points=np.array([half.stand_f.point_to_3D(v) for v in (a.start,a.end)])
                    leaf_points=np.array([half.leaf_f.point_to_3D(v) for v in (b.start,b.end)])
                    np.testing.assert_allclose(stand_points,leaf_points[::-1],atol=1e-6)

    def test_complete_collar_mesh_and_fold_constraints(self):
        shirt=DressShirt(self.body,self.design)
        for panel in (shirt.back_fall,shirt.right.collar_comp.leaf_f,shirt.left.collar_comp.leaf_f):
            self.assertFalse(panel.is_self_intersecting(),panel.name)
        pattern=shirt.assembly()
        pairs={frozenset([s[0]['panel'],s[1]['panel']]) for s in pattern.pattern['stitches']}
        for pair in [('right_stand_back','left_stand_back'),('right_collar_front','collar_back'),('left_collar_front','collar_back')]:
            self.assertIn(frozenset(pair),pairs)
        with TemporaryDirectory() as folder:
            BasicPattern.serialize(pattern,folder,to_subfolder=False)
            box=BoxMesh(Path(folder)/'DressShirt_specification.json',1.5)
            box.load()
            data=panel_mesh_data(box,trimesh.load('assets/bodies/mean_all.obj',process=False))
            scene=build_scene(data,dict(garment='dress-shirt',resolution_cm=1.5,panels=len(box.panelNames),panel_stiffness=pattern.pattern['panel_stiffness']),'collar-test')
        folds=scene['hinges']
        self.assertGreater(len(folds),30)
        self.assertTrue(all(np.isfinite(c['angle']) and c['compliance']>0 for c in folds))
        covered={scene['vertex_panels'][i] for c in folds for i in c['ids']}
        self.assertTrue({'right_collar_front','left_collar_front','collar_back'} <= covered)
        for start,count in scene['hinge_batches']:
            ids=[i for h in folds[start:start+count] for i in h['ids']]
            self.assertEqual(len(ids),len(set(ids)))


if __name__=='__main__':
    unittest.main()
