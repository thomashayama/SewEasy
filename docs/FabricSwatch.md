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
- The 10 mm cells are split in a checkerboard of the two diagonals, which is
  mirror-symmetric about the strip, so a symmetric load cannot twist it.
- Interior dihedral energy is D/2 × l/h × (theta-theta0)², h=(A0+A1)/(3l).
  Compliance is 1/(D l/h). Edges across the strip and the diagonals take the
  rigidity along the strip, the one under test; only edges lying along the
  strip take the other. On this grid l/h is divided by 2.431 and doubled on the
  clamp line (see Bending against the elastica and Mesh resolution).
  There is no measured bend/twist coupling or Poisson contraction model.
- Damping is exp(-rate × dt). Zero disables a property; null uses a labeled
  assumption (stretch 1000 N/m, shear 100 N/m, bend 1e-5 N·m, damping 14/s).
  Weight must be supplied. Thickness and friction are stored but these
  contact-free tests do not exercise them.
- Bend mode uses gravity 9.81 m/s². Stretch mode applies 25 N/m to the free edge
  (1 N total). Shear mode applies 5 N/m sideways (0.2 N total). Both loaded
  tests disable gravity; trapezoidal edge quadrature distributes the force.
- Bending uses 12 substeps per 1/60 s frame and four iterations; refinement
  uses 24 steps/eight iterations. Its clock follows display time with bounded
  work, including 30 Hz displays. Loaded tests use four iterations and a
  substep count sized from the fabric's own stiffness (see Numerical range;
  refined: twice as many) with a fixed simulation increment for repeatable readings.
  They stay planar under in-plane forces, so zero-energy bending passes are
  skipped. Cameras stay fixed for comparison. The solver measures
  real GPU vertex positions every 15 frames, and checks fixed pins and finite
  deformation. Six stable readings and low RMS speed establish numerical rest.
  Zero damping may keep a sample moving; that is not reported as equilibrium.

The 50-vertex mesh fits in one 64-thread workgroup. The optimized and reference
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

## Numerical range

The loaded tests have an exact answer. The energy has no Poisson coupling, a
uniform strain is representable by linear triangles, and trapezoidal edge loads
are consistent with them, so a converged strip extends by exactly
traction ÷ stiffness on any mesh. Any other reading is solver error, which
makes it measurable. `benchmarks/swatch_reference.mjs` repeats the GPU solver
on the CPU step for step; on the application's own scenes it reproduces the
browser's readings to four figures (cupro bend 73.29 / 70.53 mm and shear
13.51 / 9.71 mm on both), so its findings are the GPU's.

What it found, on the stiff polyester's warp (6571 N/m, exact 0.3804%):

| Substeps × iterations per frame | Reading | Error |
| --- | --- | --- |
| 12 × 32 | 3.628% | +854% |
| 48 × 32, the old setting | 0.528% | +39% |
| 48 × 128 | 0.366% | −3.8% |
| 48 × 512 | 0.381% | +0.02% |
| 192 × 8, the old cost | 0.422% | +10.8% |
| 384 × 4, the old cost | 0.392% | +3.0% |
| 768 × 4 | 0.381% | +0.01% |
| 832 × 4, the sized step | 0.380% | −0.10% |

- **Step size, not iterations.** The sized step reads far closer than
  48 × 128 at about half its cost, and adding iterations alone converges
  slowly and not monotonically. An under-converged solve also drifted a pure
  pull sideways by up to 1.5 mm; at the sized step it does not.
- **Not floating point.** Float32 and float64 agree to four figures at every
  stretch and shear setting, up to 768 substeps. Bending is the exception:
  below about 1/190 of a frame, gravity's per-step increment nears float32
  resolution and the drop wanders by 0.3%, so bending keeps its larger step.
- **Not the mesh, for stretch.** The exact answer is mesh-independent, and
  the reading matches it. Shear and bending are discretised, so their readings
  carry the 10 mm mesh's own error; Mesh resolution below measures it.
- **Bending is insensitive.** Its drop moves under 0.3% from 12 × 4 to 192 × 4.

The governing number is XPBD's stiffness ratio for a constraint, Σw|∇C|²·dt² ÷
compliance: stiffness over mass, times the step squared. The old setting put
the polyester near 400. `loaded_numerics` sizes the step so the worst
constraint sits at 1, between 96 and 1024 substeps, with four iterations:

| Fabric | Substeps | Warp / weft error, old | Now |
| --- | --- | --- | --- |
| Polyester dobby, 6571 / 3560 N/m | 832 | +39% / +8.9% | −0.10% / −0.04% |
| Cotton voile, 1675 / 338 N/m | 390 | −2.4% / +0.1% | −0.03% / −0.01% |
| Cupro, 588 / 1035 N/m | 286 | +0.2% / −0.9% | −0.01% / −0.02% |

The target was 2 until the mesh study. There a light, soft cloth (60 g/m²,
200 N/m) still read 1.0% low and the cupro's weft 0.36% low; at 1 they read
0.13% and 0.02% low, for 41% more steps.

Shear moved the same way: the polyester over-read by 29% and is now within
0.05% of a far finer solve. **Error budget for the step:** inside the range,
every measured sample reads within 0.1% of exact and every synthetic case from
60 to 350 g/m² and 50 to 10 000 N/m within 0.2%. Past 1024 substeps the step
can shrink no further; the scene says so and the dialog warns. That now starts
sooner, for cloth both light and stiff (60 g/m² above about 7 500 N/m). There
the error grows with the ratio: 2% at 4, 15% at 8 and 74% at 20, reached by
100 000 N/m at 40 g/m². Soft cloth costs less than the old fixed step, stiff
cloth up to 2.7 times more, which these tests accept.

### Bending against the elastica

A clamped strip under its own weight also has an exact answer: the heavy
elastica, D θ″ = −q (L − s) cos θ with θ(0) = 0 and θ′(L) = 0. The bend test was
not reproducing it. The strip bent as if its rigidity were about twice the value
entered, so the polyester's warp dropped 57.4 mm where the elastica gives
66.4 mm. This was the model, not the solver: the drop barely moves with the step.

Two causes, both in how curvature is lumped onto this mesh:

- Discrete Shells' l/h assumes curvature is shared among three unstructured
  edge directions. On a right-triangle grid bent along a mesh axis only the cross
  edges and diagonals fold, which over-counts rigidity by 2.4 on paper and 2.431
  measured against a small-deflection cantilever, where beam theory is exact.
- The hinge on the clamp line stands for half a cell of curvature, not a whole
  one. Treating it as a whole cell left the strip about 3.5% too limp even
  after the first correction.

With both, at the application's own settings (the last column is the mesh
the application uses now; Mesh resolution says what changed):

| Fixture | Elastica | Uncorrected | Checkerboard, 2.431 |
| --- | --- | --- | --- |
| Polyester warp, 1.99e-5 N·m | 66.39 mm | 57.37 (−13.6%) | 66.13 (−0.4%) |
| Polyester weft, 1.36e-5 | 69.69 | 63.85 (−8.4%) | 69.61 (−0.1%) |
| Voile warp, 1.00e-5 assumed | 72.28 | | 72.57 (+0.4%) |
| Cupro warp, 1.00e-5 | 72.87 | 71.12 (−2.4%) | 73.28 (+0.6%) |
| Cupro weft, 1.60e-5 | 70.49 | 66.14 (−6.2%) | 70.53 (+0.05%) |
| Voile weft, 2.23e-6 | 76.60 | 77.85 (+1.6%) | 78.11 (+2.0%) |

**Error budget:** within 1% of the elastica up to a 72 mm drop, rising smoothly
to 2.5% for the limpest fabrics, which curl at the clamp more tightly than a
10 mm cell can follow. On the GPU the cupro read 73.29 / 70.53 mm, the CPU
reference's own figures. The dialog shows the elastica's drop beside the reading.

Earlier drops quoted in this document and in FabricSources.md were read before
this correction and are too small by the amounts above.

### Mesh resolution

The application's grid is fixed at 10 mm, 50 vertices in one GPU workgroup.
`benchmarks/swatch_mesh.mjs` builds the same strip at any cell size, and is
tested to equal the application's scenes at 10 mm; `benchmarks/swatch_refinement.mjs`
solves it on 10, 5 and 2.5 mm cells in float64. Finer cells need finer steps:
a membrane's stiffness ratio grows as 1/h², a hinge's as 1/h⁴. Doubling the
step count at 5 mm moved no reading by more than 0.03%.

**Shear has no exact answer, and the 10 mm grid reads it low.** The strip is a
short cantilever loaded sideways, so it bends in its own plane as well as
shearing, and linear triangles are stiff in that mode. The mesh-converged value
is a Richardson extrapolation of the three readings (observed order 1.3 to 1.75):

| Fixture | 10 mm | 5 mm | 2.5 mm | Converged | Error at 10 mm | at 5 mm |
| --- | --- | --- | --- | --- | --- | --- |
| Polyester warp | 5.071 mm | 5.363 | 5.484 | 5.569 | −8.9% | −3.7% |
| Polyester weft | 5.835 | 6.219 | 6.359 | 6.440 | −9.4% | −3.4% |
| Voile warp | 7.686 | 8.249 | 8.431 | 8.518 | −9.8% | −3.2% |
| Voile weft | 19.505 | 21.530 | 22.130 | 22.384 | −12.9% | −3.8% |
| Cupro warp | 13.507 | 14.767 | 15.146 | 15.308 | −11.8% | −3.5% |
| Cupro weft | 9.706 | 10.476 | 10.711 | 10.813 | −10.2% | −3.1% |

How the cells are split does not matter here: the cupro's warp converges to
15.308, 15.323 and 15.311 mm for the checkerboard and the two uniform splits.
**Error budget:** the shear reading is 9 to 13% low, most for cloth that
stretches easily, on top of a step error under 0.1%. The dialog says so. It
ranks fabrics; it is not a measurement from which to read a shear stiffness.
A 5 mm grid would still read 3 to 4% low and no longer fits one workgroup.

**Bending has the elastica, and the 10 mm grid is as close as finer ones.**
With the 10 mm calibration held fixed:

| Fixture | Elastica | 10 mm | 5 mm | 2.5 mm |
| --- | --- | --- | --- | --- |
| Polyester warp | 66.39 mm | −0.4% | −0.7% | −0.6% |
| Polyester weft | 69.69 | −0.1% | −0.7% | −0.6% |
| Voile warp | 72.28 | +0.4% | −0.3% | −0.1% |
| Cupro warp | 72.87 | +0.6% | −0.4% | −0.4% |
| Cupro weft | 70.49 | +0.05% | −0.4% | −0.3% |
| Voile weft | 76.60 | +2.0% | +0.3% | −0.2% |

Only the limp voile gains from finer cells, which confirms that its 2% is the
tight curl at the clamp. The others drift slightly low because the grid factor
is not quite a constant: a small-deflection cantilever needs 2.431 at 10 mm,
2.483 at 5 mm and 2.466 at 3.3 mm. The clamp holds the first cells flat, which
stops the relaxation that gives 2.4 on paper, over a length set by the strip's
width rather than the cell. The calibration belongs to this grid: another mesh
needs its own small-deflection check.

The study also found two faults in the fixture itself, both now fixed:

- **The strip twisted.** Every cell was split along the same diagonal. That
  couples bending to twist (on paper a curvature κ along the strip induces a
  twist κ/5), so one corner of the free edge hung lower than the other: 1.2 mm
  for the voile's weft, 3.3 mm for the cupro's warp and 5.8 mm for the
  polyester's, across a 40 mm edge. Mirroring the split reversed the sign. A
  checkerboard of the two diagonals is mirror-symmetric about the strip and
  hangs level to 0.05 mm, with the same drop.
- **The across-strip rigidity leaked into the answer.** Diagonal hinges took
  the mean of the two rigidities, and they take part in how this grid bends. A
  small-deflection cantilever then behaved as if its rigidity were 2.17 to
  2.73 times the hinge value as the across/along ratio went from a quarter to
  four: an error of 11% either way in the rigidity under test, for fabrics
  whose two directions differ (the voile's by 4.5). With diagonals taking the
  rigidity along the strip the range is 2.40 to 2.47, under 2%.

This settles numerical behaviour only. It says nothing about whether a real
fabric follows a linear law, and no physical specimen has been compared. It does
mean a rigidity estimated from a supplier's loop test is no longer doubled by
the mesh before it is drawn.

## Validation

Desktop browser checks on the published Cupro sample, at the old fixed step:
25 N/m extension was 4.270% warp and 2.369% weft at 48 steps; 64 steps gave
4.256% and 2.421%. Linear predictions are 4.255% and 2.415%. With the sized
step a fabric with the stiff polyester's values reads 0.38% and 0.70% on the
GPU, its exact 0.380% and 0.702%. This verifies the implemented linear
model, not that the real fabric follows a linear law. Same-grain shear control
gave identical 13.472 mm displacements. Fixed pin error stayed below 0.00001 mm.
All GPU kernel checks passed, including damping and optimized/reference parity.
The comparison was also inspected at a 390 × 844 mobile viewport without
horizontal overflow. These are diagnostics, not portable golden values.
The interactive bend budget gave 71.118/66.145 mm tip drop, versus
70.994/65.989 mm with refinement, below 0.16 mm difference on this fixture.
Those figures predate the bending calibration and the checkerboard mesh. On the
current fixture the GPU reads the cupro at 73.29 / 70.53 mm drop, 4.25 / 2.41%
extension and 13.51 / 9.71 mm shear, each equal to the CPU reference.
Loaded tests prioritize numerical accuracy and can run slower than real time.

```powershell
python -m unittest test_fabrics test_browser_preview test_button_closures test_dress_shirt_collar -q
node --test benchmarks/test_swatch.mjs benchmarks/test_simulation_clock.mjs benchmarks/test_browser_drape.mjs benchmarks/test_collar_placement.mjs benchmarks/test_button_closures.mjs
node --test benchmarks/test_swatch_convergence.mjs    # about two minutes: exact answers, mesh symmetry, the shear budget
node benchmarks/swatch_reference.mjs --substeps=48 --iterations=32    # reproduce any row above
node benchmarks/swatch_refinement.mjs                 # the Mesh resolution tables, about 40 minutes; --mode=factor for the grid factor
```

`benchmarks/swatch_fixtures.json` holds the solver inputs of the application's
own scenes; `test_fabrics` fails if they drift from what the application builds,
and `python benchmarks/export_swatch_fixtures.py` regenerates them.

Tests cover synthetic elastica recovery with force tare, unit conversion and
provenance, unknown/zero handling, legacy normalization and intentional clears,
lossless original files, privacy and CAS updates, triangle energy area scaling,
direction swapping, applied-load quadrature and race-free batches.

References: [Browzwear Physics Reference](https://help.browzwear.com/en/articles/13065506-physics-reference),
[FAB raw measurement documentation](https://github.com/vizoogmbh/u3m/tree/master/u3m1.1/physics),
[Strain Based Dynamics](https://matthias-research.github.io/pages/publications/strainBasedDynamics.pdf),
[Discrete Shells](https://www.cs.columbia.edu/cg/pdfs/10_ds.pdf),
[Small Steps in Physics Simulation](https://matthias-research.github.io/pages/publications/smallsteps.pdf).
