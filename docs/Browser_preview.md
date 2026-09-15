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
Selecting **Default body** restores the original template unchanged.

Drag to turn the mannequin; **Shift-drag** or right/middle-drag moves the
view. On touch screens, two fingers pan and pinch to zoom. Scroll zooms; the
arrow keys rotate and **Shift+arrows** pan when the canvas has focus.
Panning changes framing while the mannequin's rotation stays centered on its
body. **Recenter** restores the initial framing. The visible floor has been removed.

Click the mannequin caption below the preview for a table comparing requested
and measured height, bust, underbust, waist, hips, wrist and thigh (wrist/thigh
values average the two sides). Custom bodies
are checked against a 1 cm maximum section error before being used. The fitter
also adjusts torso/leg landmarks, shoulder/neck width, arm length and arm pose.
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
