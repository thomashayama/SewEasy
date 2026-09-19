# Base garment uploads

A base garment is a reusable construction template. Saved garments embed a copy
of its definition and appearance; outfits embed copies of their garments.
Names distinguish variants. Saving a garment does not modify its base.

Use `create_base_garment` to derive a template from one of the IDs returned by
`list_base_garments`. Read `get_base_garment` for parameter types and suggested
ranges. Supply overrides as dotted paths, such as `{"sleeve.length": 0.35}`.

Use `upload_base_garment` with up to eight files:

```json
{
  "name": "My uploaded vest",
  "files": [
    {"name": "vest_specification.json", "content": "<entire JSON file text>"},
    {"name": "parameters.json", "content": "{\"pattern_fit.width\":1.0}"}
  ]
}
```

Files are UTF-8 JSON or YAML; combined content is limited to 2 MB. File names
are basenames, not paths. The original files are saved with the base and can be
retrieved with `get_base_garment(include_files=true)`. Python source, ZIP archives,
external URLs, textures, and executable uploads are not supported.

For a parameter-only upload, also supply `template_id`. Parameter files may use
dotted paths, a `parameters` object containing those paths, or a SewEasy
`design` YAML tree of self-describing values. Composition comes from the base;
parameter overrides cannot turn a shirt into trousers.

For new geometry, upload one SewEasy/GarmentCode pattern specification:

```json
{
  "pattern": {
    "panels": {
      "front": {
        "vertices": [[0,0],[40,0],[40,50],[0,50]],
        "edges": [
          {"endpoints":[0,1]}, {"endpoints":[1,2]},
          {"endpoints":[2,3]}, {"endpoints":[3,0]}
        ],
        "translation": [-20,80,20],
        "rotation": [0,0,0]
      }
    },
    "stitches": []
  },
  "properties": {"units_in_meter":100,"curvature_coords":"relative"}
}
```

This example is one unsewn panel, not a complete wearable garment. Real garments
need all panels, their initial 3D placements (centimeters), rotations (degrees),
and stitches. Each stitch joins two edges:
`[{"panel":"front","edge":1},{"panel":"back","edge":3}]`.
Edges must form closed, ordered loops. Curvature uses the existing relative
quadratic/cubic/circle representation. Maximum: 64 panels, 512 vertices/edges per
panel, 8192 total vertices and 4096 stitches. The upload is drafted before saving.

Uploaded geometry retains its authored dimensions and placement. It is **not
automatically graded to body measurements**. `pattern_fit.width` and
`pattern_fit.height` provide explicit scaling. Standard parametric templates
continue to draft from body measurements normally.

Appearance is independent of construction: `fabric_color` is a hex color;
`panel_colors`, `panel_stiffness`, `panel_materials` and `panel_fabrics` map panel
names to overrides. `panel_materials` names a drape preset or a saved fabric, and
`materials` carries that fabric's own detached copy, keyed by its id, so a library
edit never restyles a saved garment. A panel fabric accepts `kind`, `fg`, `bg`, and `scale`.
Supported prints: plain, stripe, pinstripe, polka_dot, gingham, windowpane.
Use complete fabric specs with six-digit hex colors and scale in centimeters.

After creating a garment, call `render_item`. A 2D render produces SVG and PNG.
A 3D render also returns a viewer URL; open it in a WebGPU-enabled browser to
settle the cloth and attach a WebP thumbnail to the saved item. Call `get_render`
for the completed image. Render URLs expire after 24 hours and grant access only
to that render. Do not publish them. The backend performs CPU drafting and
meshing only; the browser performs all 3D simulation and rendering.
