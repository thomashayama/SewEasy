# Simulator experiments

Real SewEasy patterns → panel-aware mesh → GPU cloth solver → GLB and browser
recording, plus a live browser preview backed by a persistent local GPU session.
See [measured results and recommendation](../docs/Simulator_benchmarks_2026-09-11.md).

These are evaluation adapters, not replacements for the application's simulator.
They use the existing mean_all body for local evaluation; do not publish the
generated body geometry without resolving its asset license. Generated geometry,
recordings and the isolated environment remain in ignored directories.

## Reproduce on Windows with an NVIDIA GPU

Run from the repository root. Python 3.11 was tested. `uv` downloads that Python
version when needed. The lock file describes the complete isolated environment;
do not install it over the application's patched Warp environment.

```powershell
uv venv --python 3.11 tmp_newton_env
uv pip install --python tmp_newton_env/Scripts/python.exe -r benchmarks/requirements-lock.txt
$benchPython = 'tmp_newton_env/Scripts/python.exe'
& $benchPython benchmarks/prepare_cloth.py
& $benchPython benchmarks/prepare_cloth.py --garments t-shirt dress-shirt --resolution 1.0

foreach ($garment in @('t-shirt', 'dress-shirt', 'element-top')) {
    & $benchPython benchmarks/run_newton.py "output/simulator-benchmark/${garment}_1.5cm/mesh.npz" --solver style3d --label style3d-tuned --substeps 4 --iterations 4 --frames 300 --collide-substeps
    if ($LASTEXITCODE) { throw 'Style3D trial failed' }
    & $benchPython benchmarks/run_newton.py "output/simulator-benchmark/${garment}_1.5cm/mesh.npz" --solver vbd --label vbd-tuned --substeps 4 --iterations 10 --stiffness 10000 --frames 300 --collide-substeps
    if ($LASTEXITCODE) { throw 'VBD trial failed' }
}
foreach ($garment in @('t-shirt', 'dress-shirt')) {
    & $benchPython benchmarks/run_newton.py "output/simulator-benchmark/${garment}_1cm/mesh.npz" --solver style3d --label style3d-tuned --substeps 4 --iterations 4 --frames 300 --collide-substeps
    if ($LASTEXITCODE) { throw 'Fine-mesh trial failed' }
}
```

Run GPU experiments sequentially. A fresh kernel cache adds compilation time;
the frame timings exclude that time and the result records setup separately.
Newton's frame loop includes GPU synchronization and all collision substeps.

Test IPC's original initialization rejection and then the separated-panel trial:

```powershell
& $benchPython benchmarks/run_uipc.py output/simulator-benchmark/t-shirt_1.5cm/mesh.npz --frames 300
# The command above is expected to fail validation for touching panel edges.
& $benchPython benchmarks/run_uipc.py output/simulator-benchmark/t-shirt_1.5cm/mesh.npz --frames 300 --separate-panels
```

Test reuse of an existing drape:

```powershell
$benchMesh = 'output/simulator-benchmark/t-shirt_1.5cm/mesh.npz'
$benchStart = 'output/simulator-benchmark/t-shirt_1.5cm/style3d-tuned/trajectory.npz'
& $benchPython benchmarks/run_newton.py $benchMesh --solver vbd --label vbd-warm --substeps 2 --iterations 10 --frames 180 --collide-substeps --start-from $benchStart
& $benchPython benchmarks/run_newton.py $benchMesh --solver style3d --label style3d-width-edit --substeps 4 --iterations 4 --frames 180 --collide-substeps --start-from $benchStart --rest-width-scale 1.02
```

The width experiment changes 2D fabric rest coordinates at fixed topology. It
rebuilds the solver and starts from previous positions with zero velocity. It
does not redraft a new pattern or transfer state between different meshes.

## Browser checks

```powershell
& $benchPython benchmarks/build_viewer.py
& $benchPython benchmarks/serve_live.py
```

Open <http://127.0.0.1:8766>. Select a `style3d-tuned` recording and press **Run
live GPU · 300 frames**. After it finishes, **Widen 2% · 180 frames** tests the
edit. Each completed run saves its live timing, geometry checks, GLB and recording
under `live-style3d` or `live-width-edit` beside the selected trial. Repeating the
same live trial overwrites that local result. Keep one browser client active.

The UI counts actual simulation updates, including the browser request loop and
animation-frame scheduling. The renderer can draw between updates; this counter
is not a GPU rendering benchmark. Physics runs in CUDA on the host. This tests
loopback transport, not WAN latency, a production server or browser-native physics.

For playback without a CUDA server:

```powershell
& $benchPython -m http.server 8765 --bind 127.0.0.1 --directory output/simulator-benchmark
```

The live buttons require `serve_live.py`. Three.js 0.180.0 loads from jsDelivr.

## Verify and preserve results

```powershell
& $benchPython benchmarks/verify_artifacts.py
& $benchPython benchmarks/snapshot_results.py
& $benchPython benchmarks/build_viewer.py
& $benchPython -m compileall -q benchmarks seweasy gui assets
```

Verification checks nonzero motion, finite output, face/vertex indices, frame
accounting and GLB export geometry. A passing artifact check does **not** mean a
valid garment fit. Read penetration, strain, seam-gap and settling measurements.
Self-intersection counts and calibrated fabric equivalence are not measured.

`results/YYYY-MM-DD.json` stores the measurements, per-frame timings and explicit
failed trials without mesh assets. Initial tuning failures are kept in the
September 11 snapshot; they are not discarded to improve the reported outcome.
