# Fabric weight experiment

Open **Account → Fabrics → a fabric's menu → Test fabric swatch**.
The old, fitted tee comparison obscured the effect of changing weight alone.
The replacement uses two clamped strips, an overlaid side profile on equal
millimetre axes, and GPU-measured free-edge displacement. Equal-weight control
replaces the test's mass temporarily; it never changes the saved fabric.

## Model and limits

- 80 mm free length, 40 mm width, 10 mm clamped region, 50 vertices.
- Lumped mass from undeformed triangle area × imported g/m² / 1000. Physical
  masses include the clamped portion; zero inverse mass represents fixed points.
- Gravity 9.81 m/s², inextensible mesh edges, damping 14/s. No contact or wind.
- Interior dihedral bending with the same **assumed** coefficient kB = 0.00025
  N·m for both strips. This is not a measured Cupro property.
- Discrete-shell energy per hinge is kB × l/h × (theta - theta0)², with
  h = (A0 + A1)/(3l). XPBD compliance is 1/(2 kB l/h).
- 24 substeps per 1/60 s frame, eight coupled distance/bending iterations.
  Bending multipliers accumulate within a substep and reset each substep.
  The refinement control doubles the substeps for a sensitivity check.
- The swatches share a clock and fixed cameras. The profile averages each
  cross-section across the width. Readbacks occur every 15 simulation frames.
- Rest detection requires six consecutive samples with <0.015 mm change at
  each tip and RMS speed <0.2 mm/s, after at least three simulated seconds.
  Unstable positions, displaced clamps, excessive stretching, and failure to
  settle produce errors rather than a successful result.

The tiny mesh fits in one GPU workgroup (maximum 128 vertices, 256 hinges).
The optimized shader retains intermediate state in workgroup memory. A one-frame
GPU comparison against the ordinary colored solver must agree within 0.01 mm at
every vertex before the test runs. GPU checks also exercise a flat rest angle,
fixed pins, and the existing cloth kernels. The garment solver keeps its previous
bending model and settings; this fixture is not material assignment to garments.

Imported bending/stretch/shear curves, friction, and thickness are **not applied**.
Passing this test establishes density wiring and a plausible weight response,
not correspondence with a real fabric. Material calibration, mesh convergence,
anisotropy, hysteresis, and physical sample validation remain necessary.

## Observations, September 2026 desktop browser

The official SU-1098 Cupro example provides approximately 105.6 g/m². Under the
shared assumptions, tip drop was approximately 5.34 mm versus 14.42 mm for the
300 g/m² reference. Doubling the time resolution produced about 5.19 mm and
14.42 mm. These are diagnostic results, not real-world Cupro predictions or
portable bit-for-bit golden values. Equal-weight control produces coincident
profiles. Both the ordinary and optimized GPU paths were inspected visually.

Automated checks:

```powershell
python -m unittest test_fabrics test_browser_preview test_button_closures test_dress_shirt_collar -q
node --test benchmarks/test_swatch.mjs benchmarks/test_simulation_clock.mjs benchmarks/test_browser_drape.mjs benchmarks/test_collar_placement.mjs benchmarks/test_button_closures.mjs
```

References: [Discrete Shells, Grinspun et al. (2003)](https://www.cs.columbia.edu/cg/pdfs/10_ds.pdf),
[Small Steps in Physics Simulation, Macklin et al. (2019)](https://matthias-research.github.io/pages/publications/smallsteps.pdf).
