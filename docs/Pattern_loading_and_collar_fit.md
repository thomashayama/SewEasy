# Pattern loading and dress-shirt collar fit — September 14, 2026

## Loading

Profiling found repeated scalar curvature calculations in the sleeve's numerical
fit. Each optimizer evaluation sampled the curve 70 times. The left/right sleeves
also solved identical geometry independently. Cubic curvature now evaluates those
same samples with NumPy, and a bounded cache reuses armhole fits. Each caller gets
an independent copy because garment assembly mutates edge endpoints.

`benchmarks/benchmark_draft.py` measures complete local SVG drafts (imports and
HTTP excluded). Three samples per configuration gave these medians:

| Configuration | Draft time |
| --- | ---: |
| Scalar curvature, no armhole cache | 1,278 ms |
| Vector curvature, no armhole cache | 644 ms |
| Optimized, empty cache before each draft | 495 ms |
| Optimized, reused armhole geometry | 314 ms |

The small SVG now travels in the same UI update as its picking paths, avoiding
another image request and per-edit static route. Draft workers only change model
data; publishing UI changes runs on the event-loop thread. The canvas emits its
preview trigger after an image load and a browser paint opportunity. A body
revision still triggers preparation when the SVG bytes haven't changed. Empty
designs clear the preview without waiting for an image event.

On a local page reload, the DOM recorded **299 ms drafting / 724 ms to pattern
paint**. These are machine-specific observations, not a latency guarantee.
The first page after a server restart was slower: **2,850 ms drafting / 3,575 ms
to paint**. Cold server loading still has overhead beyond the repeated-draft
benchmark; the 724 ms observation applies to a reload with a running server.
`data-draft-ms` and `data-paint-ms` on `.se-pattern-canvas` retain these diagnostics
without displaying a notification. In Pattern view, the preview reached its
background-ready state; opening 3D reused the existing scene.

## Collar

The former draft treated the broad `neck_w` measurement as the opening width and
expanded the collar stand upward. Its roll line was about **59.5 cm** around the
default mannequin, whose neck is roughly 40–44 cm at collar height.

The revised draft estimates neck-base girth from `neck_w`, applies the existing
neck-ease control, raises the front neckline, and tapers the stand inward. The
default base seam is now about **46.2 cm**, with a **42.7 cm** roll line. Button
extensions add overlap without increasing that functional neck size. Matching
stand/fall seams and the physical neck-button attachment are retained.

Four revisions were examined. The tighter second revision produced excess local
stretch. A more aggressive taper in the fourth revision curled one collar point
upward. Revision three retained close fit and downward falls across the default,
fine-mesh, and larger-body tests.

Each settled test ran 1,800 browser WebGPU steps, representing 30 simulation
seconds. Before/after measurements and rejected iterations are recorded in
`benchmarks/webgpu/results/2026-09-14-collar-fit.json`.

| Case | Median stand clearance | 95th-percentile clearance | GPU step |
| --- | ---: | ---: | ---: |
| Previous collar | 13.0 mm | 30.7 mm | 7.8 ms |
| Revised, 1.5 cm mesh | 5.2 mm | 18.0 mm | 8.1 ms |
| Revised, 1.0 cm mesh | 4.7 mm | 12.1 mm | 8.7 ms |
| Revised, larger body | 5.1 mm | 19.1 mm | 8.3 ms |

All three chosen-revision captures had closed collar seams, no sampled body
penetration, downward collar tips, and all 18 GPU kernel checks passing. Visual
checks included front, back, and side views. Automated regressions cover taper,
button overlap, seam lengths, point changes, mirrored fold placement, distributed
fold constraints, curvature equivalence, cache isolation, and preview scheduling.
The larger-body turning test also stayed finite, retained closed collar seams
with no sampled body penetration, and kept the neck-button attachment at 3.05 mm
(its intended shank clearance is 3 mm).

This remains an approximate drape preview: neck circumference is estimated from
neck-base width, and local triangle stretch still varies with mesh resolution
(95th-percentile collar stretch ratios 1.17–1.30 in these runs). These checks
establish a better simulated fit, not physical validation of a sewn sample.
