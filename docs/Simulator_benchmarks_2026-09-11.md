# Simulator evaluation — September 11, 2026

**Newton's Style3D solver is the strongest candidate tested for SewEasy's live
preview.** A working local browser prototype delivered 55.5 simulation updates
per second for the T-shirt and 29.8 for the finer dress shirt. Physics ran on the
host RTX 3060 Ti; Three.js rendered the positions in the browser. No Rust or
browser-native WebGPU solver was implemented or benchmarked.

This is an evaluation result, not a production migration. The dress shirt still
has body penetration and collar defects. Material calibration, reliable garment
initialization, arbitrary pattern edits and multilayer self-contact remain work.

## What was exercised

The tests used the actual `t-shirt`, `dress-shirt` and `element-top` SewEasy
presets and existing `mean_all` body, starting from repository commit `536916d`.
Each run drafted the parametric garment, serialized its specification/SVG,
meshed panels through BoxMesh, simulated cloth, exported GLB and saved positions
for browser inspection. A separate live test advanced a persistent Style3D
session from the browser and tested a small fabric-width edit.

The benchmark environment is isolated from the application. Versions tested:
Python 3.11.15, Newton 1.6.0, Warp 1.17.0, pyuipc 0.0.28, Three.js 0.180.0.
Machine: Windows 11, NVIDIA RTX 3060 Ti 8 GB, driver 591.86. The raw Windows
platform string identifies build 26200 as Windows 10.

## Live browser results

| Test | Cloth vertices | Browser updates/s | Median request | Request p95 | Setup/rebuild | Wall time for simulation updates |
|---|---:|---:|---:|---:|---:|---:|
| T-shirt, initial drape | 3,187 | **55.5** | 14.1 ms | 16.6 ms | 2.29 s | 5.41 s for 5 s simulated |
| T-shirt, 2% width edit | 3,187 | **58.0** | 13.5 ms | 15.4 ms | 1.17 s | 3.10 s for 3 s simulated |
| Dress shirt, 1 cm mesh | 11,615 | **29.8** | 27.5 ms | 28.7 ms | 3.10 s | 10.07 s for 5 s simulated |

Each browser iteration requests one complete 1/60-second physics frame, receives
binary Float32 positions, updates the mesh/normals and waits for an animation
frame. Observed updates/s includes that scheduling and transport. Request time
includes physics, readback and HTTP transfer over localhost. These are not
rendering FPS, WAN measurements or multi-user server capacity estimates. Setup
and the final offline geometry checks are excluded from the update-loop wall time.

The width edit reuses the previous drape positions, increases 2D rest-panel width
by 2%, rebuilds the solver and clears velocity. It verifies reuse of an existing
drape at fixed topology; it does not exercise a SewEasy design slider, pattern
redrafting or remeshing/state transfer.

## Solver comparison

These are within-run frame timings, including all solver substeps and GPU
synchronization. Each main trial simulated 300 frames / five seconds. One run
per configuration was measured; percentiles are not confidence intervals.

| Solver / configuration | Garment | Vertices | Median frame | p95 frame | Final inside-body vertices | p95 stretch ratio |
|---|---|---:|---:|---:|---:|---:|
| Style3D, 4 substeps × 4 iterations | T-shirt, 1.5 cm | 3,187 | **12.64 ms** | 13.96 ms | 0 | 1.040 |
| Style3D, 4 × 4 | Tube top, 1.5 cm | 2,883 | **12.91 ms** | 15.21 ms | 0 | 1.020 |
| Style3D, 4 × 4 | Dress shirt, 1.5 cm | 5,167 | **21.45 ms** | 22.63 ms | 3 | 1.094 |
| Style3D, 4 × 4 | T-shirt, 1 cm | 7,175 | **17.54 ms** | 18.95 ms | 0 | 1.033 |
| Style3D, 4 × 4 | Dress shirt, 1 cm | 11,615 | **23.80 ms** | 28.79 ms | 10 | 1.096 |
| VBD, 4 × 10 | T-shirt, 1.5 cm | 3,187 | 57.25 ms | 72.46 ms | 199 | 1.447 |
| VBD, 4 × 10 | Tube top, 1.5 cm | 2,883 | 41.25 ms | 43.42 ms | 149 | 1.120 |
| VBD, 4 × 10 | Dress shirt, 1.5 cm | 5,167 | 91.19 ms | 106.50 ms | 713 | 2.637 |
| libuipc, separated panels + soft stitches | T-shirt, 1.5 cm | 3,414 | 86.95 ms | 350.83 ms | 0 | 1.036 |

Stretch is the largest singular value of each triangle's deformation gradient
relative to its **2D fabric rest shape**. A ratio of 1.04 means 4% extension in
that triangle's most stretched direction. The table reports the 95th percentile
across triangles; it is not a calibrated fabric acceptance threshold.

All five Style3D trials settled below 0.01 m/s RMS vertex velocity over the last
three recorded samples. The coarse dress shirt's deepest inside vertex was
16.4 mm; the fine shirt's was 21.9 mm. Zero inside vertices does not establish
that no triangle crosses the body, and self-intersections were not counted.
Visual inspection found a useful T-shirt drape but unfinished collar behavior
on the dress shirt. Buttons, zippers, material textures and animated bodies
were outside this experiment.

VBD was also tested from an already settled Style3D T-shirt: 9.72 ms median with
two substeps and ten iterations, with zero inside vertices, but 1.417 p95 stretch.
That speed result does not meet the intended garment-shape quality. The VBD
trials indicate this adapter/material setup needs work, not that VBD is universally
slower or less accurate.

IPC rejected initially touching panel edges. Translating panels apart by 1.5 cm
along signed X/Z directions allowed the trial to run. Five seconds of simulation
took 43.61 seconds; the first frame took 1.80 seconds. Final soft-seam gaps were
3.82 mm at p95 and 3.87 mm maximum, visible in the browser. IPC timing includes
geometry retrieval every frame and its cold first step. Newton timing excludes
periodic readback and compilation; this is not a strictly equal-overhead ranking.

## Adapter and timing details

Newton uses SewEasy's welded seam topology. Fabric rest coordinates are retained
separately from assembled world positions, centimetres are converted to metres,
and both body and cloth receive the same ground shift. Reversed panels have
their local rest X coordinate reflected to satisfy Newton's positive-area
requirement. Triangle count, positive vertex mass and total mass derived from
2D rest area are checked. Panel stiffness multipliers are applied to bending.

Style3D uses stretch parameters `(1000, 1000, 100)`, area stiffness 1000,
surface density 0.3 kg/m² and anisotropic bending `(2e-5, 1e-5, 5e-6)`. Body
contact stiffness is 10000; collisions are refreshed every substep and cloth
self-contact is enabled. VBD's main trials use stretch stiffness 10000, ten
iterations and self-contact. IPC uses its strain-limiting Baraff–Witkin shell,
discrete shell bending and 227 soft stitch pairs. The scripts contain the full
settings. Equal numerical parameters do not imply equal physical materials
between these models; fabric responses were not calibrated.

SewEasy's welded initialization stretches some seam-adjacent triangles severely.
The original simulator includes body-part drag and attachment constraints that
these adapters do not reproduce. The source dress-shirt pattern also reports
self-intersecting panels during drafting. These are meaningful integration issues.

For the coarse T-shirt, measured drafting, meshing, cached solver setup, five
seconds of simulation and export were approximately 1.01, 0.28, 1.12, 3.85 and
0.06 seconds respectively. Their sum is 6.32 seconds, excluding imports/process
startup and offline quality analysis. A full new garment is therefore not an
instant operation even when an existing simulation advances near realtime.
Initial kernel compilation in early trials took about 34 seconds for Style3D
and 27 seconds for VBD; a persistent prewarmed worker matters.

## Recommended direction

1. Keep SewEasy's Python pattern DSL and panel/rest-coordinate representation.
   Use Newton Style3D in a persistent GPU worker for the first interactive
   simulator. Stream changing vertex positions to the browser; keep mesh topology
   and body geometry resident in the renderer.
2. Resolve initialization, collar/body contact, seam/fold behavior and fabric
   calibration before treating this as reliable fit simulation. Add larger and
   multilayer garments and varied body shapes to the validation set. Establish
   triangle-level body and self-intersection checks.
3. Implement actual design edits with state transfer and controlled remeshing;
   measure remote transport and concurrent-session capacity. The local prototype
   demonstrates feasibility but is separate from the NiceGUI application.
4. If physics must run entirely on the customer's device in a browser, evaluate
   WebGPU separately. Rust/WASM can provide orchestration and mesh processing;
   the GPU solver/contact kernels still need a WebGPU implementation. These
   results provide no evidence for a Rust speedup. Prefer reuse of a proven
   cloth/contact implementation over starting with a wholesale language rewrite.

## Existing stack and sources

At the start of this evaluation the fork's most recent commit was July 23, 2026,
about seven weeks old. Its simulator dependency is substantially older: the
GarmentCode Warp fork identifies itself as based on Warp 1.0.0-beta.6 and contains
GarmentCode-specific initialization/contact changes. Its README explicitly
restricts that dependency to non-commercial use. This is separate from the
SewEasy/GarmentCode MIT license. [Original dependency and its modifications](https://github.com/maria-korosteleva/NvidiaWarp-GarmentCode).

Newton provides both the projective-dynamics Style3D cloth solver and VBD.
Newton and libuipc publish Apache-2.0 licenses. Body-asset permissions remain a
separate concern; this experiment adds no body geometry to the committed results.
[Newton solver API](https://newton-physics.github.io/newton/latest/api/newton_solvers.html),
[Newton repository and license](https://github.com/newton-physics/newton),
[libuipc repository, CUDA backend and license](https://github.com/spiriMirror/libuipc).

Reproduction instructions: [benchmarks/README.md](../benchmarks/README.md).
Evidence: [raw measurements](../benchmarks/results/2026-09-11.json). The snapshot
includes unsuccessful tuning trials, the IPC initialization rejection, live
measurements and an artifact verification record. Local output lives under
`output/simulator-benchmark`; use `serve_live.py` to reopen the preview.

Validation passed for 20 recorded outputs, including an 11-frame check that the
last recorded frame matches the exported geometry. A warm start with IPC's
different face topology was correctly rejected. Browser run selection,
initial/final views, front/side views, playback progression, live simulation and
the width edit were exercised; the browser error log was empty. Python
compilation checks passed for the benchmark, core library, GUI and assets.
