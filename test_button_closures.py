"""Permanent stitches and removable buttons have distinct topology and seats."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
import trimesh
import yaml
from assets.bodies.body_params import BodyParameters
from assets.garment_programs.dress_shirt import DressShirt
from seweasy.meshgen.boxmeshgen import BoxMesh
from seweasy.meshgen.webgpu import panel_mesh_data, build_scene
from seweasy.meshgen.browser_hardware import button_attachments
from seweasy.pattern.core import BasicPattern


class ButtonClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body=BodyParameters('assets/bodies/mean_all.yaml')
        cls.design=yaml.safe_load(Path('assets/design_params/dress-shirt.yaml').read_text())['design']
        cls.shirt=DressShirt(cls.body,cls.design)
        cls.pattern=cls.shirt.assembly()
        with TemporaryDirectory() as folder:
            BasicPattern.serialize(cls.pattern,folder,to_subfolder=False)
            box=BoxMesh(Path(folder)/'DressShirt_specification.json',1.5);box.load()
            cls.data=panel_mesh_data(box,trimesh.load('assets/bodies/mean_all.obj',process=False))
            cls.buttons=button_attachments(box,cls.pattern.pattern,cls.data)
            cls.scene=build_scene(cls.data,dict(garment='dress-shirt',resolution_cm=1.5,
                panels=len(box.panelNames),panel_stiffness=cls.pattern.pattern['panel_stiffness']),'buttons-test')

    def test_no_permanent_front_or_neck_closure(self):
        forbidden=[{'right_ftorso','left_ftorso'},{'right_stand_front','left_stand_front'}]
        for s in self.pattern.pattern['stitches']:
            self.assertNotIn({s[0]['panel'],s[1]['panel']},forbidden)
        for c in self.scene['constraints']:
            if c[2]==2:
                self.assertNotIn({self.scene['vertex_panels'][i] for i in c[:2]},forbidden)

    def test_interior_seats_use_separate_panels_and_render_at_the_physical_anchor(self):
        self.assertEqual(len(self.buttons),10)
        for b in self.buttons:
            self.assertNotEqual(b['panel'],b['hole']['panel'])
            self.assertEqual(len(set(b['ids']+b['hole']['ids'])),6)
            for seat in (b,b['hole']):
                self.assertAlmostEqual(sum(seat['weights']),1)
                self.assertGreaterEqual(min(seat['weights']),-1e-8)
                uv=np.array(seat['weights'])@self.data['uv'][seat['ids']]
                np.testing.assert_allclose(uv,seat['uv_center'],atol=1e-9)
                self.assertAlmostEqual(np.linalg.norm(seat['uv_direction']),1)
            if b['role']=='placket':
                for seat in (b,b['hole']):
                    p=np.array(seat['weights'])@self.data['unsewn_vertices'][seat['ids']]
                    self.assertAlmostEqual(p[0],0,places=6)

    def test_front_extensions_overlap_instead_of_adding_circumference(self):
        right,left=self.shirt.right.ftorso,self.shirt.left.ftorso
        a=right.point_to_3D(right.interfaces['inside'].edges[0].start)
        b=left.point_to_3D(left.interfaces['inside'].edges[0].start)
        self.assertAlmostEqual(a[0]-b[0],2*self.design['dress_shirt']['placket_width']['v'])
        self.assertGreater(b[2],a[2])

    def test_zero_buttons_really_leaves_the_shirt_open(self):
        design=deepcopy(self.design);design['buttons']['count']['v']=0
        raw=DressShirt(self.body,design).assembly().pattern
        self.assertEqual(raw['fasteners'],[])
        self.assertFalse(any({s[0]['panel'],s[1]['panel']}=={'right_ftorso','left_ftorso'} for s in raw['stitches']))
        self.assertEqual(button_attachments(None,raw,None),[])

    def test_assembly_preserves_fractional_material_coordinates(self):
        shirt=DressShirt(self.body,deepcopy(self.design));panel=shirt.right.ftorso
        before=np.array([panel.point_to_3D(v) for v in panel.edges.verts()])
        shirt.assembly()
        np.testing.assert_allclose([panel.point_to_3D(v) for v in panel.edges.verts()],before,atol=1e-10)
        shirt.assembly()
        np.testing.assert_allclose([panel.point_to_3D(v) for v in panel.edges.verts()],before,atol=1e-10)


if __name__=='__main__':unittest.main()
