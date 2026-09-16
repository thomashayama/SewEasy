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
saved outfit. Results must reference an owned garment revision, outfit revision,
or standard preset before they can be saved.

Images are attached directly to IDs in the library's `thumbnails` map:
`garment:<id>` or `outfit:<revision_id>`. A garment's `id` already identifies
an immutable version; an outfit's `revision_id` does the same. Saving a new
version gives it a separate image, and a late render for an older version cannot
replace the new version's thumbnail. Forks copy the shared image to their new ID.
Legacy content-keyed images migrate once to these attachments on library read,
without rendering again. No body files or designs are hashed for new thumbnails.

The browser loads the simulation modules only for missing thumbnails;
cached library cards do not download the cloth solver or initialize WebGPU.
Unsaved edits use the illustrative flat instead of an outdated saved image.
The flat also remains available while an image is pending or
when the browser cannot use WebGPU. Already cached or bundled images work
without WebGPU and do not start a graphics device.

## Standard images

The six standard garment renders live in `assets/garment_thumbnails/`, using
fixed preset names such as `DressShirt.webp` and `Pants.webp`. They contain only
built-in presets, never personal designs or measurements. To refresh a preset
after a design change, temporarily move its bundled image aside in a local
checkout, remove its `garment:standard:<kind>` attachment from a dedicated test
guest library if present, then open Home and let the missing render finish.
Export that test browser's cache (all six renders must be present):

```powershell
python benchmarks/export_garment_thumbnails.py .nicegui/storage-user-<id>.json
```

Commit the replacement images under the same filenames. Changes to the renderer
or mannequin do not invalidate users' saved images.

Validation: `python -m unittest test_thumbnails test_home_page test_wardrobe test_browser_preview test_fabric_selection -q`.
Browser checks cover real captures, existing outfit backfill, save-triggered
renders, reload persistence, and cached images without repeated GPU work.
