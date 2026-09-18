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

## Sharing your wardrobe

Saved garments and outfits start private. Open **Privacy & sharing** from a
library card's menu or the editor's share button to choose who can open one:

| Access | Who can view and save a copy | Listed in Explore |
| --- | --- | --- |
| Private | You and individually invited people | No |
| Friends | Your accepted friends and individually invited people | No |
| Anyone with the link | Anyone holding the link | No |
| Public | Everyone | Yes |

Existing shared links remain unlisted. Public discovery and friends sharing
require a signed-in account. **Stop sharing** returns an item to private and
removes all invitations. Individual invitations otherwise remain in effect
when changing visibility. Saving changes updates the shared design; saving a
copy creates a separately owned, private item. Copies people already saved
remain theirs after access to the original ends.

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
Favorites and friendships use `wardrobe_favorites` and `friendships`; sharing
continues to use `wardrobe_shares` and `wardrobe_invitations`. Startup adds the
new tables and nullable visibility column without changing existing access.

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


Validation: `python -m unittest test_social_wardrobe test_named_items test_wardrobe_sharing test_wardrobe test_home_page test_thumbnails test_mcp_server`.
