# Browser 3D preview

Run `python gui.py` and open <http://127.0.0.1:8080/>. Opening **3D view**
automatically prepares the current pattern and starts browser WebGPU draping.
Design and stiffness edits replace the scene automatically. Returning to the
sewing pattern pauses the simulation; reopening 3D resumes the existing drape.
Fabric and per-panel colors, mannequin tone, visibility, orbit, pause and reset
are handled in the browser without another simulation request.

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

Current limitations: this remains an approximate cloth preview using the
standard mannequin, whose shape is not reconstructed from user measurements.
The garment uses the actual current measurements and design. The tube top's
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
