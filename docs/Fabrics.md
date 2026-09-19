# Fabric prototype

Open **Account → Fabrics**. Import a U3M 1.1 material, edit its properties,
save a named copy, or export a U3MA package. The import dialog includes a
published cupro measurement sample; its minimal material wrapper is ours.

**Common fabrics** offers 12 read-only templates, searchable by name, fiber or
weave. Open a name to inspect properties and sources, choose **Test swatch**,
or **Save a copy** to edit. Three templates include CC BY published measurements;
nine are entirely estimated. Every supplied property identifies its provenance,
and missing properties remain blank. See [sources and caveats](FabricSources.md).
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
It carries the properties, provenance and solver tuning; curves, textures and
original bytes stay in the library.

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
| Friction | Per garment | The same rest-area mean, used as the positional body-friction factor. It is not a Coulomb coefficient. |
| Thickness | Per garment | Raises the solver's 4 mm numerical contact margin when a fabric is thicker. It never lowers the margin, and the measurement is never overwritten by it. |
| Warp/weft stretch, shear | Stored only | Garment panels use scalar distance constraints and a strain limiter, not N/m membrane stiffness. The orthotropic model exists only in the swatch. |
| Textures | Stored only | The garment renderer draws procedural prints; imported U3M maps are preserved but not decoded. |

Grain direction is not a garment setting: with an isotropic solver it would
change nothing, and print rotation remains a separate appearance choice.
Assigning a fabric does not import its colours or prints.

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
  (`seweasy-u3m/2`). Opening a record written by an older reader re-reads the
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
- Keeps companion files and unknown vendor extensions unchanged. Download
  original returns the exact uploaded bytes, including its original values.
- Texture files are preserved, but the current renderer does not interpret
  their PBR maps. No CLO/Browzwear application round-trip is claimed yet.
- Referenced textures, normal maps and preview images must be real PNG, JPEG,
  TIFF or WebP files of at most 16384 px per side and 80 megapixels. Only
  headers are read: pixels are never decoded, rescaled or re-encoded, so a
  truncated file is a renderer problem, not an import error.
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
material. Browser checks also
cover sample import, save, export, reimport, blank/invalid values, and the live
WebGPU comparison.
