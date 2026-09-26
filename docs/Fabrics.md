# Fabric prototype

Open **Account → Fabrics**. Import a U3M 1.1 material, edit its properties,
save a named copy, or export a U3MA package. The import dialog includes a
published cupro measurement sample; its minimal material wrapper is ours.

**Common fabrics** offers 12 read-only templates, searchable by name, fiber or
weave. Open a name to inspect properties and sources, choose **Test swatch**,
or **Save a copy** to edit. Three templates include CC BY published measurements;
nine are entirely estimated. Every supplied property identifies its provenance,
and missing properties remain blank. See [sources and caveats](FabricSources.md).
Each template also has a representative display colour, the undyed or most
familiar shade of that cloth, so the twelve can be told apart at a glance and a
piece cut from one starts that colour. It is presentation, not a measurement.
**My fabrics** contains only the user's saved records and imports.

The fabric menu's **Test fabric swatch** compares warp and weft strips with the
same weight. Browser WebGPU applies directional stretch and bending, shear,
and damping. Choose gravity bending, longitudinal stretch, or transverse shear;
a same-grain control verifies identical inputs produce identical results.
Reported measurements, estimated bending, and missing-value assumptions are
shown separately. These experiments are not yet physically calibrated. See
[the swatch model and validation](FabricSwatch.md) for its assumptions and
numerical checks. Assigning a library fabric to garment pieces is described
below; a garment drape applies fewer properties than a swatch does.

## Browsing, favorites and the studio picker

The library has three views. **Common fabrics** is the read-only collection,
**My fabrics** the account's imports and copies, and **Favorites** whatever has
been hearted from either. Each row opens with a preview tile showing the same
3 cm of cloth: the fabric's own map at scale, else its display colour, else an
empty hatch, so weaves compare by eye. A fabric imported before maps were read
gains its tile when it is next saved, because lists never re-read a stored
package. The search box matches name, notes, fiber and weave;
**Weight** filters by the usual apparel classes: light under 135 g/m², medium to
270 g/m², heavy above (4 and 8 oz/yd²). A fabric with no weight matches no class.

A heart stores only the fabric's stable id, in the same account-scoped table as
garment and outfit favorites under its own kind, so it follows the account across
devices and never appears in, or is counted by, the wardrobe's Favorites tab.
Hearting a standard fabric makes no copy. A heart whose fabric no longer resolves
is skipped in listings and can still be removed. Guests see Common fabrics only.

In the sewing pattern, **Browse fabrics…** under Fabric type opens this same list
as a picker, starting on Favorites when there are any. **Use fabric** applies the
choice to the pieces that were selected and returns to the pattern with the
selection and every unsaved design change untouched; Cancel or Escape changes
nothing. The quick list under Fabric type shows each fabric once: Favorites
first, then the rest of My fabrics and Common fabrics.

## Editing a fabric

Each numeric field shows its unit, its provenance, and what a garment drape
does with it: **drapes each piece**, **drapes the whole garment**, or **swatch
tests only**. Hover the line for the measurement source and the mapping.
Values must be finite and non-negative; there are no arbitrary safe ranges.

An override never discards a measurement. When a field differs from the
original file, including a field that was cleared, the editor shows
**Imported: _value_** with **Restore**. Restoring brings the file's value back
with its measured or reported provenance, rather than relabelling it as yours.

**Display color** is the library's own swatch colour. It appears beside the
fabric's name, tints pieces cut from the fabric, which stay recolourable, and
travels through copies and U3MA export. Vendor front and back maps are untouched.

The footer reads **All changes saved** or **Unsaved changes**; Save is enabled
only when something changed, and the other button becomes **Discard changes**.
A stale editor is still refused by the edit token.

A garment keeps the copy of a fabric it was cut from. When that fabric later
changes in the library, selecting the piece shows **Apply current fabric**;
nothing updates until it is pressed.

## Where to buy

A saved fabric can list up to 12 places to buy the physical cloth
(`webapp/fabric_sources.py`). Entry is manual: only the product page address is
required, and anything the owner does not know stays blank. Nothing fetches a
retailer's page, so there is no metadata extraction to confirm and no blocked
page to handle. Common fabrics are generic cloth and list no products; a copy
of one can.

Every source states how it relates to the properties above it, and the label
always sits beside the link:

| Relation | Meaning |
| --- | --- |
| **Measured product** | The measurements were taken from this product. |
| **Unverified link** (default) | Not checked against the measurements. |
| **Similar fabric** | A suggestion of similar cloth, not the measured one. |

The last two carry "It may drape differently." A matching name or fibre is never
treated as a match: the listing's own composition, weave, weight and width are
shown as **Listing says**, separate from the fabric's measured values, and are
never copied into them.

- **Links** must be `https://` with a real host and no embedded credentials.
  Campaign parameters and affiliate-network click ids (`utm_*`, `gclid`,
  `fbclid`, `irclickid`, `awc`, …) are removed everywhere. Amazon, eBay, Etsy and
  Walmart also lose their own affiliate parameters (`tag`, `campid`, `ref`,
  `wmlspartner`, …), but only on their own sites, because elsewhere `tag` or
  `ref` may select the product; parameters that choose a variant (`th`, `var`,
  `variation0`) are kept. A stored link identifies the product rather than
  whoever shared it. Links open in a new tab with `rel="noopener noreferrer"`.
- **The retailer is named from the address.** `fabric_sources.RETAILERS` lists
  about 75 shops by host: the marketplaces and craft chains (Amazon, eBay, Etsy,
  Michaels, Hobby Lobby, Walmart) and the common fabric shops of the United
  States, Canada, the United Kingdom, Europe, Australia and New Zealand.
  Subdomains belong to their parent, Amazon and eBay match only their real
  country sites, and a lookalike host such as `amazon.com.evil.example` keeps
  its own name. Any other shop is named by its host, or by whatever the owner
  types; the Retailer field completes the listed names and shows the detected
  one as soon as an address is pasted. JOANN and Fabric.com have closed and now
  forward to Michaels and Amazon, so they are not listed. An imported file
  cannot name its own retailer: the name always comes from where the link goes.
  To add a shop, add its name and host to the table; sources saved under the
  bare host pick the name up without being re-saved.
- **A price** needs a three-letter currency and always reads with its unit and
  variant: per yard, per metre, per precut piece, per pack, or a stated size
  such as "per 2-yard cut".
- **A price or stock status is dated.** It takes today's date when entered or
  changed unless the owner gives another, and future dates are refused. After
  30 days it is still shown, followed by **may have changed**; an undated quote
  from an imported file reads **Not dated · may have changed**.
- **Private notes** stay in the account. They are not written to U3MA or folder
  exports, and a file cannot import one.

Sources follow a named copy, which then edits its own list. They travel in
exports as `custom.seweasy.purchase_sources`; on import each source is
re-validated and an unreadable one is dropped without failing the material.
They are not part of a garment's fabric snapshot, so saved or shared garments
carry no shopping links.

## Storage

`fabrics` is an additive SQLAlchemy table, created by the existing `init_db`
path on SQLite and Postgres. Each record has a stable UUID, owner, name,
timestamps, an opaque optimistic-lock token, and JSON content. Saving updates
that record. Save a copy creates another UUID and a default `(copy)` name.
The lock token prevents lost edits; it is not user-visible version history.

Content separates `properties`, `appearance`, `source`, `curves`, and
`solver_tuning`. Original upload bytes are stored unchanged in a deferred BLOB,
alongside their filename; listing the library does not retrieve the BLOB.
Existing artistic presets remain read-only and have unknown physical values.
Their bending multipliers live only in `solver_tuning` and can be copied.
The separate common collection contains normalized physical properties and
`catalog` metadata, with stable `standard:catalog:*` IDs. It is loaded locally
without network requests or database writes. Copies store detached content;
catalog revisions do not rewrite them. Attribution, licenses and property
sources survive editing, copying and U3MA export/reimport.

`fabrics.snapshot()` produces a detached assignment value with a
`source_fabric_id`. Consumers embed that snapshot instead of re-reading the
library during simulation, so later library edits never alter a saved garment.
It carries the properties, provenance, solver tuning and the small render-ready
base-colour maps; curves, the full-size textures and original bytes stay in the
library.

## Assigning a fabric to a garment

Select pieces in the sewing pattern and choose a saved fabric under **Fabric
type**; **Common fabrics** and **My fabrics** appear beside the drape presets.
The assignment is stored in the garment's own appearance: `panel_materials`
names the fabric per piece, and `materials` holds its detached copy keyed by
fabric id. Unreferenced copies are dropped, so a garment carries only what it
uses. Each garment in an outfit keeps its own pool, and copies, shares and forks
carry both. Changing an assignment changes the appearance, so the saved
thumbnail is invalidated exactly as a design edit is.

What the garment solver does with each measured property:

| Property | Scope | Effect on the drape |
| --- | --- | --- |
| Weight | Per piece | Vertex mass is rest triangle area × g/m². Unassigned pieces keep 300 g/m². |
| Warp/weft bending | Per piece | Averaged into one isotropic bending multiplier, rigidity ÷ 1e-5 N·m, clamped to 0.5–30. Retuning **Bending stiffness** afterwards keeps the piece's fabric identity. |
| Damping | Per garment | Mean over the whole garment by rest area; a piece without a value counts at the solver default, so one cuff cannot set it. The solver damps velocity garment-wide. |
| Friction | Per garment | The same rest-area mean, used as the positional body-friction factor; it also scales the body grip (see [Mannequin motion](Mannequin_motion.md)), so slippery fabrics hold on less. It is not a Coulomb coefficient. |
| Thickness | Per garment | Raises the solver's 4 mm numerical contact margin when a fabric is thicker. It never lowers the margin, and the measurement is never overwritten by it. |
| Warp/weft stretch, shear | Stored only | Garment panels use scalar distance constraints and a strain limiter, not N/m membrane stiffness. The orthotropic model exists only in the swatch. |
| Base-colour map | Per piece | Drawn in the 2D pattern and the 3D drape, repeating at the size the file declares, with the file's multiply factor. The wrong side uses the back's map when the material has one, otherwise the front's. |
| Other maps | Stored only | Normal, roughness, displacement and the remaining PBR maps, mirrored repeats and repeat rotation are kept in the package and not rendered. |

Grain direction is not a garment setting: with an isotropic solver it would
change nothing, and print rotation remains a separate appearance choice. Maps
follow each piece's rest pattern, upright as the piece is drawn in 2D.

A piece cut from a fabric with a base-colour map shows that map, and assigning
the fabric clears the piece's earlier colour or print so it is visible. Giving
the piece a colour or print afterwards replaces the map without changing what
the piece is cut from; choose the fabric again to bring the map back. A fabric
without a map applies its display colour when it has one.

The garment carries its own copy of each map: at import the base colour is
reduced to at most 512 px and 200 KB as a WebP, keeping the declared physical
size, so shares, forks, thumbnails and agent renders need no access to the
owner's library. Maps above 36 megapixels, or with no declared size, are stored
but not drawn. A garment never fetches an image; only that embedded copy is
accepted.

## Quantities and provenance

Each physical property has `value`, `unit`, `origin`, and `source`. Missing
values are null, never zero. Origins distinguish unknown, measured, supplier
reported, estimated, and user-entered values. A measured origin describes the
source data; it is not independent certification of the measurement.

| Property | Unit / interpretation | Prototype support |
| --- | --- | --- |
| Weight | g/m² | Import, edit, export, area-derived swatch masses |
| Thickness | mm | Import, edit, export; not a collision margin |
| Friction | dimensionless coefficient | Retain reported Browzwear value; edit/export as SewEasy extension |
| Warp/weft stretch | N/m, membrane stiffness | Documented Browzwear reported values or user values; directional strain energy |
| Warp/weft bending | N·m, bending rigidity | Estimated from raw short-loop tests or user values; directional dihedral energy |
| Shear | N/m, small-angle shear stiffness | User values or explicitly assumed 100 N/m in swatches |
| Damping | 1/s, velocity decay rate | User values or explicitly assumed 14/s in swatches |

Warp means along the fabric's warp/grain and weft across it. Raw FAB `L`, `W`,
and `B` are length, width, and bias specimen measurements; the original labels
are retained without guessing a garment's grain orientation. Original FAB
curves alternate displacement in cm and force in gram-force. They remain in
the original companion JSON, including loading/unloading branches and specimen
metadata. `curves` also preserves each branch in metres and newtons (1 gf =
0.00980665 N); it does not silently discard negative forces or hysteresis.
The current solver uses linear scalar stiffness, not the full nonlinear curves.

Browzwear's [Physics Reference](https://help.browzwear.com/en/articles/13065506-physics-reference)
documents directional stretch in N/m. These reported surface stiffnesses are
converted into area-dependent XPBD compliance, not copied into solver knobs.
Vendor bend numbers are not treated as N·m. Where sufficient raw FAB U1/D1
measurements exist, a clamped-elastica model estimates effective rigidity;
`physics_normalization.bending_fits` retains the method, per-cycle fit errors,
and range. Vendor shear and linearity coefficients remain uninterpreted.

Source quality warnings are retained in `physics_normalization.raw_warnings`.
A `BendRigidityWarp`/`BendRigidityWeft` warning prevents automatic bending
estimation for that axis. The editor and swatch explain the warning; preview
fallbacks remain explicitly assumed. Raw tests and unrecognized flags survive.

Old imports are enriched from their original source when opened, copied or
exported. Normalization v2 retires our earlier bending estimates if the source
flagged their measurements. User values and intentional clears win, including
in older exports. Saving persists the normalization marker. Lists still avoid
loading blobs. See [external fixture validation and catalog candidates](FabricSources.md).

## Interchange boundaries

- Supports schema 1.1 only. Validates the material and referenced FAB JSON
  against the bundled upstream schemas, without remote schema resolution.
- U3M 1.0 is deliberately not supported. It has no `physics` section, states no
  unit for image width and height, carries one `dpi` number instead of x and y,
  and predates the U3MA archive, so neither measurements nor texture scale can
  be read from it. A 1.0 upload is refused by version, before schema errors,
  and asks for a 1.1 re-export. Vizoo's published `Example_1.0.u3m` is the
  fixture for that path.
- Every import records the reader that produced it in `source.importer`
  (`seweasy-u3m/3`). Opening a record written by an older reader re-reads the
  stored original and refreshes its textures and source; if the current reader
  rejects that file, the saved record is still returned unchanged.
- Accepts standalone `.u3m` when it has no missing companions, and complete
  `.u3ma`/`.zip` packages with exactly one material manifest. Uploads are capped
  at 20 MB, 128 entries and 64 MB expanded; individual JSON files at 4 MB.
- Reads files in memory. Rejects traversal, duplicate paths, links, encryption,
  non-finite numbers, damaged archives, and incomplete references. It never
  follows URLs to fetch missing textures or measurements.
- Exports the restricted U3MA ZIP structure, including UTF-8 flags, matching
  local/central headers, no extras/comments/data descriptors and zero attrs.
- Writes weight/thickness into native U3M fields and edited normalized values
  into `custom.seweasy`. Other software may ignore the SewEasy extension.
- **Export U3M folder (.zip)** writes the same files as an ordinary ZIP to
  unpack beside the `.u3m`; only the container differs from the U3MA.
- Every export carries `seweasy-export-notes.txt`: which values sit in standard
  U3M fields, which exist only in the extension and will be ignored elsewhere,
  which are empty, and that edits are marked `user` while the laboratory's
  companion measurements were not rewritten. Re-exporting replaces our own
  notes and never a vendor file of the same name. No account identifier, edit
  token, garment or body data is written, and no solver parameters are invented
  for another application.
- Keeps companion files and unknown vendor extensions unchanged. Download
  original returns the exact uploaded bytes, including its original values.
- Texture files are preserved. Of their PBR maps the renderer draws only the
  base colour. No CLO/Browzwear application round-trip is claimed yet.
- Referenced textures, normal maps and preview images must be real PNG, JPEG,
  TIFF or WebP files of at most 16384 px per side and 80 megapixels. Validation
  reads headers only and the stored files are never rescaled or re-encoded.
  The base-colour maps alone are also decoded, into the small separate copy a
  garment draws; one that fails to decode is simply not drawn.
- `textures` lists each reference with its role, format, pixel size, declared
  millimetres and dpi. Where 1.1 declares a physical size, it is checked
  against the pixels at that dpi (2% tolerance) and a mismatch is reported per
  texture and shown in the editor. The declared size is never rewritten.

Reference schemas and sample attribution: [webapp/u3m_spec](../webapp/u3m_spec).

## Validation

Run `python -m unittest test_fabrics -v` in the GUI environment. Tests cover
the published sample, schema and U3MA headers, preservation, edits and copies,
account isolation, stale writes, deferred BLOBs, private preview access, and
actual swatch mass = pattern area × imported areal density, including its
clamped portion. An appearance-only package with real PNG and JPEG textures
covers texture roles, byte-exact round trips, declared-scale mismatches,
unreadable, unsupported and oversized images, and the refused vendor 1.0
material. `python -m unittest test_fabric_sources` covers where-to-buy rules:
several suppliers, missing metadata, stale, undated and out-of-stock quotes, each
selling unit, refused and cleaned links, and private notes staying out of
exports, imports and garment snapshots. Browser checks also
cover sample import, save, export, reimport, blank/invalid values, the live
WebGPU comparison, and adding, editing and removing a place to buy at desktop
and 375 px widths.
