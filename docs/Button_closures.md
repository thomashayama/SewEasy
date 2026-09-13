# Dress-shirt button closures

The front opening is an overlap held at individual buttons. It is no longer a
continuously sewn edge with decorative discs.

Each front extends beyond center front by the configured placket extension.
Button seats sit inside the fabric on the center-front line, so the extra width
forms an overlap instead of increasing the shirt's circumference. The neckline
continues across the extension, with matching tabs on the neck band. Cuff tabs
replace one of each cuff's side seams; the cuff-to-sleeve construction seams stay.

The pattern's `fasteners` list identifies a button seat and buttonhole seat by
panel and 2D material coordinates. Component assembly preserves these records;
outfits namespace both ends so different garments cannot accidentally connect.
Fractional pivot coordinates remain exact during assembly, avoiding drift of
the draft and hardware on repeated exports.

CPU triangulation maps each seat to barycentric weights on its own triangle.
The browser solver connects these two material points with a short button-shank
attachment: tangential alignment and 3 mm of normal clearance between layers.
Corrections are inverse-mass weighted and equal/opposite, transferring load to
both pieces of cloth. The constraint has finite compliance and bounded per-step
motion. Graph coloring prevents overlapping writes to shared triangle vertices.
During initial assembly, attachment rest offsets contract on the same schedule
as the permanent seams, allowing the sleeve tubes to form around the arms
before the cuff buttons finish closing.
Permanent sewing junctions and button closures are solved together so a closure
does not pull apart a construction seam elsewhere in the garment. These welds
come only from authored stitches; they never connect the front opening.

Disabling a button removes its attachment force. No body anchor or cross-front
weld keeps that opening closed. Cloth between the discrete seats is free to
move, separate and fold. The studio's **Unbutton shirt** control releases all
buttons; the engine also supports each closure independently via `setButton`.
Rebuttoning closes attachments in the current drape; it cannot put a garment
that has slipped off the shoulders back onto the body. **Reset** redrapes it.

Rendering uses the same seats for the button cap and shank. Buttonholes are
material-space slots cut out by the cloth fragment shader, with a stitched rim;
they stay on the receiving panel when it opens. The 2D pattern marks both seats.

This is a discrete fastener model, not a full rigid-button/thread solver. It
does not simulate thread breakage, automatic unbuttoning, button inertia, detailed
contact around the hole perimeter, or a tailored sleeve placket. The hole is a
rendered cutout; its mechanical behavior is represented by the attachment.
The browser solver consumes these fasteners; the legacy Warp/Maya adapters do
not yet simulate them.

Validation commands:

```powershell
tmp_webgpu_cpu/Scripts/python.exe -m unittest test_button_closures test_dress_shirt_collar test_wardrobe test_browser_hardware test_browser_preview -q
node --test benchmarks/test_button_closures.mjs benchmarks/test_camera.mjs benchmarks/test_simulation_clock.mjs benchmarks/test_browser_drape.mjs benchmarks/test_collar_placement.mjs benchmarks/test_outfit_placement.mjs
```

The live harness is `benchmarks/webgpu/collar.html`. **Fastener test** settles
the shirt, turns/reverses it, releases and recloses the top pair, then releases
all buttons and turns again. Reports include distances between the seats at
every phase, GPU kernel checks and finite-position checks. **Save geometry**
archives the report and final positions. GPU fixtures separately verify that a
button transfers load to both panels, preserves center of mass, retains the
layer clearance, and exerts no force when released.

The [2026-09-13 browser results](../benchmarks/webgpu/results/2026-09-13-button-closures.json)
cover 900 frames of a shirt-and-shorts outfit through turns and reversals, and
1,170 frames of release/reclosure on a larger custom body. Both passed all 18
GPU checks and retained finite positions with zero measured construction-seam
separation. The outfit's largest button-seat distance was 3.20 mm. On the custom
body, releasing the top front and neck buttons opened their seats to 43.76 and
66.43 mm while the other front buttons stayed at 3 mm; reclosing restored the
released seats to 3.00 and 2.98 mm. Each run averaged about 20.5 ms per harness
frame, including rendering/readback, at 30 simulation Hz. The live studio was
also checked by unbuttoning, rebuttoning and resetting the default shirt.

All 20 Python regression tests and 18 Node tests in the commands above passed.
