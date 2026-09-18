"""Private-by-default access, immutable histories, ownership and fork provenance."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User
from webapp.wardrobe import Wardrobe, latest_garments
from webapp.wardrobe_sharing import WardrobeSharing, ShareUnavailable
from test_wardrobe import PARAMS, LOOK


class SharingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + str(Path(self.tmp.name) / 'test.db'))
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([User(email='alice@example.com', name='Alice'), User(email='bob@example.com', name='Bob'),
                        User(email='mallory@example.com', name='Mallory')])
            db.commit()
        self.patches = [patch('webapp.' + module + '.SessionLocal', self.sessions) for module in ('wardrobe', 'wardrobe_sharing')]
        for p in self.patches:
            p.start()
        self.alice, self.bob, self.mallory = [Wardrobe(email=email + '@example.com') for email in ('alice', 'bob', 'mallory')]
        self.owner, self.reader = WardrobeSharing(self.alice), WardrobeSharing(self.bob)
        self.guest = WardrobeSharing(Wardrobe(storage={}))
        self.g = self.alice.save_garment('Oxford', PARAMS, LOOK)
        self.token = self.owner.ensure('garment', self.g['id'])

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_private_default_and_owner_only_controls(self):
        self.assertEqual(self.owner.settings(self.token), dict(public_link=False, visibility='private', recipients=[]))
        self.assertEqual(self.owner.ensure('garment', self.g['id']), self.token)
        for viewer in (self.reader, self.guest, WardrobeSharing(self.mallory)):
            for action in (lambda: viewer.get(self.token), lambda: viewer.fork(self.token),
                           lambda: viewer.settings(self.token), lambda: viewer.set_link(self.token, True),
                           lambda: viewer.invite(self.token, 'attacker@example.com'),
                           lambda: viewer.revoke_invitation(self.token, 'bob@example.com')):
                with self.assertRaises(ShareUnavailable):
                    action()
            with self.assertRaises(ValueError):
                viewer.ensure('garment', self.g['id'])

    def test_link_access_tracks_saved_item_and_is_revocable(self):
        self.owner.set_link(self.token, True)
        first = self.guest.get(self.token)
        params = deepcopy(PARAMS)
        params['fabric']['kind']['v'] = 'stripe'
        second = self.alice.save_garment('Renamed', params, LOOK, parent_id=self.g['id'])
        self.assertEqual(second['id'], self.g['id'])
        self.assertEqual(self.guest.get(self.token)['snapshot']['params'], params)
        first['snapshot']['params']['meta'].clear()
        self.assertEqual(self.owner.get(self.token)['snapshot']['params'], params)
        new_token = self.owner.ensure('garment', second['id'])
        self.assertEqual(new_token, self.token)
        self.guest.get(new_token)
        self.owner.set_link(self.token, False)
        with self.assertRaises(ShareUnavailable):
            self.guest.fork(self.token)

    def test_email_invites_and_links_are_independent(self):
        self.owner.invite(self.token, ' BOB@EXAMPLE.COM ')
        self.owner.invite(self.token, 'bob@example.com')
        self.owner.invite(self.token, 'future@example.com')
        self.assertEqual(len(self.reader.shared_with_me()), 1)
        self.assertEqual(self.reader.get(self.token)['owner_name'], 'Alice')
        with self.assertRaises(ShareUnavailable):
            self.guest.get(self.token)
        self.assertEqual(len(WardrobeSharing(Wardrobe('future@example.com')).shared_with_me()), 1)
        self.owner.set_link(self.token, True)
        self.owner.set_link(self.token, False)
        self.reader.get(self.token)  # Turning off a public link leaves the invitation intact.
        self.owner.revoke_invitation(self.token, 'bob@example.com')
        self.assertEqual(self.reader.shared_with_me(), [])
        with self.assertRaises(ShareUnavailable):
            self.reader.fork(self.token)  # A page opened before revocation cannot fork.
        for email in ('', 'bad', 'one two@example.com', 'alice@example.com'):
            with self.assertRaises(ValueError):
                self.owner.invite(self.token, email)

    def test_fork_has_new_owner_identity_and_preserves_appearance(self):
        self.owner.invite(self.token, 'bob@example.com')
        existing = self.bob.save_garment('Oxford', PARAMS, LOOK)
        fork = self.reader.fork(self.token)
        self.assertNotEqual(existing['id'], fork['id'])
        self.assertNotEqual(fork['id'], self.g['id'])
        self.assertEqual(fork['name'], 'Oxford (copy)')
        self.assertNotIn('version', fork)
        self.assertEqual(fork['appearance'], LOOK)
        self.assertEqual(fork['forked_from']['revision_id'], self.g['id'])
        edited = self.bob.save_garment('My Oxford', PARAMS, {'fabric_color': '#ffffff'}, parent_id=fork['id'])
        self.assertEqual(edited['id'], fork['id'])
        self.assertEqual(edited['forked_from'], fork['forked_from'])
        self.assertEqual(len(self.bob.read()['garments']), 2)
        self.assertEqual(len(self.alice.read()['garments']), 1)
        self.owner.revoke_invitation(self.token, 'bob@example.com')
        self.assertEqual(self.bob.revision('garment', fork['id']), edited)
        with self.assertRaises(ValueError):
            self.alice.revision('garment', fork['id'])

    def test_outfit_copy_keeps_its_own_members_and_does_not_fill_garment_library(self):
        old = self.alice.save_outfit('Workday', [self.g['id'], self.g['id']])
        token = self.owner.ensure('outfit', old['id'])
        self.owner.set_link(token, True)
        fork = self.reader.fork(token)
        self.assertEqual(len(fork['garments']), 2)
        self.assertEqual(fork['garments'][0], fork['garments'][1])
        self.assertEqual(self.bob.read()['garments'], [])
        self.assertEqual(fork['garments'][0]['appearance'], LOOK)
        self.assertEqual(fork['forked_from']['revision_id'], old['id'])
        second = self.alice.save_garment('Oxford', PARAMS, {'fabric_color': '#000000'}, parent_id=self.g['id'])
        latest = self.alice.save_outfit('New workday', [second['id']], parent_id=old['id'])
        self.assertEqual(latest['id'], old['id'])
        self.assertEqual(len(self.alice.read()['outfits']), 1)
        self.assertEqual(self.reader.get(token)['snapshot']['name'], 'New workday')
        self.assertEqual(self.bob.read()['outfits'][0], fork)

    def test_no_private_library_or_measurements_in_share(self):
        # Older records can contain extra application metadata. Only the
        # explicit share snapshot fields cross the privacy boundary.
        with self.alice._edit() as library:
            library['garments'][0]['body'] = {'height': 180}
            library['garments'][0]['owner_email'] = 'alice@example.com'
            library['garments'][0]['private_note'] = 'secret'
        from webapp.models import WardrobeShare
        with self.sessions() as db:
            db.delete(db.get(WardrobeShare, self.token))
            db.commit()
        token = self.owner.ensure('garment', self.g['id'])
        self.owner.set_link(token, True)
        data = self.guest.get(token)
        self.assertNotIn('owner_key', data)
        self.assertNotIn('recipients', data)
        self.assertNotIn('body', data['snapshot'])
        self.assertNotIn('owner_email', data['snapshot'])
        self.assertNotIn('private_note', data['snapshot'])

    def test_fork_preserves_all_panel_materials_and_default_body_thumbnail(self):
        from test_thumbnails import raster
        from webapp.thumbnail_cache import thumbnail_key
        look = dict(LOOK, panel_fabrics={'front': {'kind': {'v': 'stripe'}, 'scale': {'v': .5}}},
                    panel_stiffness={'front': .8}, panel_materials={'back': 'linen'})
        garment = self.alice.save_garment('Linen', PARAMS, look, new=True)
        token = self.owner.ensure('garment', garment['id'])
        self.alice.save_thumbnail('garment', garment['id'], raster())
        self.assertEqual(self.owner.ensure('garment', garment['id']), token)
        self.owner.set_link(token, True)
        fork = self.reader.fork(token)
        self.assertEqual(fork['appearance'], look)
        self.assertIn(thumbnail_key('garment', fork['id']), self.bob.read()['thumbnails'])
        self.assertNotIn(thumbnail_key('garment', garment['id']), self.bob.read()['thumbnails'])

    def test_outfit_image_is_copied_to_the_fork_id_and_visible_to_invitees(self):
        from test_thumbnails import raster
        from webapp.thumbnail_cache import thumbnail_key
        outfit = self.alice.save_outfit('Work', [self.g['id']])
        image = self.alice.save_thumbnail('outfit', outfit['revision_id'], raster())
        token = self.owner.ensure('outfit', outfit['revision_id'])
        self.owner.invite(token, 'bob@example.com')
        self.assertEqual(self.reader.shared_with_me()[0]['thumbnail'], image)
        fork = self.reader.fork(token)
        self.assertEqual(self.bob.read()['thumbnails'][thumbnail_key('outfit', fork['revision_id'])], image)
        self.assertNotEqual(fork['revision_id'], outfit['revision_id'])

    def test_guest_ownership_survives_service_reload_and_does_not_cross_sessions(self):
        storage = {}
        a = Wardrobe(storage=storage)
        g = a.save_garment('Guest shirt', PARAMS, LOOK)
        share = WardrobeSharing(a)
        token = share.ensure('garment', g['id'])
        WardrobeSharing(Wardrobe(storage=storage)).set_link(token, True)
        fork = self.guest.fork(token)
        self.assertEqual(fork['forked_from']['owner_name'], 'Guest designer')
        with self.assertRaises(ShareUnavailable):
            self.guest.set_link(token, False)

    def test_concurrent_copies_are_independent_and_stale_saves_cannot_overwrite(self):
        def save(i):
            return Wardrobe('alice@example.com').import_fork('garment', self.g, {'name': 'Oxford'})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(save, range(6)))
        self.assertEqual(len({g['id'] for g in results}), 6)
        self.assertEqual(len({g['name'] for g in results}), 6)
        self.assertEqual(len(self.alice.read()['garments']), 7)
        self.alice.save_garment('Oxford', PARAMS, LOOK, parent_id=self.g['id'], expected_updated_at=self.g['updated_at'])
        with self.assertRaisesRegex(ValueError, 'another tab'):
            self.alice.save_garment('Lost update', PARAMS, LOOK, parent_id=self.g['id'], expected_updated_at=self.g['updated_at'])

    def test_legacy_migration_is_stable_and_preserves_named_snapshots(self):
        first = dict(id='g1', name='Old shirt', version=1, params=PARAMS, appearance=LOOK)
        second = dict(first, id='g2', version=2)
        outfit = dict(id='o1', name='Old outfit', garments=[deepcopy(first)], updated_at='2026-01-01')
        storage = {'wardrobe': dict(garments=[first, second], outfits=[outfit])}
        store = Wardrobe(storage=storage)
        migrated = store.read()
        self.assertEqual(migrated, store.read())
        self.assertEqual(len(latest_garments(migrated)), 2)
        self.assertEqual([g['name'] for g in migrated['garments']], ['Old shirt (copy)', 'Old shirt'])
        self.assertTrue(all('version' not in g for g in migrated['garments']))
        third = store.save_garment('Renamed', PARAMS, LOOK, parent_id='g2')
        self.assertEqual(third['id'], 'g2')
        updated = store.save_outfit('Updated', [third['id']], parent_id='o1')
        self.assertEqual(updated['id'], 'o1')
        self.assertEqual(len(store.read()['outfits']), 1)
        self.assertEqual(migrated['outfits'][0]['garments'][0]['params'], PARAMS)
        self.assertNotIn('outfit_revisions', store.read())


if __name__ == '__main__':
    unittest.main()
