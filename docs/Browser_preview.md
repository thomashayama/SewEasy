# Browser 3D preview

Run `python gui.py` and open <http://127.0.0.1:8080/>. Opening **3D view**
automatically prepares the current pattern and starts browser WebGPU draping.
Design and stiffness edits replace the scene automatically. Returning to the
sewing pattern pauses the simulation; reopening 3D resumes the existing drape.
Fabric and per-panel colors, mannequin tone, visibility, orbit, pan, pause and reset
are handled in the browser without another simulation request.

Use **Customize measurements** in the studio, upload a measurement file, or
select a saved profile. Both the garment and mannequin use that profile. Body
fitting runs on CPU; the fitted surface supplies the visible mesh and the
browser's collision field. The account measurement editor uses the same fitter.
Selecting **Default body** restores the original template unchanged.

Drag to rotate; **Shift-drag**, right/middle-drag or the **Pan** toggle moves the
view. On touch screens, two fingers pan and pinch to zoom. Scroll zooms; the
arrow keys pan when the canvas has focus. **Recenter** restores the initial
framing. The visible floor has been removed.

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
Fabric prints and button hardware are currently shown in 2D only. Live drapes
are not yet attached as GLB exports when saving an outfit; stored legacy drapes
remain available for existing saved outfits. The physics and asset licensing
limits in `benchmarks/webgpu/README.md` still apply.

Validation: `python -m unittest test_browser_preview -v` covers lazy preparation,
scene reuse, edits during a mesh job, empty designs and retry after failure.
`node --test benchmarks/test_browser_drape.mjs` checks unsupported WebGPU,
obsolete browser responses, and disposal during loading using a fake GPU.
Browser integration checks cover automatic startup, live design replacement,
view switching, material changes and empty designs. The standalone benchmark
continues to use the same scene exporter and GPU engine.

`python -m unittest test_body_fit -v` checks different proportions, dimensions,
finite closed meshes, cache isolation, invalid inputs and the exact fitted
surface reaching the renderer/collision scene. `node --test benchmarks/test_camera.mjs`
checks screen-space pan at different camera angles, mouse/touch controls and
pointer cleanup.
