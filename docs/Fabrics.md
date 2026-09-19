# Fabric prototype

Open **Account → Fabrics**. Import a U3M 1.1 material, edit its properties,
save a named copy, or export a U3MA package. The import dialog includes a
published cupro measurement sample; its minimal material wrapper is ours.

The fabric menu's **Compare weight in 3D** opens two independent WebGPU
simulations of the same tee on the default mannequin: the current 300 g/m²
reference and the saved fabric's weight. The CPU only triangulates the
reference pattern once per process. Simulation and rendering run in the browser.
Vertex masses change in proportion to areal density; gravity, geometry,
bending, stretch, friction, and all other settings remain identical.
This tests data integration and numerical stability, not whether a real cupro
garment will drape accurately. Library fabrics are not assigned to saved
garment pieces yet.

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

`fabrics.snapshot()` produces a detached assignment value with a
`source_fabric_id`. Consumers must embed that snapshot instead of re-reading
the library during simulation; later library edits must not alter a garment.
The garment assignment UI is a separate follow-up.

## Quantities and provenance

Each physical property has `value`, `unit`, `origin`, and `source`. Missing
values are null, never zero. Origins distinguish unknown, measured, supplier
reported, estimated, and user-entered values. A measured origin describes the
source data; it is not independent certification of the measurement.

| Property | Unit / interpretation | Prototype support |
| --- | --- | --- |
| Weight | g/m² | Import, edit, export, weight-only 3D experiment |
| Thickness | mm | Import, edit, export; not a collision margin |
| Friction | dimensionless coefficient | Retain reported Browzwear value; edit/export as SewEasy extension |
| Warp/weft stretch | N/m, membrane stiffness | Explicit user values only; no vendor coefficient conversion |
| Warp/weft bending | N·m, bending rigidity | Explicit user values only; not the artistic multiplier |
| Shear | N/m, membrane shear stiffness | Explicit user values only |
| Damping | 1/s, velocity decay rate | Explicit user values only |

Warp means along the fabric's warp/grain and weft across it. Raw FAB `L`, `W`,
and `B` are length, width, and bias specimen measurements; the original labels
are retained without guessing a garment's grain orientation. Original FAB
curves alternate displacement in cm and force in gram-force. They remain in
the original companion JSON, including loading/unloading branches and specimen
metadata. No calibrated SI curves are populated in `curves` yet.

The normalized bending/stretch fields deliberately remain unknown when a
vendor supplies only solver-specific coefficients. U3M does not make those
coefficients interchangeable with our XPBD compliance values. Calibrating
them requires controlled swatch tests and an explicit mapping.

## Interchange boundaries

- Supports schema 1.1 only. Validates the material and referenced FAB JSON
  against the bundled upstream schemas, without remote schema resolution.
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

Reference schemas and sample attribution: [webapp/u3m_spec](../webapp/u3m_spec).

## Validation

Run `python -m unittest test_fabrics -v` in the GUI environment. Tests cover
the published sample, schema and U3MA headers, preservation, edits and copies,
account isolation, stale writes, deferred BLOBs, private preview access, and
actual tee mass = pattern area × imported areal density. Browser checks also
cover sample import, save, export, reimport, blank/invalid values, and the live
WebGPU comparison.
