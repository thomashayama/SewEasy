from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from webapp.db import Base
from webapp.models import User
from webapp.wardrobe import Wardrobe

PARAMS={'meta':{'upper':{'v':'DressShirt'}},'fabric':{'kind':{'v':'gingham'}}}
LOOK={'fabric_color':'#27496a','panel_colors':{'right_collar_front':'#ffffff'},'panel_stiffness':{}}
class WardrobeTest(unittest.TestCase):
    def test_outfit_pins_versions_and_copies_every_appearance_field(self):
        storage={};w=Wardrobe(storage=storage);params=deepcopy(PARAMS);look=deepcopy(LOOK)
        one=w.save_garment('Oxford',params,look);outfit=w.save_outfit('Workday',[one['id'],one['id']])
        params['fabric']['kind']['v']='stripe';look['fabric_color']='#aa0000'
        two=w.save_garment('Oxford',params,look)
        self.assertEqual(two['version'],2);self.assertEqual(outfit['garments'][0]['params'],PARAMS)
        self.assertEqual(Wardrobe(storage=storage).read()['outfits'][0]['garments'][1]['appearance'],LOOK)
        outfit['garments'][0]['appearance']['fabric_color']='#000000'
        self.assertEqual(w.read()['outfits'][0]['garments'][0]['appearance'],LOOK)
    def test_requires_one_or_more_owned_garment_versions(self):
        w=Wardrobe(storage={})
        for ids in ([],['missing']):
            with self.assertRaises(ValueError):w.save_outfit('Test',ids)
        with self.assertRaises(ValueError):w.save_garment('Empty',{'meta':{}},LOOK)
        g=w.save_garment('Shirt',PARAMS,LOOK);self.assertEqual(len(w.save_outfit('Solo',[g['id']])['garments']),1)
    def test_sql_library_is_private_and_survives_new_service_instance(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine)
        with sessions() as db:db.add_all([User(email='one@example.com'),User(email='two@example.com')]);db.commit()
        with patch('webapp.wardrobe.SessionLocal',sessions):
            one=Wardrobe('one@example.com');g=one.save_garment('Oxford',PARAMS,LOOK);one.save_outfit('Work',[g['id']])
            self.assertEqual(len(Wardrobe('one@example.com').read()['outfits']),1)
            self.assertEqual(Wardrobe('two@example.com').read()['garments'],[])
            with self.assertRaises(ValueError):Wardrobe('two@example.com').save_outfit('Stolen',[g['id']])
        engine.dispose()
    def test_outfit_drafting_namespaces_repeated_garments_without_cross_stitches(self):
        from gui.gui_pattern import GUIPattern
        from gui.outfit import OutfitProgram
        p=GUIPattern(draft=False)
        try:
            item={'params':deepcopy(p.design_params),'appearance':deepcopy(LOOK)}
            item['params']['fabric']['kind']['v']='stripe'
            outfit=OutfitProgram(p.body_params,[item,deepcopy(item)]).assembly().pattern
            names=outfit['panels'];self.assertTrue(any(n.startswith('g1__') for n in names))
            self.assertTrue(outfit['panel_fabrics']);self.assertEqual(len(outfit['button_groups']),2)
            for seam in outfit['stitches']:self.assertEqual(seam[0]['panel'].split('__')[0],seam[1]['panel'].split('__')[0])
            self.assertEqual(len(outfit['fasteners']),20)
            for fastener in outfit['fasteners']:
                prefix=fastener['id'].split('__')[0]
                for side in ('button','buttonhole'):
                    self.assertEqual(fastener[side]['panel'].split('__')[0],prefix)
        finally:p.release()
if __name__=='__main__':unittest.main()
