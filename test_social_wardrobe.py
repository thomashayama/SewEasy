"""Access boundaries, mutual friendships, bookmarks and real photo storage."""
from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User, WardrobeShare, FinishedPhoto
from webapp.wardrobe import Wardrobe
from webapp.wardrobe_sharing import WardrobeSharing, ShareUnavailable
from webapp.friends import Friends
from webapp.favorites import Favorites
from webapp import finished_photos
from test_wardrobe import PARAMS, LOOK


def photo_bytes():
    image = Image.new('RGB', (400, 200), '#7c9983')
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = 'Private camera metadata'
    output = BytesIO()
    image.save(output, 'JPEG', exif=exif)
    return output.getvalue()


class SocialWardrobeTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = self.stack.enter_context(TemporaryDirectory())
        engine = create_engine('sqlite:///' + str(Path(temp) / 'social.db'), connect_args={'check_same_thread': False})
        self.stack.callback(engine.dispose)
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(bind=engine)
        for module in ('wardrobe', 'wardrobe_sharing', 'access', 'friends', 'favorites', 'finished_photos'):
            self.stack.enter_context(patch('webapp.' + module + '.SessionLocal', self.sessions))
        with self.sessions() as db:
            db.add_all([User(email=name + '@example.test', name=name.title()) for name in ('alice', 'bob', 'eve')])
            db.commit()
        self.alice, self.bob, self.eve = [Wardrobe(name + '@example.test') for name in ('alice', 'bob', 'eve')]
        self.guest = Wardrobe(storage={})
        self.owner, self.reader = WardrobeSharing(self.alice), WardrobeSharing(self.bob)
        self.garment = self.alice.save_garment('Oxford', PARAMS, LOOK)
        self.share = self.owner.ensure('garment', self.garment['id'])

    def make_friends(self):
        identity = Friends(self.alice.email).request(self.bob.email)
        Friends(self.bob.email).accept(identity)
        return identity

    def test_only_recipient_can_accept_and_only_members_can_remove(self):
        a, b, e = [Friends(s.email) for s in (self.alice, self.bob, self.eve)]
        identity = a.request(' BOB@EXAMPLE.TEST ')
        self.assertEqual(a.request(self.bob.email), identity)
        self.assertEqual(len(b.list()['incoming']), 1)
        self.assertEqual(e.list(), dict(friends=[], incoming=[], outgoing=[]))
        for actor in (a, e):
            with self.assertRaises(ValueError):
                actor.accept(identity)
        with self.assertRaises(ValueError):
            e.remove(identity)
        with self.assertRaisesRegex(ValueError, 'Accept their request'):
            b.request(self.alice.email)
        b.accept(identity)
        b.accept(identity)  # Idempotent duplicate acceptance.
        self.assertEqual(a.list()['friends'][0]['name'], 'Bob')
        a.remove(identity)
        self.assertEqual(b.list()['friends'], [])

    def test_requests_do_not_disclose_whether_email_is_registered(self):
        service = Friends(self.alice.email)
        for email in (self.bob.email, 'future@example.test'):
            service.request(email)
        self.assertTrue(all(p['name'] == p['email'] for p in service.list()['outgoing']))
        for email in ('bad', self.alice.email, 'bad address@example.test'):
            with self.assertRaises(ValueError):
                service.request(email)
        with self.assertRaises(ValueError):
            Friends(None).request(self.bob.email)

    def test_pending_declined_and_removed_friends_cannot_view_or_fork(self):
        self.owner.set_visibility(self.share, 'friends')
        identity = Friends(self.alice.email).request(self.bob.email)
        self.assertEqual(self.reader.shared_with_me(), [])
        with self.assertRaises(ShareUnavailable):
            self.reader.get(self.share)
        Friends(self.bob.email).accept(identity)
        self.assertEqual(self.reader.shared_with_me()[0]['id'], self.share)
        self.reader.fork(self.share)
        Friends(self.bob.email).remove(identity)
        self.assertEqual(self.reader.shared_with_me(), [])
        with self.assertRaises(ShareUnavailable):
            self.reader.fork(self.share)
        self.assertEqual(len(self.bob.read()['garments']), 1)  # Existing independent copies remain.

    def test_public_is_discoverable_but_private_friends_and_links_are_not(self):
        guest = WardrobeSharing(self.guest)
        for mode in ('private', 'friends', 'link'):
            self.owner.set_visibility(self.share, mode)
            self.assertEqual(guest.discover(), [])
        self.owner.set_visibility(self.share, 'public')
        result = guest.discover('oXfOrD')
        self.assertEqual(result[0]['snapshot']['name'], 'Oxford')
        self.assertNotIn('owner_key', result[0])
        self.assertNotIn('alice@example.test', json.dumps(result))
        self.assertEqual(guest.discover('missing'), [])
        self.owner.set_visibility(self.share, 'private')
        self.assertEqual(guest.discover(), [])
        with self.assertRaises(ShareUnavailable):
            guest.get(self.share)

    def test_invites_are_independent_and_stop_sharing_revokes_all_access(self):
        self.make_friends()
        self.owner.invite(self.share, self.bob.email)
        self.owner.set_visibility(self.share, 'friends')
        self.assertEqual(len(self.reader.shared_with_me()), 1)
        self.owner.set_visibility(self.share, 'private')
        self.reader.get(self.share)
        self.owner.stop_sharing(self.share)
        self.assertEqual(self.owner.settings(self.share)['recipients'], [])
        with self.assertRaises(ShareUnavailable):
            self.reader.get(self.share)
        for mode in ('public', 'friends', 'link', 'private'):
            with self.assertRaises(ShareUnavailable):
                self.reader.set_visibility(self.share, mode)
        with self.assertRaises(ShareUnavailable):
            self.reader.stop_sharing(self.share)

    def test_legacy_links_are_unlisted_and_new_copies_private(self):
        with self.sessions() as db:
            row = db.get(WardrobeShare, self.share)
            row.public_link, row.visibility = True, None
            db.commit()
        self.assertEqual(self.owner.settings(self.share)['visibility'], 'link')
        self.assertEqual(self.reader.discover(), [])
        copy = self.reader.fork(self.share)
        own_copy = self.reader.ensure('garment', copy['id'])
        self.assertEqual(self.reader.settings(own_copy)['visibility'], 'private')
        self.reader.set_visibility(own_copy, 'public')
        snapshot = self.reader.get(own_copy)['snapshot']
        self.assertNotIn('share_id', snapshot['forked_from'])
        self.assertEqual(snapshot['forked_from']['owner_name'], 'Alice')

    def test_favorites_follow_latest_design_and_revocation(self):
        self.owner.set_visibility(self.share, 'public')
        favorites = Favorites(self.bob)
        favorites.set('share', self.share, True)
        favorites.set('share', self.share, True)
        self.assertEqual(len(favorites.list()), 1)
        self.alice.save_garment('Oxford updated', PARAMS, LOOK, parent_id=self.garment['id'])
        self.assertEqual(favorites.list()[0]['snapshot']['name'], 'Oxford updated')
        self.owner.stop_sharing(self.share)
        self.assertEqual(favorites.list(), [])
        favorites.set('share', self.share, False)
        self.assertEqual(favorites.keys(), set())

    def test_own_garment_and_outfit_favorites_are_account_scoped(self):
        outfit = self.alice.save_outfit('Work', [self.garment['id']])
        favorites = Favorites(self.alice)
        favorites.set('garment', self.garment['id'], True)
        favorites.set('outfit', outfit['id'], True)
        self.assertEqual(len(favorites.list()), 2)
        self.assertEqual(Favorites(self.bob).list(), [])
        with self.assertRaises(ValueError):
            Favorites(self.bob).set('garment', self.garment['id'], True)
        with self.assertRaises(ValueError):
            Favorites(self.guest).set('share', self.share, True)

    def test_own_public_favorite_is_the_same_as_library_favorite(self):
        self.owner.set_visibility(self.share, 'public')
        favorites = Favorites(self.alice)
        favorites.set('garment', self.garment['id'], True)
        favorites.set('share', self.share, True)
        self.assertEqual(len(favorites.list()), 1)
        self.assertEqual(favorites.keys(), {'garment:' + self.garment['id']})
        favorites.set('share', self.share, False)
        self.assertEqual(favorites.list(), [])

    def test_concurrent_uploads_cannot_exceed_photo_limit(self):
        from concurrent.futures import ThreadPoolExecutor
        data = photo_bytes()
        for _ in range(7):
            finished_photos.add(self.alice, 'garment', self.garment['id'], data)
        def upload():
            try:
                return finished_photos.add(self.alice, 'garment', self.garment['id'], data)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: upload(), range(2)))
        self.assertEqual(sum(bool(result) for result in results), 1)
        self.assertEqual(len(finished_photos.list_photos(self.alice, 'garment', self.garment['id'])), 8)

    def test_photos_strip_metadata_correct_orientation_and_attach_to_item(self):
        identity = finished_photos.add(self.alice, 'garment', self.garment['id'], photo_bytes(), 'My first sewn shirt')
        with self.sessions() as db:
            row = db.get(FinishedPhoto, identity)
            image = Image.open(BytesIO(row.image))
            self.assertEqual(image.size, (200, 400))
            self.assertEqual(image.format, 'WEBP')
            self.assertEqual(dict(image.getexif()), {})
            self.assertEqual(row.item_id, self.garment['id'])
        self.assertEqual(finished_photos.list_photos(self.alice, 'garment', self.garment['id'])[0]['caption'], 'My first sewn shirt')
        copy = self.alice.import_fork('garment', self.garment, {'name': 'Oxford'})
        self.assertEqual(finished_photos.list_photos(self.alice, 'garment', copy['id']), [])

    def test_photo_urls_recheck_private_friend_and_public_access(self):
        identity = finished_photos.add(self.alice, 'garment', self.garment['id'], photo_bytes())
        app = FastAPI()
        finished_photos.register(app)
        def user(request):
            email = request.headers.get('x-test-user')
            return {'email': email} if email else None
        with patch('webapp.finished_photos.auth.current_user', user), TestClient(app) as client:
            own, shared = f'/finished-photos/{identity}', f'/shared-photos/{self.share}/{identity}'
            self.assertEqual(client.get(own).status_code, 404)
            self.assertEqual(client.get(own, headers={'x-test-user': self.bob.email}).status_code, 404)
            self.assertEqual(client.get(own, headers={'x-test-user': self.alice.email}).status_code, 200)
            self.assertEqual(client.get(shared).status_code, 404)
            relationship = self.make_friends()
            self.owner.set_visibility(self.share, 'friends')
            self.assertEqual(client.get(shared, headers={'x-test-user': self.bob.email}).status_code, 200)
            Friends(self.alice.email).remove(relationship)
            self.assertEqual(client.get(shared, headers={'x-test-user': self.bob.email}).status_code, 404)
            self.owner.set_visibility(self.share, 'public')
            response = client.get(shared)
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['cache-control'])
            self.owner.stop_sharing(self.share)
            self.assertEqual(client.get(shared).status_code, 404)

    def test_photo_validation_ownership_and_item_binding(self):
        for invalid in (b'', b'<svg>not a photo</svg>', b'x' * (finished_photos.MAX_BYTES + 1)):
            with self.assertRaises(ValueError):
                finished_photos.add(self.alice, 'garment', self.garment['id'], invalid)
        with self.assertRaises(ValueError):
            finished_photos.add(self.bob, 'garment', self.garment['id'], photo_bytes())
        identity = finished_photos.add(self.alice, 'garment', self.garment['id'], photo_bytes())
        other = self.alice.save_garment('Other shirt', PARAMS, LOOK, new=True)
        other_share = self.owner.ensure('garment', other['id'])
        self.owner.set_visibility(other_share, 'public')
        with self.assertRaises(ValueError):
            finished_photos.image_for(self.guest, identity, other_share)
        with self.assertRaises(ValueError):
            finished_photos.remove(self.bob, identity)
        finished_photos.remove(self.alice, identity)
        self.assertEqual(finished_photos.list_photos(self.alice, 'garment', self.garment['id']), [])

    def test_outfit_photos_and_upload_limit(self):
        outfit = self.alice.save_outfit('Outfit', [self.garment['id']])
        for _ in range(finished_photos.MAX_PHOTOS):
            finished_photos.add(self.alice, 'outfit', outfit['id'], photo_bytes())
        with self.assertRaisesRegex(ValueError, 'eight'):
            finished_photos.add(self.alice, 'outfit', outfit['id'], photo_bytes())
        self.assertEqual(len(finished_photos.list_photos(self.alice, 'outfit', outfit['id'])), 8)


class SocialMigrationTest(unittest.TestCase):
    def test_additive_migration_preserves_legacy_private_and_unlisted_rows(self):
        from webapp import db as module
        with TemporaryDirectory() as folder:
            engine = create_engine('sqlite:///' + str(Path(folder) / 'legacy.db'))
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE wardrobe_shares (id VARCHAR PRIMARY KEY, owner_key VARCHAR NOT NULL, '
                                  'owner_name VARCHAR NOT NULL, kind VARCHAR NOT NULL, revision_id VARCHAR NOT NULL, '
                                  'snapshot JSON NOT NULL, thumbnail TEXT, public_link BOOLEAN NOT NULL, '
                                  'created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)'))
                conn.execute(text("INSERT INTO wardrobe_shares VALUES ('old', 'account:alice@example.test', 'Alice', 'garment', 'g', '{}', NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            with patch.object(module, 'engine', engine):
                module.init_db()
                module.init_db()
            with engine.connect() as conn:
                self.assertEqual(tuple(conn.execute(text('SELECT id, public_link, visibility FROM wardrobe_shares')).one()), ('old', 1, None))
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
