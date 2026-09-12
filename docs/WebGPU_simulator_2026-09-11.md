# Browser-only simulator evaluation — September 11, 2026

Follow-up: [refined solver, placement, diagnostics and comparative results](WebGPU_refinement_2026-09-11.md).

**A working SewEasy prototype now runs both cloth physics and rendering entirely
in browser WebGPU, with no GPU backend.** Normal playback was observed at 59.9
simulation updates per second on the RTX 3060 Ti. The page completed a full
300-frame drape and a separate 2% width-edit trial with its static server stopped.

This establishes feasibility for a browser preview. It does not establish
production-grade garment fitting: stretch is higher than in the Style3D trials,
some triangles distort severely, and the strapless tube top slides down.
The experiment is separate from the existing NiceGUI/Modal draping path.

## What runs where

- **CPU preparation:** SewEasy's existing Python DSL drafts patterns and BoxMesh
  triangulates them. The exporter prepares rest coordinates, constraints, seams
  and a mannequin triangle BVH. It produces ordinary static files.
- **Browser GPU:** builds the mannequin distance field, assembles/sews the cloth,
  integrates motion, projects constraints, handles body/particle contact, computes
  normals and renders the mesh. The renderer directly reads the simulation's
  GPU position buffer. No CPU position transfer is needed during normal playback.
- **Static host:** serves HTML, JavaScript and mesh data. The optional local result
  archive writes JSON only. It is not involved in advancing simulation frames.

A separate clean Python 3.11 environment containing no Warp, Newton, libuipc or
Modal successfully drafted and exported the T-shirt. Its vertex, face, UV,
constraint and BVH data matched the browser-tested asset exactly. The static
server itself ran under Python 3.13 with only standard-library imports.

## Measurements

Hardware: NVIDIA RTX 3060 Ti 8 GB, driver 591.86, Windows 11. Browser: Codex's
Chromium 152 browser surface, reporting a WebGPU NVIDIA Ampere adapter.
Default solver: 12 substeps per 1/60-second frame, graph-colored small-step XPBD,
body contact and particle self-contact enabled. Each row covers 300 simulation
updates / five simulated seconds. Benchmark mode is unthrottled; normal playback
targets 60 updates/s.

| Garment / mesh | Vertices | Unthrottled updates/s | Median GPU physics | Final inside-body vertices | p95 triangle stretch |
|---|---:|---:|---:|---:|---:|
| T-shirt, 1.5 cm, final baseline | 3,414 | 87.2 | 1.77 ms | 0 | 1.100 |
| T-shirt, 1 cm | 7,505 | 93.5 | 1.90 ms | 0 | 1.178 |
| Dress shirt, 1.5 cm | 5,639 | 94.3 | 1.70 ms | 0 | 1.162 |
| Dress shirt, 1 cm | 12,300 | 81.1 | 2.29 ms | 0 | 1.252 |
| Tube top, 1.5 cm | 2,998 | 98.5 | 1.64 ms | 0 | 1.283 |

The tube top's high speed and zero inside vertices do **not** make its fit valid:
it slid from the bust toward the hips. Likewise, the fine dress shirt's worst
triangle stretch reached 11.1×, despite its p95 being 1.25×. Local distortions,
initialization and fabric behavior need further work. Zero inside vertices is a
vertex-containment measurement, not proof that triangles never cross the body.

Browser throughput includes JavaScript command encoding, GPU completion,
rendering submission, timestamp readback and animation-frame scheduling.
GPU physics timings use WebGPU timestamp queries. Separate render-pass timestamps
were unresolved/zero on this setup, so no standalone GPU rendering-time claim is
made. These are simulation-update rates, not guaranteed displayed monitor FPS.

Throughput varied across runs and with other open preview tabs: a prior T-shirt
run reached 99.5 updates/s; a disconnected run with another active preview reached
52.1. Both are preserved. Idle rendering was subsequently removed; the final
T-shirt baseline above reached 87.2. There are no confidence intervals or
mobile/cross-browser performance claims.

The body distance field is generated on the browser GPU at 160 × 224 × 64 samples.
Measured construction took about 1.0–1.9 seconds; total asset/pipeline setup was
roughly 1.2–2.3 seconds in these local runs. Those costs are excluded from the
simulation-update rate. Static JSON assets are currently 9–15 MB; binary packing,
compression and shared body caching remain deployment optimizations.

## Live edit and disconnected tests

The static host and earlier CUDA preview server were stopped before the
disconnected tests. The already-loaded page completed 300 drape frames without
network access to either service. After creating a drape, a second disconnected
test increased rest-panel width by 2% and advanced another 300 frames using the
existing GPU state. No shader, solver or mesh rebuild was required for the edit.

The edit trial processed five simulated seconds in 2.03 wall seconds, with
1.64 ms median GPU physics. Maximum displacement from the prior drape was 2.23 cm
and final RMS vertex velocity was 0.00035 m/s. Subsequent normal playback showed
59.9 updates/s, continuing past 47 simulated seconds. These tests exercise a
fixed-topology width change, not arbitrary SewEasy design edits or remeshing.

The host was restarted only to archive results. Front/side views, run/pause,
reset, garment selection and the width control were exercised. The final browser
error log was empty. At startup, GPU fixtures passed for particle separation,
adjacent-vertex exclusion and the XPBD distance equation. Exporter checks enforce
positive rest area/mass, seam mapping and race-free constraint colors. Offline
CPU analysis verifies finite positions and GLB export/reload geometry.

## Limitations and next work

The solver uses distance-based stretching and approximate opposite-vertex bending.
It has no calibrated fabric model, strain-limiting guarantee, continuous collision
detection, edge/triangle self-contact, animated mannequin or validated multilayer
garments. The signed body distance is approximated from nearest surface normals
and then sampled into a grid. Initial panels are raised 6 cm and sewn before
gravity; more general garment placement is still needed.

The original assembly attempt applied gravity while sewing and dropped the
T-shirt. Sewing first kept it on the body but querying the detailed triangle BVH
every substep cost 31.65 ms of GPU physics per frame. The distance field reduced
that cost substantially; it trades geometric precision for speed. These earlier
trials remain in the archived evidence.

With the no-GPU-backend requirement, the next development path is to improve this
browser solver's strain/bending model, garment placement and self-contact, then
connect CPU pattern generation to the browser component in NiceGUI. Keeping the
existing authoring DSL does not require keeping GPU simulation on the server.

The implementation uses JavaScript orchestration and WGSL compute/render shaders.
Rust was not needed to demonstrate the speed or remove the GPU backend.
Algorithm references: [XPBD](https://matthias-research.github.io/pages/publications/XPBD.pdf)
and [Small Steps in Physics Simulation](https://mmacklin.com/smallsteps.pdf).

See [run instructions and implementation details](../benchmarks/webgpu/README.md),
[raw measurements](../benchmarks/webgpu/results/2026-09-11.json), and the earlier
[CUDA comparison](Simulator_benchmarks_2026-09-11.md). Generated body/cloth assets
stay local and are not included in the committed evidence.
