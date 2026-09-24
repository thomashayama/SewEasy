"""One access model for garments, outfits, fabrics and body profiles: private by
default, public and link access, viewer/admin members, a single transferable owner."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp import fabrics, profiles
from webapp.access import Access, NotAllowed, ShareUnavailable, migrate_profile_shares
from webapp.db import Base
from webapp.models import BodyProfileShare, User, WardrobeFavorite, WardrobeShare
from webapp.wardrobe import Wardrobe
from webapp.wardrobe_sharing import WardrobeSharing
from test_wardrobe import PARAMS, LOOK

BODY = {'height': 170.0, 'waist': 72.0}
MODULES = ('access', 'wardrobe', 'wardrobe_sharing', 'fabrics', 'profiles', 'friends', 'favorites',
           'fabric_favorites', 'finished_photos')


class AccessTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(TemporaryDirectory())
        self.engine = create_engine('sqlite:///' + str(Path(folder) / 'access.db'),
                                    connect_args={'check_same_thread': False})
        self.stack.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        for module in MODULES:
            self.stack.enter_context(patch(f'webapp.{module}.SessionLocal', self.sessions))
        with self.sessions() as db:
            db.add_all([User(email=f'{name}@example.test', name=name.title())
                        for name in ('alice', 'bob', 'carol', 'dave')])
            db.commit()
        self.alice, self.bob, self.carol, self.dave = (f'{n}@example.test' for n in ('alice', 'bob', 'carol', 'dave'))
        self.wardrobe = Wardrobe(self.alice)
        garment = self.wardrobe.save_garment('Oxford', PARAMS, LOOK)
        outfit = self.wardrobe.save_outfit('Workday', [garment['id']])
        fabric = fabrics.create_fabric(self.alice, 'Linen')
        profiles.save_profile(self.alice, 'Me', dict(BODY))
        body = profiles.list_profiles(self.alice)[0]
        self.items = dict(garment=garment['id'], outfit=outfit['id'], fabric=fabric['id'], body=body['id'])
        owner = WardrobeSharing(self.wardrobe)
        self.shares = {kind: owner.ensure(kind, item_id) for kind, item_id in self.items.items()}

    def access(self, email):
        return WardrobeSharing(Wardrobe(email))

    def can_open(self, email, kind):
        """Opening the item itself, the way each kind's own screens do."""
        if kind == 'fabric':
            try:
                return fabrics.get_fabric(email, self.items['fabric'])['role']
            except ValueError:
                return None
        if kind == 'body':
            data = profiles.get_profile(email, self.items['body'])
            return data and data['role']
        return Access(email).role(self.shares[kind])

    def test_every_kind_starts_private_and_owned_by_its_creator(self):
        for kind, share in self.shares.items():
            self.assertEqual(Access(self.alice).settings(share)['visibility'], 'private', kind)
            self.assertEqual(self.can_open(self.alice, kind), 'owner', kind)
            for stranger in (self.bob, None):
                self.assertIsNone(self.can_open(stranger, kind), kind)
                with self.assertRaises(ShareUnavailable):
                    Access(stranger).get(share)
        self.assertEqual(Access(self.bob).shared_with_me(), [])
        # A copy is a new, private item: it gets no access record of its own.
        copy = fabrics.copy_fabric(self.alice, self.items['fabric'])
        with self.sessions() as db:
            self.assertEqual(db.query(WardrobeShare).filter_by(revision_id=copy['id']).count(), 0)

    def test_public_and_link_access_make_viewers_only(self):
        for kind, share in self.shares.items():
            Access(self.alice).set_visibility(share, 'link')
            self.assertEqual(self.can_open(None, kind), 'viewer', kind)
            self.assertEqual(Access(None).discover(kinds=(kind,)), [])
            Access(self.alice).set_visibility(share, 'public')
            found = Access(None).discover(kinds=(kind,))
            self.assertEqual([f['id'] for f in found], [share])
            self.assertNotIn('alice@example.test', repr(found))
            for action in (lambda: Access(self.dave).set_visibility(share, 'private'),
                           lambda: Access(self.dave).add_member(share, self.dave, 'admin'),
                           lambda: Access(self.dave).delete(share),
                           lambda: Access(self.dave).transfer(share, self.dave)):
                with self.assertRaises(NotAllowed):
                    action()
        self.assertEqual({f['kind'] for f in Access(None).discover()}, set(self.shares))

    def test_viewers_view_and_copy_but_change_nothing(self):
        owner = Access(self.alice)
        for share in self.shares.values():
            owner.add_member(share, self.bob, 'viewer')
        self.assertEqual({v['kind']: v['role'] for v in Access(self.bob).shared_with_me()},
                         dict.fromkeys(self.shares, 'viewer'))
        for kind in self.shares:
            self.assertEqual(self.can_open(self.bob, kind), 'viewer')
        # Save a copy: a new item Bob owns, in each kind's own library.
        fork = self.access(self.bob).fork(self.shares['garment'])
        self.assertEqual(Wardrobe(self.bob).revision('garment', fork['id'])['forked_from']['owner_name'], 'Alice')
        self.access(self.bob).fork(self.shares['outfit'])
        copy = fabrics.copy_fabric(self.bob, self.items['fabric'])
        self.assertEqual(copy['role'], 'owner')
        self.assertEqual(profiles.copy_profile(self.bob, self.items['body']), 'Me')
        self.assertEqual(profiles.list_profiles(self.bob)[0]['name'], 'Me')
        # Changing the original is not a viewer's to do.
        record = fabrics.get_fabric(self.bob, self.items['fabric'])
        with self.assertRaisesRegex(ValueError, 'owner or an admin'):
            fabrics.update_fabric(self.bob, record['id'], record['edit_token'], name='Mine', description='', values={})
        with self.assertRaisesRegex(ValueError, 'owner or an admin'):
            fabrics.delete_fabric(self.bob, self.items['fabric'])
        with self.assertRaisesRegex(ValueError, 'owner or an admin'):
            profiles.update_profile(self.bob, self.items['body'], dict(BODY, height=1.0))
        self.assertFalse(profiles.delete_profile(self.bob, self.items['body']))
        with self.assertRaises(NotAllowed):
            self.access(self.bob).save_garment(self.shares['garment'], 'Mine', PARAMS, LOOK)
        for share in self.shares.values():
            for action in (lambda: Access(self.bob).settings(share),
                           lambda: Access(self.bob).set_visibility(share, 'public'),
                           lambda: Access(self.bob).add_member(share, self.dave),
                           lambda: Access(self.bob).set_role(share, self.bob, 'admin'),
                           lambda: Access(self.bob).stop_sharing(share),
                           lambda: Access(self.bob).delete(share),
                           lambda: Access(self.bob).transfer(share, self.bob)):
                with self.assertRaises(NotAllowed):
                    action()
        self.assertEqual(len(self.wardrobe.read()['garments']), 1)
        self.assertEqual(profiles.get_profile(self.alice, self.items['body'])['measurements'], BODY)

    def test_admins_edit_share_and_delete_but_cannot_transfer(self):
        owner, admin = Access(self.alice), Access(self.carol)
        for share in self.shares.values():
            owner.add_member(share, self.carol, 'admin')
        # Content: saved into the owner's own library, not a copy.
        garment = self.wardrobe.revision('garment', self.items['garment'])
        edited = self.access(self.carol).save_garment(self.shares['garment'], 'Oxford blue', PARAMS,
                                                      dict(LOOK, fabric_color='#0000ff'), garment['updated_at'])
        self.assertEqual(edited['id'], garment['id'])
        self.assertEqual(self.wardrobe.revision('garment', garment['id'])['name'], 'Oxford blue')
        self.assertEqual(Wardrobe(self.carol).read()['garments'], [])
        outfit = self.wardrobe.revision('outfit', self.items['outfit'])
        self.access(self.carol).save_outfit(self.shares['outfit'], 'Weekend', outfit['garments'], outfit['updated_at'])
        self.assertEqual(self.wardrobe.revision('outfit', outfit['id'])['name'], 'Weekend')
        record = fabrics.get_fabric(self.carol, self.items['fabric'])
        self.assertEqual((record['role'], record['owner_name']), ('admin', 'Alice'))
        fabrics.update_fabric(self.carol, record['id'], record['edit_token'], name='Irish linen',
                              description='Heavy', values={'weight': '190'})
        self.assertEqual(fabrics.get_fabric(self.alice, record['id'])['name'], 'Irish linen')
        self.assertEqual(owner.settings(self.shares['fabric'])['name'], 'Irish linen')   # Listings follow renames.
        profiles.update_profile(self.carol, self.items['body'], dict(BODY, height=171.0))
        self.assertEqual(profiles.get_profile(self.alice, self.items['body'])['measurements']['height'], 171.0)
        # Settings: general access, members and roles, other admins included.
        for share in self.shares.values():
            admin.set_visibility(share, 'public')
            admin.add_member(share, self.dave, 'admin')
            admin.set_role(share, self.dave, 'viewer')
            self.assertEqual(admin.settings(share)['members'],
                             [dict(email=self.carol, role='admin'), dict(email=self.dave, role='viewer')])
            with self.assertRaisesRegex(ValueError, 'owns'):
                admin.add_member(share, self.alice)
            with self.assertRaises(NotAllowed):
                admin.transfer(share, self.dave)
        # Deletion: the item, its record, members and bookmarks go; forks stay theirs.
        fork = self.access(self.dave).fork(self.shares['garment'])
        with self.sessions() as db:
            db.add(WardrobeFavorite(owner_email=self.dave, kind='share', item_id=self.shares['garment']))
            db.commit()
        for kind, share in self.shares.items():
            admin.delete(share)
            self.assertIsNone(self.can_open(self.alice, kind), kind)
            with self.assertRaises(ShareUnavailable):
                Access(self.alice).get(share)
        self.assertEqual(self.wardrobe.read()['garments'], [])
        self.assertEqual(fabrics.list_fabrics(self.alice), [])
        self.assertEqual(profiles.list_profiles(self.alice), [])
        self.assertEqual(Wardrobe(self.dave).revision('garment', fork['id'])['name'], 'Oxford blue (copy)')
        with self.sessions() as db:
            self.assertEqual(db.query(WardrobeShare).count(), 0)
            self.assertEqual(db.query(WardrobeFavorite).filter_by(owner_email=self.dave).count(), 0)

    def test_owner_transfers_to_a_member_and_stays_as_admin(self):
        owner = Access(self.alice)
        Wardrobe(self.bob).save_garment('Oxford', PARAMS, LOOK)
        profiles.save_profile(self.bob, 'Me', dict(BODY))
        for kind, share in self.shares.items():
            with self.assertRaisesRegex(ValueError, 'Add them'):
                owner.transfer(share, self.bob)
            owner.add_member(share, 'new@example.test')
            with self.assertRaisesRegex(ValueError, 'sign in'):
                owner.transfer(share, 'new@example.test')
            owner.add_member(share, self.bob, 'viewer')
            owner.transfer(share, self.bob)
            self.assertEqual(self.can_open(self.bob, kind), 'owner', kind)
            self.assertEqual(self.can_open(self.alice, kind), 'admin', kind)
            settings = Access(self.bob).settings(share)
            self.assertEqual((settings['role'], settings['owner_name']), ('owner', 'Bob'))
            self.assertIn(dict(email=self.alice, role='admin'), settings['members'])
            self.assertNotIn(self.bob, settings['recipients'])
            with self.assertRaises(NotAllowed):
                owner.transfer(share, self.alice)   # Only one owner, and it's Bob now.
        # The item moved: same ID and link, a free name, gone from Alice's lists.
        moved = Wardrobe(self.bob).revision('garment', self.items['garment'])
        self.assertEqual(moved['name'], 'Oxford (2)')
        self.assertEqual(self.wardrobe.read()['garments'], [])
        self.assertEqual(Wardrobe(self.bob).revision('outfit', self.items['outfit'])['name'], 'Workday')
        self.assertEqual([f['name'] for f in fabrics.list_fabrics(self.bob)], ['Linen'])
        self.assertEqual(fabrics.list_fabrics(self.alice), [])
        self.assertEqual(sorted(p['name'] for p in profiles.list_profiles(self.bob)), ['Me', 'Me (2)'])
        self.assertEqual([p['name'] for p in profiles.shared_profiles(self.alice)], ['Me (2)'])
        # The former owner, as an admin, still edits it in Bob's library.
        self.access(self.alice).save_garment(self.shares['garment'], 'Oxford (2)', PARAMS, {'fabric_color': '#fff'})
        self.assertEqual(Wardrobe(self.bob).revision('garment', moved['id'])['appearance'], {'fabric_color': '#fff'})

    def test_purchase_notes_stay_with_the_owner(self):
        record = fabrics.get_fabric(self.alice, self.items['fabric'])
        source = dict(url='https://www.etsy.com/listing/123', private_note='Ask Sam for the discount')
        record = fabrics.update_fabric(self.alice, record['id'], record['edit_token'], name='Linen', description='',
                                       values={}, sources=[source])
        Access(self.alice).add_member(self.shares['fabric'], self.carol, 'admin')
        Access(self.alice).set_visibility(self.shares['fabric'], 'link')
        for email in (self.carol, None):
            seen = fabrics.get_fabric(email, record['id'])['content']['purchase_sources']
            self.assertEqual(seen[0]['private_note'], '')
            self.assertNotIn('Sam', repr(fabrics.listed(email, record['id'])))
        # An admin's save leaves the note in place; nobody but the owner sees it.
        seen = fabrics.get_fabric(self.carol, record['id'])
        fabrics.update_fabric(self.carol, record['id'], seen['edit_token'], name='Linen', description='',
                              values={}, sources=[dict(seen['content']['purchase_sources'][0], variant='Natural')])
        mine = fabrics.get_fabric(self.alice, record['id'])['content']['purchase_sources'][0]
        self.assertEqual((mine['variant'], mine['private_note']), ('Natural', 'Ask Sam for the discount'))
        copy = fabrics.copy_fabric(self.carol, record['id'])
        self.assertEqual(fabrics.get_fabric(self.carol, copy['id'])['content']['purchase_sources'][0]['private_note'], '')
        # A transfer hands over the fabric, not the previous owner's notes.
        Access(self.alice).add_member(self.shares['fabric'], self.bob)
        Access(self.alice).transfer(self.shares['fabric'], self.bob)
        self.assertEqual(fabrics.get_fabric(self.bob, record['id'])['content']['purchase_sources'][0]['private_note'], '')

    def test_stop_sharing_removes_viewers_but_keeps_admins(self):
        share = self.shares['fabric']
        owner = Access(self.alice)
        owner.set_visibility(share, 'public')
        owner.add_member(share, self.bob)
        owner.add_member(share, self.carol, 'admin')
        Access(self.carol).stop_sharing(share)
        settings = owner.settings(share)
        self.assertEqual((settings['visibility'], settings['members']), ('private', [dict(email=self.carol, role='admin')]))
        self.assertIsNone(self.can_open(self.bob, 'fabric'))
        self.assertEqual(self.can_open(self.carol, 'fabric'), 'admin')

    def test_members_can_leave_and_admins_can_remove_each_other(self):
        share = self.shares['body']
        owner = Access(self.alice)
        owner.add_member(share, self.bob)
        owner.add_member(share, self.carol, 'admin')
        owner.add_member(share, self.dave, 'admin')
        Access(self.bob).leave(share)
        self.assertIsNone(self.can_open(self.bob, 'body'))
        Access(self.carol).remove_member(share, self.dave)
        self.assertIsNone(self.can_open(self.dave, 'body'))
        with self.assertRaises(ShareUnavailable):
            Access(self.dave).remove_member(share, self.carol)

    def test_guest_items_have_viewers_but_no_admins_or_transfer(self):
        guest = Wardrobe(storage={})
        garment = guest.save_garment('Guest shirt', PARAMS, LOOK)
        sharing = WardrobeSharing(guest)
        share = sharing.ensure('garment', garment['id'])
        sharing.invite(share, self.bob)
        with self.assertRaisesRegex(ValueError, 'Sign in to add admins'):
            sharing.add_member(share, self.carol, 'admin')
        with self.assertRaisesRegex(ValueError, 'Sign in to share with friends'):
            sharing.set_visibility(share, 'public')
        with self.assertRaisesRegex(ValueError, 'Sign in'):
            sharing.transfer(share, self.bob)
        self.assertEqual(Access(self.bob).role(share), 'viewer')
        sharing.delete(share)
        self.assertEqual(guest.read()['garments'], [])
        self.assertIsNone(Access(self.bob).role(share))

    def test_owner_deleting_from_their_library_clears_access(self):
        Access(self.alice).set_visibility(self.shares['garment'], 'public')
        self.wardrobe.delete_item('garment', self.items['garment'])
        with self.assertRaises(ShareUnavailable):
            Access(None).get(self.shares['garment'])
        self.assertEqual(len(self.wardrobe.read()['outfits'][0]['garments']), 1)   # Outfits embed their pieces.
        with self.assertRaises(ValueError):
            self.wardrobe.delete_item('garment', self.items['garment'])

    def test_legacy_profile_shares_become_viewers(self):
        with self.sessions() as db:
            db.query(WardrobeShare).filter_by(kind='body').delete()
            db.add(BodyProfileShare(profile_id=self.items['body'], recipient_email=self.bob))
            db.add(BodyProfileShare(profile_id=999, recipient_email=self.bob))       # its profile is gone
            db.commit()
        migrate_profile_shares(self.engine)
        migrate_profile_shares(self.engine)
        with self.sessions() as db:
            self.assertEqual(db.query(BodyProfileShare).count(), 0)
        shared = profiles.shared_profiles(self.bob)
        self.assertEqual([(p['name'], p['role'], p['owner_name']) for p in shared], [('Me', 'viewer', 'Alice')])
        settings = Access(self.alice).settings(shared[0]['share_id'])
        self.assertEqual((settings['visibility'], settings['members']), ('private', [dict(email=self.bob, role='viewer')]))


if __name__ == '__main__':
    unittest.main()
