# Browser 3D preview

Run `python gui.py` and open <http://127.0.0.1:8080/>. The current pattern starts
preparing for 3D as soon as its 2D draft is available. Both views stay mounted;
the browser compiles the GPU pipelines and warms the cloth in the docked
preview while **Pattern** is open. Opening **3D** or expanding the preview
reuses that same canvas, GPU device and scene.
Design and stiffness edits prepare a new scene automatically. Mesh preparation
uses a separate CPU worker and a snapshot of the draft, so further 2D edits can
continue and an outdated result cannot replace the current design.

In 2D, the browser runs up to six simulated seconds of warm-up at 30 updates per
second, then idles. Interacting with the dock wakes the simulation briefly so
turning the mannequin still moves the cloth. This is an initial drape, not a convergence guarantee. The
visible 3D view continues live simulation; an explicit Pause is respected, and
switching away from the browser tab suspends GPU steps. The first load or a fresh
edit still needs preparation time, but switching to an already warmed scene
does not reload, recompile or restart it.
Fabric and per-panel colors, mannequin tone, visibility, orbit, pan, pause and reset
are handled in the browser without another simulation request.

Open **Measurements** in the header, then **Customize measurements**, upload a measurement file, or
select a saved profile. Both the garment and mannequin use that profile. Body
fitting runs on CPU; the fitted surface supplies the visible mesh and the
browser's collision field. The account measurement editor uses the same fitter.
**Default body**, **Default woman** and **Default man** are three mannequins
from the same averaged survey: the neutral population mean, and the women's and
men's means (166, 172 and 179 cm tall). Choosing one applies its measurements,
so the pattern redrafts for that body, and draws that mannequin's own mesh
unchanged. Custom measurements are fitted from whichever of the three needs
the least deformation, because smaller changes fit more accurately; the choice
follows the numbers, not a stated sex. A new measurement profile in the account
can start from any of the three. Saved thumbnails keep the neutral mannequin.

**Default measurements.** The ★ beside the picker (or **Make default** under
Account → Measurements) makes a profile, yours or one shared with you, the one
new designs open with. It is stored on the account, so it survives new browsers
and redeploys, which reset browser storage. A choice made in the picker still
wins for that browser's current draft, and a chosen profile is reread each time
a studio opens, so edits made on the account page apply.

**Inseam.** The editors ask for the inseam (crotch to floor) instead of the
hip-to-crotch depth, which is hard to take yourself. The body model keeps its
vertical chain (height = head + back length + waist-to-hip + hip-to-crotch +
inseam), so the entered inseam sets hip-to-crotch; trouser lengths and the
mannequin's legs then match it. Implausible combinations are flagged.

**Arm pose** is a 3D setting, not a measurement: the preview's ⋯ menu has a
slider (20–75° below horizontal, 0° being a T-pose), saved per account. It
re-poses the mannequin and places the sleeves for draping; the 2D pattern does
not change. The mannequin fitter reads the angle below horizontal, the same way
the garment programs place sleeves (before, it read it from vertical, which only
agreed at the default 45°).

**Skin tone and hair** belong to a measurement profile, edited with its
measurements on the account page (the mannequin there shows them as you
change them) and worn wherever the profile is chosen. The default mannequins
have their own: short hair, and a bun for the default woman.

*Skin tone* is two choices: depth (fair to deep) and undertone — cool (rosy),
neutral (peach), warm (golden) or olive (a muted green-gold).
`webapp/measurement_guide.py` builds each colour in CIELAB: lightness and
chroma follow depth, so deep skin keeps its warmth instead of turning grey,
and the hue angle sets the undertone. A stored colour reads back as the
nearest depth and undertone.

*Hair* starts from a style — bald, buzz cut, short, side part, short curls,
afro, bob, bob with bangs, shoulder length, long, long waves, bun or ponytail
— in one of twelve natural shades or any colour, and every part can then be
adjusted: length (buzz, short, ear, chin, shoulder, mid-back or waist,
measured on that body), volume, texture (straight, wavy, curly, coily), tied
(loose, bun, low bun, ponytail), fringe (none, full, side-swept), parting and
a receding hairline. `seweasy/meshgen/hair.py` builds it on the fitted body
with each 3D scene:

- a scalp cap: the head above a hairline running from the forehead over the
  ears to the nape, cut out along that curve and lifted along the surface
  normals, fuller on top and feathered at the hairline; a fringe lowers the
  hairline over the forehead, a parting dips it along a line, and coily hair
  lifts it into a rounded shape;
- for longer loose hair, a thick sheet falling from the widest part of the
  head that follows it in and out gently, clears the neck, stops at the
  shoulders beside the face and gathers down the back, with its ends curled
  in; below the nape it keeps room for the garment being draped;
- a bun, or a ponytail that falls under gravity and settles against the back.

The scene carries the mesh; the shader draws fine strands along each part's
flow, bent by waves and curls or broken into tufts for coils, fading to the
plain colour at a distance so it does not shimmer. Hair is drawn only: it
takes no part in cloth collision, is not in thumbnails or exports, and is left
out when a garment has a hood (a panel named `hood`). **Show hair** in the ⋯
menu hides it for the session, to see a neckline or back.

Drag to turn the mannequin; **Shift-drag** or right/middle-drag moves the
view. On touch screens, two fingers pan and pinch to zoom. Scroll zooms; the
arrow keys rotate and **Shift+arrows** pan when the canvas has focus.
Panning changes framing while the mannequin's rotation stays centered on its
body. **Recenter** restores the initial framing. The visible floor has been removed.

Click the mannequin caption below the preview for a table comparing requested
and measured height, bust, underbust, waist, hips, wrist and thigh (wrist/thigh
values average the two sides). Custom bodies
are checked against a 1 cm maximum section error before being used. The fitter
also adjusts torso/leg landmarks, shoulder/neck width, arm length and the arm pose.
Underbust height and other proportions not specified by these controls are
estimated from the template; front/back balance, bust/seat point spacing and
surface tape lengths are not independently reconstructed. This is an approximate
body shape, not a scan or a guarantee of fit. The original default template is
not recalibrated, so its measured sections can differ from its nominal preset.

The server drafts and triangulates the pattern on CPU. It never calls Modal,
Warp, CUDA or the legacy `GUIPattern.drape_3d()` from this view. Unsupported
browsers display an error and do not fall back to a server solver. Use a
WebGPU-capable browser with hardware acceleration on HTTPS or localhost.

A minimal local environment without GPU simulation packages:

```powershell
uv venv --python 3.11 tmp_webgpu_cpu
uv pip install --python tmp_webgpu_cpu/Scripts/python.exe -r benchmarks/requirements-webgpu-cpu.txt
uv pip install --python tmp_webgpu_cpu/Scripts/python.exe 'nicegui<3' 'sqlalchemy>=2' requests 'python-jose[cryptography]'
tmp_webgpu_cpu/Scripts/python.exe gui.py
```

The full project install also includes optional legacy and AI dependencies.
The dataset simulation scripts still require their separate Warp installation.

Current limitations: this remains an approximate cloth preview. The tube top's
height-only neckline support is exposed as **Hold neckline (fitting aid)**.
Fabric prints and attached button hardware appear in both 2D and 3D. Live drapes
are not yet attached as GLB exports when saving an outfit; stored legacy drapes
remain available for existing saved outfits. The physics and asset licensing
limits in `benchmarks/webgpu/README.md` still apply.

Validation: `python -m unittest test_browser_preview -v` covers preparation in 2D,
scene reuse, edits during a mesh job, draft snapshot isolation, empty designs and
retry after failure.
`node --test benchmarks/test_browser_drape.mjs` checks unsupported WebGPU,
obsolete browser responses, disposal during loading, bounded background warm-up,
pause/tab visibility and reuse on reveal using a fake GPU.
Browser integration checks cover automatic startup, live design replacement,
view switching, material changes and empty designs. The standalone benchmark
continues to use the same scene exporter and GPU engine.

`python -m unittest test_body_fit -v` checks different proportions, dimensions,
finite closed meshes, cache isolation, invalid inputs and the exact fitted
surface reaching the renderer/collision scene. `node --test benchmarks/test_camera.mjs`
checks screen-space pan at different camera angles, mouse/touch controls and
pointer cleanup.
