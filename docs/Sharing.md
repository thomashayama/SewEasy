# Garment and outfit ownership

Saved items are private by default. The library card menu provides **Share**
and **Version history**; these controls are also available in the studio's
saved garment and outfit menus. The library shows the latest version of each
garment. Older versions remain accessible in its history.

## Sharing

Sharing always refers to one saved version, including its fabric, colors and
panel settings. An outfit includes the exact garment versions saved in it.
New saves do not update an existing share or inherit its access settings.

- **Anyone with the link** permits anyone holding that link to view and fork
  the version. The owner can turn it off.
- **Invite people** grants the same view/fork access to a verified email address.
  Invitations appear under **Shared with me** after Google sign-in. Addresses
  can be invited before registration. This implementation does not send email.
- Link access and invitations are independent. To revoke all access, turn off
  the link and remove the invitations. Access is checked again when forking,
  including from a page opened before revocation.

The share page is read-only. **Fork to my library** creates an independently
owned version 1 and opens it in the studio. For an outfit, its component garment
versions are copied into the recipient's library as well. Forks record the source
version, creator display name and share identifier. Further edits retain this
attribution. Revocation does not remove copies already forked.

Body measurements and body-profile assets are excluded. Previews use cached
renders on the default mannequin, with a flat illustration fallback.

## Version history

Garments have stable `lineage_id` values and immutable revision `id` values.
Outfits retain a stable `id` and get a new `revision_id` on every save. Both
record `parent_revision_id` and a version number. Renaming an opened item keeps
its history; starting a new garment or outfit creates a distinct identity even
if the name matches. Opening an older version creates a draft; saving it appends
a revision based on that version, without overwriting previous history.

Legacy garment versions are grouped using their former name-based identity.
Existing outfits become version 1; their previously overwritten states cannot
be recovered. This migration is deterministic and preserves design snapshots.
It is persisted on the next library write.

## Persistence and authentication

Account ownership comes from the verified session email. Guest ownership comes
from a random identifier in NiceGUI's server-side user storage; guest libraries
and account libraries remain separate. Clearing the guest session loses access
to its ownership controls. Display names never confer editing permission.

`wardrobe_shares` stores immutable snapshots and link settings;
`wardrobe_invitations` stores per-version email grants. These are new additive
SQL tables, separate from the older design/body-profile sharing system.
Library writes allocate versions inside a transaction (SQLite `BEGIN IMMEDIATE`,
Postgres parent-row lock). Guest writes are serialized within the app process.

Private invitation access requires configured Google OAuth. Share URLs point
to the installation where they are created; a local development server needs
to be hosted at a reachable address before people on other devices can use it.

Validation: `python -m unittest test_wardrobe_sharing test_wardrobe test_home_page test_thumbnails`.
