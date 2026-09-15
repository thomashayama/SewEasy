# Saved 3D thumbnails

Home and the studio's garment list display cached renders on the default
`mean_all.yaml` mannequin. User measurements, camera position, simulation motion,
and current selection never enter a thumbnail. Outfits render all their saved
garment versions together, including per-panel colors, prints and stiffness.

Missing thumbnails are backfilled from Home. Saving a garment or outfit also
queues a thumbnail in the studio without holding up the save. A page has one
background renderer, with one job in flight. CPU drafting/meshing is serialized
in a separate worker thread; simulation, lighting and rasterization use WebGPU
in the browser. Each image gets six seconds of simulated settling and consistent
camera framing around the garment on the default mannequin. No backend GPU or
Modal call is involved. Hidden tabs pause the browser work; navigation cancels
unfinished work and the next Home visit resumes missing thumbnails.

The renderer copies the GPU framebuffer before presentation to avoid blank
canvas captures. Output is a 384 × 448 WebP, validated and re-encoded by the
server. Private images live in the owner's existing wardrobe storage: SQL for
accounts and persistent NiceGUI storage for guests. They are separate from
garment snapshots, so an image cannot create a new garment version or change a
saved outfit. Results must still match an owned garment, outfit, or standard
preset before they can be saved; stale outfit results are rejected.

Cache keys include the ordered garment designs and appearance, default body,
and thumbnail renderer version. Names, version numbers and custom measurements
do not affect the key. Identical single-garment outfits reuse their garment's
image. The illustrative flat remains available while an image is pending or
when the browser cannot use WebGPU. Already cached or bundled images work
without WebGPU and do not start a graphics device.

## Standard images

The six standard garment renders live in `assets/garment_thumbnails/`. They
contain only built-in presets, never personal designs or measurements. To refresh
them after a design change, open Home and let the browser finish its missing
renders, then export that local browser cache:

```powershell
python benchmarks/export_garment_thumbnails.py .nicegui/storage-user-<id>.json
```

Bump `THUMBNAIL_VERSION` in `webapp/thumbnail_cache.py` when changing renderer
framing, the body mesh or simulation behavior. This invalidates earlier renders;
regenerate the six bundled files with the new keys.

Validation: `python -m unittest test_thumbnails test_home_page test_wardrobe test_browser_preview test_fabric_selection -q`.
Browser checks cover real captures, existing outfit backfill, save-triggered
renders, reload persistence, and cached images without repeated GPU work.
