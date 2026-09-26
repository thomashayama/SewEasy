"""Measurements: the inseam, a default profile per account, the 3D arm pose, and the guide's pictures."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp import measurement_guide as guide, profiles
from webapp.access import Access
from webapp.db import Base
from webapp.models import User

ROOT = Path(__file__).parent
DIAGRAMS = ROOT / 'assets/img/measurements'


class InseamTest(unittest.TestCase):
    def setUp(self):
        self.body = profiles.default_measurements('all')

    def test_every_default_body_implies_a_realistic_inseam(self):
        for name in profiles.DEFAULT_BODIES:
            body = profiles.default_measurements(name)
            inseam = guide.editor_values(body)['inseam']
            self.assertAlmostEqual(inseam / body['height'], .445, delta=.02)

    def test_inseam_sets_the_crotch_depth_and_the_mannequin_follows(self):
        from seweasy.meshgen.body_fit import levels
        changed = guide.apply_inseam(self.body, 80)
        for key in ('height', 'head_l', 'waist_line', 'hips_line'):
            self.assertEqual(changed[key], self.body[key])          # measured values are kept
        self.assertAlmostEqual(guide.inseam_cm(changed), 80, places=1)
        self.assertAlmostEqual(levels(changed)['crotch'], 80, places=1)   # the mannequin's legs match
        self.assertEqual(guide.validate_measurements(changed), ([], []))

    def test_an_inseam_that_does_not_add_up_is_caught(self):
        errors, _ = guide.validate_measurements(guide.apply_inseam(self.body, 95))
        self.assertTrue(any('too long' in e for e in errors))
        _, warnings = guide.validate_measurements(guide.apply_inseam(self.body, 60))
        self.assertTrue(any('below hip level' in w for w in warnings))

    def test_editors_list_fields_in_measuring_order_without_derived_values_or_the_pose(self):
        essentials = guide.editor_keys(self.body, essential_only=True)
        self.assertEqual(essentials[0], 'height')
        self.assertEqual(essentials[-1], 'inseam')
        everything = guide.editor_keys(self.body, essential_only=False)
        self.assertNotIn('arm_pose_angle', everything)
        self.assertNotIn('crotch_hip_diff', everything)     # set by the inseam
        self.assertNotIn('arm_pose_angle', guide.GUIDE)
        self.assertEqual(set(everything) - {'inseam'}, set(self.body) - {'arm_pose_angle', 'crotch_hip_diff'})


class DefaultProfileTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(TemporaryDirectory())
        engine = create_engine('sqlite:///' + str(Path(folder) / 'm.db'), connect_args={'check_same_thread': False})
        self.stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        for module in ('profiles', 'access', 'friends'):
            self.stack.enter_context(patch(f'webapp.{module}.SessionLocal', self.sessions))
        with self.sessions() as db:
            db.add_all([User(email='alice@example.test', name='Alice'), User(email='bob@example.test', name='Bob')])
            db.commit()
        self.alice, self.bob = 'alice@example.test', 'bob@example.test'
        profiles.save_profile(self.alice, 'Me', dict(profiles.default_measurements('female'), height=160.0),
                              skin_color='#a07e56')
        self.mine = profiles.list_profiles(self.alice)[0]['id']

    def studio(self, email, snapshot):
        """A studio's opening body, without drawing a page."""
        from gui.callbacks import GUIState
        state = GUIState.__new__(GUIState)
        state.user = {'email': email} if email else None
        state.pattern_state = Mock()
        state._restore_body(snapshot)
        applied = state.pattern_state.set_new_body_params.call_args
        return state.body_choice, applied[0][0] if applied else None, state._restored_skin

    def test_set_clear_and_only_profiles_you_can_open(self):
        self.assertIsNone(profiles.get_default_profile(self.alice))
        profiles.set_default_profile(self.alice, self.mine)
        self.assertEqual(profiles.get_default_profile(self.alice)['name'], 'Me')
        with self.assertRaises(ValueError):
            profiles.set_default_profile(self.bob, self.mine)       # private to Alice
        share = Access(self.alice).ensure('body', self.mine)
        Access(self.alice).add_member(share, self.bob)
        profiles.set_default_profile(self.bob, self.mine)            # shared with Bob: allowed
        self.assertEqual(profiles.get_default_profile(self.bob)['role'], 'viewer')
        Access(self.alice).remove_member(share, self.bob)
        self.assertIsNone(profiles.get_default_profile(self.bob))   # access ended, so no default
        profiles.set_default_profile(self.alice, None)
        self.assertIsNone(profiles.get_default_profile(self.alice))

    def test_a_studio_opens_with_the_default_unless_this_browser_chose(self):
        profiles.set_default_profile(self.alice, self.mine)
        stale = {'body': {'height': 199.0}, 'skin': None}
        # No choice here (a new browser, or storage reset by a deploy): the default.
        choice, body, skin = self.studio(self.alice, stale)
        self.assertEqual((choice, body['height'], skin), (self.mine, 160.0, '#a07e56'))
        choice, body, _ = self.studio(self.alice, None)
        self.assertEqual((choice, body['height']), (self.mine, 160.0))
        # An explicit choice made in this browser wins.
        choice, body, _ = self.studio(self.alice, dict(stale, body_choice='__default__'))
        self.assertEqual((choice, body['height']), ('__default__', 199.0))
        # A chosen profile is reread, so account edits apply.
        profiles.update_profile(self.alice, self.mine, dict(profiles.default_measurements('female'), height=158.0))
        choice, body, _ = self.studio(self.alice, dict(stale, body_choice=self.mine))
        self.assertEqual(body['height'], 158.0)
        # A guest, or someone without a default, keeps the draft's body.
        self.assertEqual(self.studio(None, stale)[1], {'height': 199.0})
        self.assertEqual(self.studio(self.bob, stale)[1], {'height': 199.0})

    def test_a_profile_you_lost_access_to_keeps_its_numbers_not_its_link(self):
        share = Access(self.alice).ensure('body', self.mine)
        Access(self.alice).add_member(share, self.bob)
        snapshot = {'body': {'height': 170.0}, 'body_choice': f'shared:{self.mine}'}
        self.assertEqual(self.studio(self.bob, snapshot)[1]['height'], 160.0)
        Access(self.alice).remove_member(share, self.bob)
        choice, body, _ = self.studio(self.bob, snapshot)
        self.assertEqual((choice, body), ('__custom__', {'height': 170.0}))

    def test_arm_pose_is_an_account_setting_kept_over_every_body(self):
        self.assertIsNone(profiles.get_arm_pose(self.alice))
        self.assertEqual(profiles.set_arm_pose(self.alice, 100), profiles.ARM_POSE_RANGE[1])
        self.assertEqual(profiles.set_arm_pose(self.alice, 38.24), 38.2)
        self.assertEqual(profiles.get_arm_pose(self.alice), 38.2)
        from gui.gui_pattern import GUIPattern
        pattern = GUIPattern(draft=False)
        try:
            pattern.set_arm_pose(38.2)
            pattern.set_new_body_params(profiles.default_measurements('male'))
            self.assertEqual(pattern.body_params['arm_pose_angle'], 38.2)
            self.assertEqual(pattern.body_params['height'], profiles.default_measurements('male')['height'])
        finally:
            pattern.release()


class GuidePicturesTest(unittest.TestCase):
    def test_every_measurement_has_a_diagram_drawn_on_the_mannequin(self):
        for key in guide.GUIDE:
            svg = (DIAGRAMS / f'{key}.svg').read_text(encoding='utf-8')
            self.assertIn('data:image/webp;base64,', svg, key)
            self.assertIn('<title>', svg, key)
        self.assertTrue((DIAGRAMS / 'overview.svg').is_file())
        self.assertFalse((DIAGRAMS / 'arm_pose_angle.svg').exists())

    def test_photos_are_credited_and_present(self):
        credits = DIAGRAMS / 'photos' / 'credits.json'
        if not credits.exists():
            self.skipTest('No measurement photos yet')
        entries = json.loads(credits.read_text(encoding='utf-8'))
        allowed = ('Unsplash License', 'Pexels License', 'CC0', 'Public domain', 'CC BY', 'CC BY-SA')
        for key, entry in entries.items():
            self.assertIn(key, guide.GUIDE)
            self.assertTrue((DIAGRAMS / 'photos' / entry['file']).is_file(), key)
            self.assertTrue(entry['author'] and entry['page'].startswith('https://'), key)
            self.assertTrue(entry['license'].startswith(allowed), (key, entry['license']))
            self.assertIsNotNone(guide.photo_for(key))


class SkinToneTest(unittest.TestCase):
    """Depth and undertone vary independently, with human hues throughout."""

    def lab(self, depth, undertone):
        return guide._rgb_lab(guide._hex_rgb(guide.skin_tone_hex(depth, undertone)))

    def test_depth_darkens_every_undertone_without_turning_grey(self):
        for undertone in guide.SKIN_UNDERTONES:
            with self.subTest(undertone):
                lightness = [self.lab(d / 10, undertone)[0] for d in range(11)]
                self.assertEqual(lightness, sorted(lightness, reverse=True))
                self.assertGreater(lightness[0] - lightness[-1], 55)
                _, a, b = self.lab(1, undertone)
                self.assertGreater((a * a + b * b) ** .5, 10)          # deep skin keeps its warmth
                for depth in (0, .5, 1):
                    self.assertGreater(self.lab(depth, undertone)[1], 4)   # never without red

    def test_undertones_run_rosy_to_golden_to_olive(self):
        import math
        for depth in (.15, .5, .85):
            hues = [math.degrees(math.atan2(*self.lab(depth, u)[:0:-1])) for u in ('cool', 'neutral', 'warm', 'olive')]
            self.assertEqual(hues, sorted(hues))
            self.assertGreater(hues[-1] - hues[0], 20)

    def test_a_stored_colour_reads_back_as_its_choices(self):
        for undertone in guide.SKIN_UNDERTONES:
            for depth in (0., .25, .62, 1.):
                with self.subTest(undertone=undertone, depth=depth):
                    found = guide.skin_tone_params(guide.skin_tone_hex(depth, undertone))
                    self.assertEqual(found[1], undertone)
                    self.assertAlmostEqual(found[0], depth, delta=.02)
        self.assertEqual(len(guide.skin_tone_gradient('warm')), 9)


if __name__ == '__main__':
    unittest.main()
