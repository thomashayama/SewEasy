# Fabric material experiments

Open **Account → Fabrics → a fabric’s menu → Test fabric swatch**.
Two 80 × 40 mm strips compare warp and weft. Same-grain control uses warp
properties in both and never edits the saved material. All simulation is WebGPU
in the browser; the server only prepares geometry and material coefficients.

## Applied model

- Mass is rest triangle area × g/m² / 1000, including the 10 mm clamped part.
- Triangle membrane energy is A/2 × (Eu eu² + Ev ev² + G cos(angle)²).
  Eu/Ev/G are N/m, stretch strains are |Fu|-1 and |Fv|-1, and shear is the
  normalized dot product of the deformed material axes. Each scalar XPBD
  compliance is 1/(A × stiffness), with multipliers accumulated within a step.
  Hard distance constraints and the garment strain limiter are disabled here.
- Interior dihedral energy is D/2 × l/h × (theta-theta0)², h=(A0+A1)/(3l).
  D is an approximate directional interpolation of warp/weft rigidity using
  the curvature axis perpendicular to the rest UV edge. Compliance is 1/(D l/h).
  There is no measured bend/twist coupling or Poisson contraction model.
- Damping is exp(-rate × dt). Zero disables a property; null uses a labeled
  assumption (stretch 1000 N/m, shear 100 N/m, bend 1e-5 N·m, damping 14/s).
  Weight must be supplied. Thickness and friction are stored but these
  contact-free tests do not exercise them.
- Bend mode uses gravity 9.81 m/s². Stretch mode applies 25 N/m to the free edge
  (1 N total). Shear mode applies 5 N/m sideways (0.2 N total). Both loaded
  tests disable gravity; trapezoidal edge quadrature distributes the force.
- The solver uses 48 substeps per 1/60 s frame and 32 iterations, colored
  constraints, and a fixed comparison camera. Refinement uses 64 substeps. It measures
  real GPU vertex positions every 15 frames, and checks fixed pins and finite
  deformation. Six stable readings and low RMS speed establish numerical rest.
  Zero damping may keep a sample moving; that is not reported as equilibrium.

The 50-vertex mesh fits in one 128-thread workgroup. The optimized and reference
GPU implementations must agree within 0.01 mm after one frame. Membrane kernel
checks verify the SI energy equation, independent weft compliance, shear force,
zero moduli, rotation invariance, and fixed pins. Garment material assignment
remains a separate follow-up; this does not change saved garment simulations.

## Import and bending estimate

FAB L/W/B are warp/weft/bias; distance is cm and force is gram-force. Branches
remain distinct, including conditioning, loading and unloading. All are kept
in normalized SI curves and unmodified original source bytes.

Browzwear documents reported directional stretch in N/m. We use that linear
reported coefficient, not the vendor’s stretch linearity or raw hysteresis.
Vendor bend numbers have no reliable direct N·m mapping here. Instead, raw U1
and D1 short-loop loading branches after conditioning are fitted to an ideal
clamped, inextensible elastica:

    span/L = 2 E(m)/K(m) - 1
    force = 16 K(m)² × D × width/L² + cycle_force_offset

Fits use span/L between .55 and .94 and at least six points. Nonpositive slopes,
insufficient range, and normalized RMSE above .2 are rejected. At least two
accepted cycles are required; the median, range and each cycle’s residual error
are retained. This assumes fixed tangent clamps, no gravity and no clamp slip.
It estimates effective bending, not a certified measurement or an independently
validated prediction. Up/down asymmetry and relaxation can produce wide ranges.

The published Cupro sample yields warp D≈1.002e-5 N·m, range 4.162e-6–1.747e-5,
and weft D≈1.602e-5, range 1.238e-5–2.329e-5. Its reported stretch values are
587.51 and 1035.25 N/m. In particular, the bending spread is substantial and
physical swatch validation remains necessary. The old weight-only fixture’s
shared, much stiffer coefficient is no longer used in material comparisons.

## Validation

Desktop browser checks on the published Cupro sample: 25 N/m extension was
4.270% warp and 2.369% weft at 48 steps; 64 steps gave 4.256% and 2.421%.
Linear predictions are 4.255% and 2.415%. This verifies the implemented linear
model, not that the real fabric follows a linear law. Same-grain shear control
gave identical 13.472 mm displacements. Fixed pin error stayed below 0.00001 mm.
All GPU kernel checks passed, including damping and optimized/reference parity.
The comparison was also inspected at a 390 × 844 mobile viewport without
horizontal overflow. These are diagnostics, not portable golden values.

```powershell
python -m unittest test_fabrics test_browser_preview test_button_closures test_dress_shirt_collar -q
node --test benchmarks/test_swatch.mjs benchmarks/test_simulation_clock.mjs benchmarks/test_browser_drape.mjs benchmarks/test_collar_placement.mjs benchmarks/test_button_closures.mjs
```

Tests cover synthetic elastica recovery with force tare, unit conversion and
provenance, unknown/zero handling, legacy normalization and intentional clears,
lossless original files, privacy and CAS updates, triangle energy area scaling,
direction swapping, applied-load quadrature and race-free batches.

References: [Browzwear Physics Reference](https://help.browzwear.com/en/articles/13065506-physics-reference),
[FAB raw measurement documentation](https://github.com/vizoogmbh/u3m/tree/master/u3m1.1/physics),
[Strain Based Dynamics](https://matthias-research.github.io/pages/publications/strainBasedDynamics.pdf),
[Discrete Shells](https://www.cs.columbia.edu/cg/pdfs/10_ds.pdf),
[Small Steps in Physics Simulation](https://matthias-research.github.io/pages/publications/smallsteps.pdf).
