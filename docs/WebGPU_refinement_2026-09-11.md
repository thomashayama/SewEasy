# Browser simulator refinement — September 11, 2026

The browser-only experiment now has better sleeve placement, less triangle
distortion, surface contact, positional friction, a visible stretch diagnostic,
and an explicit fitting aid for the strapless top. It still requires no backend
GPU or Modal. This remains a standalone prototype, separate from the NiceGUI
draping path.

## Changes

- A principal-strain projection constrains triangle deformation, including shear
  that edge lengths alone miss. Constraints are colored to avoid shared-vertex
  writes. The 2% setting is an iterative target, not a guaranteed bound.
- Body contact also samples three edge midpoints and the triangle centroid.
  Particle self-contact recognizes neighbors across stitched panels. Positional
  friction corrects tangential displacement instead of only reducing velocity.
- Long sleeve/cuff assemblies are translated to match mannequin cross-sections
  at their cuff positions before sewing. This fixes cuffs closing above the arms.
  Sewing now takes 1.6 seconds before gravity, and the material is firmer.
- The tube-top cuff has 67 bending constraints across its seam to preserve the
  authored fold. **Hold neckline for preview** is a visible, optional height
  constraint. It is initially enabled for the tube top and recorded in results.
  The unsupported garment still falls; this aid does not validate its fit.
- A closer garment view, full-body framing, GPU stretch colors, a measurement
  dialog, and a 30-second measurement option make the experiment easier to inspect.

## Comparison

Same RTX 3060 Ti 8 GB and Chromium 152 as the initial experiment. Each baseline
row is five simulated seconds at 12 substeps per 1/60-second update, starting from
unsewn panels. No precomputed drape is loaded. Unthrottled rates include browser
encoding, rendering submission, GPU completion, timestamps and scheduling; they
are not guaranteed monitor FPS. GPU physics timing is reported separately.

| Garment | Previous p95 stretch | Refined p95 stretch | Previous worst stretch | Refined worst stretch | Updates/s | GPU physics median |
|---|---:|---:|---:|---:|---:|---:|
| T-shirt, 1.5 cm | 1.100× | 1.057× | 2.651× | 2.503× | 116.6 | 3.41 ms |
| T-shirt, 1 cm | 1.178× | 1.082× | 3.047× | 2.615× | 96.5 | 4.13 ms |
| Dress shirt, 1.5 cm | 1.162× | 1.127× | 6.980× | 2.494× | 110.8 | 3.74 ms |
| Dress shirt, 1 cm | 1.252× | 1.136× | 11.120× | 2.579× | 89.1 | 4.46 ms |

Stretch is the largest singular value of each triangle's deformation gradient
relative to its 2D rest pattern. A value of 1.10 means 10% extension in the most
stretched direction. These values describe the final captured pose, not the worst
transient during assembly.

The supported tube top reached 111.4 updates/s, with p95 stretch 1.064× and worst
stretch 1.354×. Its result is kept separate because the neckline aid changes the
physical problem. Turning the aid off in the same browser allowed it to fall.

The added work increases GPU physics cost from the earlier roughly 1.4–2.3 ms to
roughly 3.4–4.5 ms for these baseline trials. It remains within a 60 Hz budget on
this GPU. Browser scheduling differed between sessions, so the higher unthrottled
rates do not establish a speedup. Mobile and other GPU/browser combinations have
not been tested.

Normal playback of the supported tube top was observed at 59.9 updates/s and
continued beyond 90 simulated seconds with its cuff folded down.

## Validation

Nine GPU fixtures pass at load: particle separation; local and sewn-neighbor
exclusion; the XPBD distance equation; principal strain reduction; center-of-mass
preservation; rotation invariance; positional friction; and a triangle crossing a
sphere while its vertices remain outside. The tube top also passes a check that
its support changes only height. All fixtures restore initial state afterward.

All five meshes were exercised through the actual browser UI. Front, side, back,
garment/full-body views, the stretch overlay, reset, support release, measurement
dialog and result export were tested. Final measurement records contain no GPU
errors. An early support bind-group validation error was fixed before these runs.

Offline CPU analysis found zero inside-body vertices and zero inside-body surface
samples in all five final baseline captures. The fine dress shirt improved from
**82 to zero inside samples out of 91,784** edge-midpoint/centroid samples, using
the same body mesh. Its earlier zero-vertex count had missed those intersections.
Sampling is still not a proof that every point on every triangle clears the body.

The checker uses libigl distances to the actual body triangles, with pseudonormal
signs. Independent trimesh ray parity agrees at every negative sample, the 64
nearest samples and 128 distributed samples. Browser triangle-stretch statistics
agree with NumPy SVD, and GLB export/reload preserves finite vertices and geometry
counts. The checker and asset exporter run in the CPU-only environment.

The fine dress shirt continued for another 30 simulated seconds after its initial
five-second drape. Maximum movement over that continuation was 8.1 mm; p95 stretch
remained 1.136×. Final RMS velocity was 0.016 m/s, so some localized jitter remains.
The garment stayed on the mannequin.

With the static host stopped, a 2% width edit advanced another five simulated
seconds from that state. Maximum displacement was 12.0 mm and p95 stretch became
1.122×. The stretch overlay and camera also worked while disconnected. The host
was restarted only to save the capture. Pattern preparation and export remain
CPU-only; the host itself still uses only Python's standard library.

## Remaining limits

The solver is not a calibrated fabric or manufacturing-fit model. Local stretch
still reaches roughly 2.6× on shirt meshes. The fine dress shirt's worst stitch
gap is about 11.5 mm, compared with 4.8 mm in the earlier run: lower triangle
distortion does not mean every quality metric improved. The stretch display and
measurement report expose these residuals.

Body contact uses a sampled signed distance field and a finite set of cloth
surface samples. Self-contact is still particle-only. There is no continuous
collision detection, full triangle/edge self-contact, arbitrary pattern remeshing
during playback, animated mannequin, or validated multilayer fabric model.
The sleeve placement heuristic targets the existing cuff/panel naming and a
static mannequin; it is not a general garment dressing algorithm.

See [run instructions](../benchmarks/webgpu/README.md),
[initial evaluation](WebGPU_simulator_2026-09-11.md), and
[archived refinement measurements](../benchmarks/webgpu/results/2026-09-11-refined.json).
Generated mannequin geometry, captures and GLBs stay in ignored local output.

Algorithm references: [XPBD](https://matthias-research.github.io/pages/publications/XPBD.pdf),
[Small Steps](https://mmacklin.com/smallsteps.pdf), and
[Strain Based Dynamics](https://matthias-research.github.io/pages/publications/strainBasedDynamics.pdf).
