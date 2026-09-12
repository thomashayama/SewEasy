# SewEasy browser draping

An experimental cloth solver and renderer running entirely in browser WebGPU.
No Modal, CUDA, Newton, server GPU, or precomputed drape is required. The Python
pattern DSL and triangulation stay on the CPU; their output is ordinary static
mesh data. This is a standalone experiment, not yet the NiceGUI draping path.

## Run

From the repository root, create the **CPU-only** preparation environment:

```powershell
uv venv --python 3.11 tmp_webgpu_cpu
uv pip install --python tmp_webgpu_cpu/Scripts/python.exe -r benchmarks/requirements-webgpu-cpu.txt
$webgpuPython = 'tmp_webgpu_cpu/Scripts/python.exe'
& $webgpuPython benchmarks/prepare_cloth.py
& $webgpuPython benchmarks/prepare_cloth.py --garments t-shirt dress-shirt --resolution 1.0
& $webgpuPython benchmarks/prepare_webgpu.py
python benchmarks/serve_webgpu.py
```

Open <http://127.0.0.1:8767>. The static server uses only Python's standard
library. A current browser with WebGPU and hardware acceleration is required;
HTTPS or localhost provides the secure context. Unsupported browsers show an
error instead of falling back to a remote GPU.

For ordinary static hosting without the optional result archive:

```powershell
python -m http.server 8767 --bind 127.0.0.1 --directory output/webgpu
```

The existing `mean_all` mannequin remains a local evaluation asset. Generated
geometry lives in ignored `output/` folders; its license must be resolved before
publishing or bundling it in a commercial product.

## Controls and measurements

- **Run simulation** advances at up to 60 simulation updates per second; rendering
  uses the same GPU position buffer. **Pause**, **Reset**, camera views, orbit and
  zoom work locally. Paused scenes render only when the view changes.
- **Pattern width** changes rest distances at fixed topology. **Widen 2%** makes
  a small edit without recreating the solver. It is not a SewEasy pattern redraft.
- **Measure 300 frames** runs as fast as browser scheduling allows and includes
  frame encoding, GPU completion, rendering submission and timestamp readback.
  It simulates five seconds. Enable **Start from current drape** in the settings
  to measure an edit using the existing browser-generated state.
- **Save result & geometry** archives the result locally with `serve_webgpu.py`.
  That optional POST only writes JSON; it does not compute physics. On an ordinary
  static host the button falls back to downloading the JSON file.

All assets load before simulation starts. The page can keep simulating, editing
and rendering after the static server is stopped. Loading a different garment
still requires its mesh file, and the optional archive needs the server running.

## Implementation

`prepare_webgpu.py` preserves 2D rest coordinates, builds stretch edges and
approximate opposite-vertex bending constraints, retains separate seam vertices,
and colors constraints so each GPU dispatch has no shared-vertex write races.
It checks positive triangle areas/masses, seam correspondence and color validity.
The exported body BVH uses the existing triangle mesh and vertex normals.

The browser uses small-step XPBD distance projections, sewing constraints,
gravity, damping, discrete body collision and particle self-contact through a
GPU spatial hash. All positions, velocities, normals and collision data stay on
the browser GPU during normal playback. WGSL computes normals and the WebGPU
renderer reads the position buffer directly. No frame streams come from Python.

For assembly, original unsewn panels are raised 6 cm and sewn over 0.8 seconds
before gravity ramps up. No settled garment is loaded. The mannequin distance
field is generated **on the browser GPU** from the triangle BVH at startup,
using a 160 × 224 × 64 grid in bounded submissions. The grid is an approximation;
its cost and dimensions are included in results.

The solver is an original implementation informed by
[XPBD](https://matthias-research.github.io/pages/publications/XPBD.pdf) and
[Small Steps in Physics Simulation](https://mmacklin.com/smallsteps.pdf).
The reviewed [jspdown WebGPU example](https://github.com/jspdown/cloth) also
demonstrates parallel constraint coloring; its source was not vendored.

The workspace uses a blue drafting-table palette (#eef3f7, #ffffff, #17354a,
#265c9a, #527084), a Georgia wordmark and Segoe UI controls. The garment occupies
the main area, with controls on the left and measured values along the bottom.

## Validation and limits

Every load executes small GPU fixtures checking that self-contact separates two
unconnected vertices, adjacent vertices are excluded, and a distance constraint
matches the XPBD equation. Those checks restore the original state before use.

After saving browser measurements, run CPU-only geometry checks and GLB export:

```powershell
& $webgpuPython benchmarks/analyze_webgpu.py
```

That computes triangle stretch from rest coordinates, body vertex containment,
penetration depth, and validates the exported GLB. It does not run a simulator.

Known limits: materials are uncalibrated; opposite-vertex bending approximates
cloth bending; self-contact is particle-only; contact is discrete and the body
distance field is sampled. There is no continuous collision detection or proof
that triangles do not intersect. The strapless tube top currently slides down,
and the dress shirt has localized distortion. High frame rate does not establish
physically accurate fabric or fit. Mobile and other browser/GPU combinations
have not been benchmarked.

Read the [measured results](../../docs/WebGPU_simulator_2026-09-11.md) before
treating this as a replacement for the production simulator.
