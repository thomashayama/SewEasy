from types import SimpleNamespace
import unittest
import numpy as np
from seweasy.meshgen.browser_hardware import button_attachments

class BrowserHardwareTest(unittest.TestCase):
    def fixture(self):
        points=np.array([[0.,0.,.2],[.4,0,.2],[.4,.6,.2],[0,.6,.2]])
        faces=np.array([[0,1,2],[0,2,3]])
        panel=SimpleNamespace(panel_vertices=points[:,:2],edges=[SimpleNamespace(label='button_placket',vertex_range=[0,3])])
        box=SimpleNamespace(panelNames=['front'],panels={'front':panel})
        return box,dict(unsewn_vertices=points,uv_faces=faces,face_panels=np.array(['front','front']))
    def test_count_size_and_placket_anchors(self):
        box,data=self.fixture()
        for count in [0,1,7,12]:
            config=dict(buttons=dict(count=count,diameter=1.3))
            result=button_attachments(box,config,data)
            self.assertEqual(len(result),count)
            for b in result:
                self.assertAlmostEqual(sum(b['weights']),1)
                self.assertTrue(all(w>=-1e-8 for w in b['weights']))
                self.assertAlmostEqual(b['radius_m'],.0065)
                seat=np.array(b['weights'])@data['unsewn_vertices'][b['ids']]
                self.assertAlmostEqual(seat[0],0);self.assertGreaterEqual(seat[1],.036-1e-8);self.assertLessEqual(seat[1],.564+1e-8)
    def test_button_follows_its_material_triangle_under_deformation(self):
        box,data=self.fixture();b=button_attachments(box,dict(buttons=dict(count=1,diameter=1)),data)[0]
        initial=np.array(b['weights'])@data['unsewn_vertices'][b['ids']]
        shifted=data['unsewn_vertices'].copy();shifted[b['ids']]+=np.array([.2,.1,-.3])
        moved=np.array(b['weights'])@shifted[b['ids']]
        np.testing.assert_allclose(moved-initial,[.2,.1,-.3])
    def test_no_hardware_leaks_to_other_garments(self):
        box,data=self.fixture();self.assertEqual(button_attachments(box,{},data),[])
        config=dict(button_groups=[dict(count=7,diameter=1.3,panels=[])])
        self.assertEqual(button_attachments(box,config,data),[])
if __name__=='__main__':unittest.main()
