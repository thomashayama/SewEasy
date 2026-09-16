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

## Sharing and copies

Items remain private until their owner enables link sharing or adds invitations.
An existing share follows the owner's saved changes. Saving a copy never inherits
access settings. The Save arrow offers Save a copy, Rename and Share for owned
items; standards and other people's items use Save a copy as their main action.

- Anyone with the link can view and copy the item while link sharing is enabled.
- Invitations grant access to verified email addresses and appear in Shared with
  me after sign-in. No invitation email is sent.
- Link and invitation access are independent and can be revoked individually.
- Access is checked again when copying. Copies already saved remain independent.
- Copying an outfit preserves its embedded garments without filling the user's
  standalone garment library. Any piece can be saved separately later.

Copies retain source attribution. Measurements, private library metadata and
body-profile assets do not cross the sharing boundary. Preview images use the
default mannequin.

## Storage and migration

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

Validation: `python -m unittest test_named_items test_wardrobe_sharing test_wardrobe test_home_page test_thumbnails`.
