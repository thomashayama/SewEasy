"""Hair on the mannequin: its shapes (seweasy/meshgen/hair.py), and hair as part of a body profile."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial import cKDTree
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import trimesh

from seweasy.meshgen import hair as H
from webapp import profiles
from webapp.db import Base
from webapp.models import User

ROOT = Path(__file__).parent
MEASUREMENTS = {'head_l': 26.3, 'waist_line': 36.9}


class HairShapeTest(unittest.TestCase):
    """Built on the neutral mannequin the preview drapes over."""

    @classmethod
    def setUpClass(cls):
        body = trimesh.load(ROOT / 'assets' / 'bodies' / 'mean_all.obj', process=False)
        cls.vertices, cls.faces = np.asarray(body.vertices), np.asarray(body.faces)
        cls.normals = np.asarray(body.vertex_normals)
        cls.head = H.Head(cls.vertices)
        cls.stops = H._landmarks(cls.head, MEASUREMENTS)
        cls.tree = cKDTree(cls.vertices)
        cls.meshes, cls.seconds = {}, {}
        for key in H.PRESETS:
            started = time.perf_counter()
            cls.meshes[key] = cls.build(H.preset(key))
            cls.seconds[key] = time.perf_counter() - started

    @classmethod
    def build(cls, hair):
        return H.hair_mesh(cls.vertices, cls.faces, hair, MEASUREMENTS)

    def points(self, key):
        return self.meshes[key]['positions'].astype(float)

    def test_every_preset_builds_a_well_formed_mesh_quickly(self):
        for key, mesh in self.meshes.items():
            with self.subTest(key):
                if key == 'bald':
                    self.assertIsNone(mesh)
                    continue
                count = len(mesh['positions'])
                self.assertTrue(np.isfinite(mesh['positions']).all() and np.isfinite(mesh['uv']).all())
                self.assertLess(mesh['faces'].max(), count)
                self.assertTrue(((mesh['shade'] > 0) & (mesh['shade'] <= 1)).all())
                self.assertLess(count, 12000)                 # sent with every scene
                self.assertLess(self.seconds[key], .5)        # built with every re-mesh

    def test_short_hair_leaves_face_ears_and_neck_bare(self):
        cx, _, cz = self.head.centre
        s, top = self.head.scale, self.head.top
        for key in ('buzz', 'short', 'side_part', 'curly_short'):
            with self.subTest(key):
                p = self.points(key)
                depth, theta = top - p[:, 1], np.abs(np.arctan2(p[:, 0] - cx, p[:, 2] - cz))
                face = (p[:, 2] > cz + .05) & (np.abs(p[:, 0] - cx) < .045 * s) & (depth > .075 * s)
                ears = (theta > 1.5) & (theta < 1.9) & (depth > .125 * s)    # below the ear's top; curls may brush it
                self.assertEqual(int(face.sum()), 0)
                self.assertEqual(int(ears.sum()), 0)
                self.assertLess(depth.max(), .2 * s)

    def test_hair_lies_on_the_body_not_inside_it(self):
        for key in ('short', 'bob', 'long', 'long_wavy', 'afro', 'ponytail'):
            with self.subTest(key):
                p = self.points(key)
                _, nearest = self.tree.query(p)
                outward = ((p - self.vertices[nearest]) * self.normals[nearest]).sum(axis=1)
                self.assertLess((outward < -.002).mean(), .02)

    def test_lengths_end_at_their_landmarks(self):
        chin, shoulder = self.stops[4], self.stops[5]
        self.assertAlmostEqual(self.points('bob')[:, 1].min(), chin, delta=.035)
        long = self.points('long')
        self.assertLess(long[:, 1].min(), shoulder - .15)
        # Beside the face long hair stops at the shoulders; below them it
        # gathers down the back instead of fanning across it.
        cx, _, cz = self.head.centre
        self.assertGreater(long[long[:, 2] > cz + .02, 1].min(), shoulder - .04)
        low = long[long[:, 1] < shoulder - .12]
        self.assertLess(np.ptp(low[:, 0]), .34)
        self.assertTrue((low[:, 2] < cz).all())

    def test_tied_hair_is_gathered_behind_the_head(self):
        back, nape = self.head.back, self.stops[5]
        self.assertLess(self.points('bun')[:, 2].min(), back - .03)
        tail = self.points('ponytail')
        self.assertLess(tail[:, 1].min(), nape - .15)
        self.assertTrue((tail[tail[:, 1] < nape, 2] < self.head.centre[2]).all())

    def test_fringe_covers_the_forehead(self):
        cx, _, cz = self.head.centre
        s, top = self.head.scale, self.head.top

        def on_forehead(key):
            p = self.points(key)
            depth = top - p[:, 1]
            return int(((p[:, 2] > cz + .05) & (np.abs(p[:, 0] - cx) < .03 * s)
                        & (depth > .07 * s) & (depth < .095 * s)).sum())

        self.assertGreater(on_forehead('bangs'), 10)
        self.assertEqual(on_forehead('bob'), 0)

    def test_coily_hair_grows_outward_and_a_hairline_can_recede(self):
        def width(mesh):
            return np.ptp(mesh['positions'][:, 0])

        self.assertGreater(width(self.meshes['afro']), width(self.meshes['short']) + .05)
        cx, _, cz = self.head.centre

        def hairline(recede):
            p = self.build(dict(H.preset('short'), recede=recede))['positions']
            front = p[(p[:, 2] > cz + .04) & (np.abs(p[:, 0] - cx) < .02)]
            return front[:, 1].min()

        self.assertGreater(hairline(1.), hairline(0.) + .015)

    def test_a_hood_covers_the_head(self):
        self.assertTrue(H.covered_head(['front', 'hood_left']))
        self.assertFalse(H.covered_head(['front', 'back']))


class HairDescriptionTest(unittest.TestCase):
    def test_anything_unknown_takes_its_default(self):
        self.assertEqual(H.clean_hair(None), H.DEFAULT_HAIR)
        cleaned = H.clean_hair({'length': 99, 'volume': -1, 'texture': 'frizzy', 'tie': 'bun',
                                'color': '#ABCDEF', 'style': 'mohawk', 'recede': 'lots'})
        self.assertEqual((cleaned['length'], cleaned['volume'], cleaned['texture'], cleaned['tie']),
                         (H.MAX_LENGTH, 0., 'straight', 'bun'))
        self.assertEqual((cleaned['color'], cleaned['style'], cleaned['recede']), ('#abcdef', 'short', 0.))
        self.assertEqual(H.clean_hair({'color': 'rgb(1,2,3)'})['color'], H.DEFAULT_HAIR['color'])

    def test_presets_are_recognised_and_keep_a_chosen_colour(self):
        for key in H.PRESETS:
            with self.subTest(key):
                self.assertEqual(H.matching_preset(H.preset(key, '#9a4a26')), key)
                self.assertEqual(H.preset(key, '#9a4a26')['color'], '#9a4a26')
        self.assertIsNone(H.matching_preset(dict(H.preset('bob'), volume=.95)))
        self.assertFalse(H.has_hair(H.preset('bald')))


class ProfileHairTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(TemporaryDirectory())
        engine = create_engine('sqlite:///' + str(Path(folder) / 'h.db'), connect_args={'check_same_thread': False})
        self.stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        for module in ('profiles', 'access'):
            self.stack.enter_context(patch(f'webapp.{module}.SessionLocal', sessions))
        with sessions() as db:
            db.add_all([User(email='alice@example.test', name='Alice'), User(email='bob@example.test', name='Bob')])
            db.commit()
        self.alice = 'alice@example.test'

    def profile(self, name='Me'):
        row = next(r for r in profiles.list_profiles(self.alice) if r['name'] == name)
        return profiles.get_profile(self.alice, row['id'])

    def test_hair_is_saved_with_the_profile(self):
        body = profiles.default_measurements('female')
        profiles.save_profile(self.alice, 'Me', body)
        self.assertEqual(self.profile()['hair'], H.DEFAULT_HAIR)      # none stored yet
        profile = self.profile()
        profiles.update_profile(self.alice, profile['id'], body, '#c69570', H.preset('ponytail', '#9a4a26'))
        saved = self.profile()
        self.assertEqual((saved['hair']['tie'], saved['hair']['color'], saved['skin_color']),
                         ('ponytail', '#9a4a26', '#c69570'))
        profiles.update_profile(self.alice, profile['id'], body, '#c69570')        # hair untouched
        self.assertEqual(self.profile()['hair']['tie'], 'ponytail')
        profiles.update_profile(self.alice, profile['id'], body, None, {'length': 'junk', 'texture': 'coily'})
        self.assertEqual(self.profile()['hair']['texture'], 'coily')

    def test_a_copy_keeps_the_hair(self):
        profiles.save_profile(self.alice, 'Me', profiles.default_measurements(), hair=H.preset('afro'))
        name = profiles.copy_profile(self.alice, self.profile()['id'])
        self.assertEqual(self.profile(name)['hair']['texture'], 'coily')

    def test_default_mannequins_have_their_own_hair(self):
        self.assertEqual(profiles.default_hair('female')['tie'], 'bun')
        self.assertEqual(profiles.default_hair('male')['style'], 'short')
        with self.assertRaises(ValueError):
            profiles.default_hair('giant')


class StudioHairTest(unittest.TestCase):
    def studio(self, snapshot):
        from gui.callbacks import GUIState
        state = GUIState.__new__(GUIState)
        state.user = None
        state.pattern_state = Mock()
        state._restore_body(snapshot)
        return state

    def test_the_studio_dresses_the_chosen_mannequin(self):
        self.assertEqual(self.studio({'body_choice': '__woman__'}).hair['tie'], 'bun')
        state = self.studio({})
        self.assertEqual(state.hair, H.preset('short'))
        self.assertEqual(state.pattern_state.hair, state.hair)       # drawn with the next scene
        custom = self.studio({'body_choice': '__custom__', 'hair': H.preset('long')})
        self.assertEqual(custom.hair['style'], 'long')


class SceneHairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        body = trimesh.load(ROOT / 'assets' / 'bodies' / 'mean_all.obj', process=False)
        cls.data = {'body_vertices': np.asarray(body.vertices), 'body_faces': np.asarray(body.faces)}

    def draft(self, hair):
        return SimpleNamespace(hair=hair, measurements=MEASUREMENTS)

    def test_the_scene_carries_compact_hair_unless_there_is_none(self):
        from gui.browser_drape import scene_hair
        hair = scene_hair(self.data, self.draft(H.preset('bob', '#9a4a26')), ['front', 'back'])
        count = len(hair['shade'])
        self.assertEqual((len(hair['positions']), len(hair['uv'])), (3 * count, 2 * count))
        self.assertLess(max(hair['faces']), count)
        self.assertEqual((hair['color'], hair['texture']), ('#9a4a26', 0))
        self.assertIsNone(scene_hair(self.data, self.draft(H.preset('bob')), ['front', 'hood']))
        self.assertIsNone(scene_hair(self.data, self.draft(H.preset('bald')), ['front']))
        self.assertIsNone(scene_hair(self.data, self.draft(None), ['front']))


if __name__ == '__main__':
    unittest.main()
