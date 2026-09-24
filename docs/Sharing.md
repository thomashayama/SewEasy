# Named garments and outfits

Each garment or outfit is an independently owned, named item with a stable ID.
**Save** updates that item; **Save a copy** creates a new ID and asks for a name,
defaulting to `Dress shirt (copy)`, then `Dress shirt (copy 2)` if needed. Names
are unique per item type in an owner's library. Renaming retains the ID.

The garment editor opens one piece, with design and fabric controls. It has no
Add garment action. **Create outfit with this** starts a separate outfit draft.
The outfit editor uses the same pattern/3D layout with a garment list and
**Add garment**. Adjustments are embedded in the outfit: saving never silently
changes or adds standalone library garments. Its piece menu offers **Edit
garment separately** and **Save garment as copy**. A return action carries the
edited piece back to the outfit draft.

## Privacy and sharing

Garments, outfits, fabrics and body-measurement profiles share one access
model (`webapp/access.py`). Every item starts private, with exactly one owner:
the account that created it (or the browser, for a guest's garment or outfit).
Open **Privacy & sharing** from a library card's menu, the editor's share
button, a fabric's menu, the Measurements **Share** button, or an item's
shared page.

**General access** decides who can view the item:

| Access | Who can view and save a copy | Listed in Explore |
| --- | --- | --- |
| Private | The owner and people added by email | No |
| Friends | The owner's accepted friends, and people added by email | No |
| Anyone with the link | Anyone holding the link | No |
| Public | Everyone | Yes |

**People added by email** get a role:

| Role | View and save a copy | Edit, rename, share, delete | Transfer ownership |
| --- | --- | --- | --- |
| Viewer | Yes | No | No |
| Admin | Yes | Yes (including other admins' access) | No |
| Owner (one) | Yes | Yes | Yes |

- **Save a copy** (a fork) creates a new, private item owned by you: a garment
  or outfit in your wardrobe, a fabric in My fabrics, or a measurement
  profile. Copies people already saved remain theirs after access ends.
- **Admins** open the original from its shared page. The studio's Save, the
  fabric editor and the measurement editor then write to the owner's item,
  and the change is visible to everyone with access.
- **Transfer ownership** is owner-only, to someone already added who has signed
  in. The item keeps its ID and link, moves to the new owner's library (a name
  they already use gains a number), and the previous owner stays on as an
  admin. A guest's item cannot be transferred or have admins.
- **Delete** is for the owner and admins. It removes the item, its access,
  bookmarks and finished photos. Outfits embed their garments, so deleting a
  garment leaves outfits intact; garments cut from a fabric keep their copy.
- **Make private** turns off link, friend and public access and removes every
  viewer; admins keep access. Anyone added can **Remove from my list**.
- A fabric's purchase-source private notes are the owner's alone: others see
  them blank, an admin's save keeps them, and a transfer drops them.

Shared with me and Explore on the wardrobe home list all four kinds. Shared
fabrics also appear under Account → Fabrics → Shared with me and in the
studio's fabric chooser; shared profiles in Measurements and the studio's
measurement picker. Existing shared links remain unlisted. Friends and public
access require a signed-in owner.

## Friends

Use **Friends** in the wardrobe header (or Account → Friends). Send a request
using the person's sign-in email. They must accept before Friends-only designs
become accessible. Requests and invitations appear inside SewEasy; no email is
sent. Requests can be cancelled or declined, and either person can remove a
friend. Removing a friend ends Friends-only access in both directions, while
explicit invitations remain in effect. There is no public email directory.

## Favorites

Tap the heart on a saved or shared garment/outfit to bookmark it in
**Favorites**. Favorites belong to your account and work across devices. They
refer to the current design, rather than creating copies. If access is revoked,
the design disappears from Favorites until access is granted again. Favoriting
your own public design is the same bookmark as favoriting it in your library.

## Photos after sewing

Choose **Made it — add photos** from a saved garment or outfit's menu after
physically making it. Add up to eight JPEG, PNG or WebP photos, each at most
8 MB and 24 megapixels, with optional captions. Photos are attached to the
stable garment/outfit ID, separate from the simulated mannequin thumbnail.
They survive edits and renames. Saving a copy does not copy the original's
finished-piece photos.

Only the owner can upload or remove photos. Anyone who can open the design
can see its finished photos on the shared page. Every image request rechecks
the current access rules. Images are resized to at most 1600 × 1600, converted
to WebP, and stripped of embedded metadata (including GPS location).

Photo pixels and metadata are stored in the database's `finished_photos` table.
Favorites and friendships use `wardrobe_favorites` and `friendships`. Access for
all four kinds uses `wardrobe_shares` (one record per shared item; no record
means private) and `wardrobe_invitations` (members, with a `role` column).
Startup adds new tables and columns without changing existing access: earlier
invitations become viewers, and earlier body-profile shares
(`body_profile_shares`) become viewer members of private records. The older
pre-wardrobe saved designs keep their own read-only sharing (`webapp/sharing.py`).

## Library storage and migration


Account libraries live in `wardrobe_libraries.content`; guest libraries live in
NiceGUI server-side user storage. JSON format 2 contains `garments`, `outfits`
and optional `thumbnails`. Save replaces one record under a transaction; it does
not append revisions. `updated_at` protects against overwriting changes from
another open editor. ID and name are distinct: ownership always comes from the
verified account or server-side guest identity, never from the display name.

Old garment and outfit revisions are preserved as independent named items.
The newest keeps its name; collisions receive copy suffixes. Original revision
IDs remain attached to thumbnails and share links. Outfit `revision_id` remains
an alias for its stable ID for compatibility; it no longer changes on save.
There are no new version numbers, parent revision chains or history lists.
The migration is idempotent and persisted on the first read/write.

The `wardrobe_shares.revision_id` SQL column also retains its legacy name but
identifies a stable item. Share snapshots and thumbnails update with the item,
under the same account transaction. SQLite uses BEGIN IMMEDIATE; Postgres locks
the owner's row. Guest writes are serialized within the app process.


Validation: `python -m unittest test_access test_social_wardrobe test_named_items test_wardrobe_sharing test_wardrobe test_home_page test_thumbnails test_mcp_server`.
