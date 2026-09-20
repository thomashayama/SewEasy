# Fabric sources and importer validation

Checked 2026-09-18. A fiber name is not a constitutive model: use a specific
construction, weight, finish and supplier article. These are candidates and
format checks, not a newly published standard-fabric catalog.

## Shipped common collection (2026-09-19)

Account → Fabrics → Common fabrics contains 12 offline templates. Nine are
explicit SewEasy estimates: lightweight cotton poplin, polyester plain weave,
silk satin, polyester chiffon, wool suiting, cotton denim, cotton canvas,
cotton jersey and cotton/elastane stretch jersey. Their numbers are starting
points, not measured representative averages for a fiber class.

Three include openly published measurements, licensed CC BY 4.0:

| Template | Published properties | Source |
| --- | --- | --- |
| Cotton twill, 3/1 Z | Reported 184 g/m²; thickness 0.59 mm; warp/weft bending 23.33/4.3 μN·m | [Akter et al. 2024](https://doi.org/10.1002/pls2.10141), abstract and sections 3.3/3.7; [license record](https://research.aalto.fi/en/publications/effect-of-cotton-polyester-composite-yarn-on-the-physico-mechanic/) |
| Linen plain weave, FLAX PLAIN | 199.7 g/m² (SD 1.7); 0.51 mm (SD 0.01) | [Vasile et al. 2024](https://doi.org/10.3390/ma17071650), Tables 1–2 |
| Cotton/polyester/elastane stretch twill, M1 | 226.58 g/m²; 0.52 mm; KES bending 0.356/0.093 cN·cm | [Mahnić Naglić et al. 2025](https://doi.org/10.3390/polym17152013), Tables 1–2 |

These are transcribed data, not supplier U3M packages. Cotton's abstract and
section 3.1 disagree on weight (184 versus 208 g/m²); the collection retains
184 as **reported** with this discrepancy disclosed. The M1 paper's CLO
bending column differs tenfold from direct SI conversion of its KES column;
we use KES cN·cm × 1e-4 = N·m and disclose the discrepancy. No CLO solver
coefficients, breaking strength or Schlenker bending force are treated as
normalized membrane/bending stiffness. Linen bending, every template's stretch
and shear, and the nine unmeasured presets are explicitly estimated. Friction
and damping stay unknown; the preview labels its damping fallback.

`webapp/fabric_catalog.json` records sample identity, composition, construction,
authors, source links, licenses, conversions and per-property provenance.
Templates have stable IDs and no database seed writes. Saving a copy freezes
all content into the user's own record. Refreshing the collection cannot alter
copies or snapshots. U3MA preserves attribution in `custom.seweasy.catalog`,
property sources, and a readable `seweasy-fabric-sources.txt` companion. Source
companions are never replaced on re-export. No third-party textures or paper
images are bundled. The legacy studio presets retain their existing behavior.

Validate with `python -m unittest test_fabric_catalog test_fabrics -q`.
Catalog inputs exercise the browser swatches only; physical calibration,
favorites and garment assignment remain separate work.

Browser checks: chiffon tip drop 78.24/78.97 mm, canvas 50.18/56.19 mm,
and the published cotton twill 68.60/77.94 mm (warp/weft). All 22 GPU checks
passed per canvas; fixed-pin error stayed below 0.00001 mm. These compare
implemented inputs, not real specimens. Named copy/edit/reopen and rapid
search/tab switching were exercised; the latter revealed and fixed stale
async list renders. The collection was checked at a 390 px viewport.

## Common-fabric candidates

| Fabric | Weight | Source and availability | What was verified |
| --- | --- | --- | --- |
| 100% cotton voile, STYLEM 02600035000 | 92 g/m² | [Product](https://jp.stylemfabrics.com/products/02600035000), [free quality-evaluation sample](https://us.stylemfabrics.com/pages/degitalfabric) | Full U3MA import/export passed; 102 raw test branches. Warp bending flagged low-force; only weft bending estimated. Supplier description identifies cotton, but package composition is the placeholder `TEST`, so do not infer composition from its JSON. Resin finish makes this a particular crisp voile, not generic cotton. |
| Polyester ECO dobby check, STYLEM 016S0070148 | 79 g/m² listed; 79.2 imported | [Product](https://jp.stylemfabrics.com/products/016s0070148), same free-sample page | Full U3MA import/export passed; 102 raw branches and both bending fits. Supplier describes recycled polyester; exact fiber percentage is absent from the downloaded package and was not confirmed. |
| 100% linen Oxford, STYLEM 016S0070111 | 156 g/m² | [Product](https://us.stylemfabrics.com/products/016s0070111) | Listed digital fabric; account/purchase required. No file obtained or simulation claimed. Physical fabric is listed discontinued. |
| 100% linen plain weave, STYLEM 016S0070099 | Not confirmed | [Product](https://jp.stylemfabrics.com/products/016s0070099) | Supplier describes French-origin linen. Digital purchase requires an account; no file obtained. |
| 100% recycled polyester single jersey, Hung's Fortune HFI-REP-020-3LL | 152 g/m² | [PERFORMANCE DAYS product](https://www.performancedays.com/loop/marketplace/product-detail/63156.html), [3D collection](https://www.performancedays.com/loop/trends-forum/3d-forum.html) | Composition/weight listed in collection; anonymous product page did not expose its U3MA download. Not import-tested. |
| 100% organic cotton, Ventile Dry 110 org | 110 g/m² | [PERFORMANCE DAYS product](https://www.performancedays.com/loop/marketplace/product-detail/22073.html), same 3D collection | Lighter woven-cotton candidate; no anonymous U3MA link obtained. Not import-tested. |

STYLEM samples are offered for evaluating their digital-fabric quality. Its
[license terms](https://us.stylemfabrics.com/pages/terms-of-service) prohibit
transfer, sublicensing and redistribution of licensed content to third parties.
Keep these evaluation downloads in ignored local files; do not seed them into
SewEasy's public library without appropriate supplier permission. Other vendor
assets need their own redistribution review. No account was created or purchase made.

## Repeatable checks

Two upstream BSD-licensed FAB datasets are committed under `webapp/u3m_spec`:
Cupro and the cotton-knit QA fixture Shirley. Tests create minimal SewEasy
wrappers around the original measurement JSON; they are not vendor-exported
complete materials. `python -m unittest test_fabrics -q` covers both plus quality
warnings, axis-specific exclusions, old-record upgrades, user overrides,
intentional clears, units, unsupported fields and raw source preservation.

Five complete third-party packages were downloaded separately and passed
`benchmarks.validate_fabric_packages`: original companion bytes, vendor
extensions, appearance references, normalized properties/provenance and curves
survive export/reimport. Vendor textures and measurements are not redistributed
in this repository. The checker has no network access and accepts local paths:

```powershell
python -m benchmarks.validate_fabric_packages path/to/material.u3ma path/to/another.zip
```

| Package | Bytes | Preserved companions | Physics result |
| --- | ---: | ---: | --- |
| [Vizoo JerseyJaquard](https://www.u3m.info/wp-content/uploads/2019/03/0004_JerseyJaquard-1.zip) | 12933297 | 9 | Appearance only; every physical property remains unknown |
| [Vizoo Houndstooth](https://www.u3m.info/wp-content/uploads/2019/03/0005_Houndstooth-1.zip) | 6772408 | 9 | Appearance only; every physical property remains unknown |
| [Vizoo BigKnitJaquard](https://www.u3m.info/wp-content/uploads/2019/03/0006_BigKnitJaquard-1.zip) | 20833668 | 9 | Appearance only; every physical property remains unknown |
| [STYLEM cotton voile sample](https://cdn.shopify.com/s/files/1/0565/1303/6403/files/02600035000_110_sample.u3ma?v=1675157285) | 12008713 | 10 | 92 g/m²; 0.199384 mm; stretch 1674.790/338.036 N/m; warp bending unknown, weft estimate 2.231e-6 N·m |
| [STYLEM dobby check sample](https://cdn.shopify.com/s/files/1/0565/1303/6403/files/016S0070148_750_Shopify.u3ma?v=1674452927) | 17465853 | 18 | 79.2 g/m²; 0.201055 mm; stretch 6571.345/3560.165 N/m; bending estimates 1.989e-5/1.357e-5 N·m |

SHA-256 hashes, in table order:

```text
51a042ec26ce48f715cf358fa57943a0cb39a0646dabbb1cecd41f28bf673f40
ed1ef10ff35a3d20487fb9ec47cfd03e5eeb88558090f02b7467e10e09e0df1d
a96d951b0dae8a48c14ca74d4ff5294c4c6167b287961b54dd623d1c9d8bd9b6
6271a1e1845c7fdc88f2571f9bbeae2f1defd0411394838a9407f8093d63f452
074915a6095d169033a41a16a99c6c5a0647f4fa964ea32641de9cab3367eba4
```

The downloaded dobby material uses color suffix 750, but its embedded physics
name ends 500. Preserve this provenance mismatch; do not claim color-specific
physical validation. Mass agrees with the product's rounded published GSM.

## Appearance of the common collection

The twelve templates carry no scanned textures: none of the public measurement
sources publishes redistributable maps, and no third-party image was copied.
Each has a `display_color` chosen by SewEasy as the undyed or most familiar
shade of that cloth (ecru linen, indigo denim, charcoal suiting, and so on).
It labels the preview tile and tints pieces cut from the template, which stay
recolourable. It is presentation only: no property cites it, it is not derived
from any sample, and catalog revision 2 added it without touching a measured or
estimated value. A garment already cut from a template keeps its earlier copy
and is offered **Apply current fabric**.

## Simulation scope

Import success does not establish real-world accuracy. The same CPU-side
normalization feeds private, browser-only WebGPU swatches. Cotton warnings are
visible in the editor and preview, with missing warp bending explicitly assumed.
The cotton gravity test settled at 70.13/77.85 mm tip drop; stretch at 25 N/m
gave 1.401/7.409% (linear strip predictions 1.493/7.396%). These are numerical
diagnostics, not measurements of a sewn garment. Polyester settled at
57.37/63.85 mm drop and 0.526/0.740% extension, versus linear strip predictions
0.380/0.702%. The 0.146 percentage-point warp error is significant relative to
that small extension; passing GPU kernel tests does not establish solver
convergence for stiff materials. Track this in the calibration follow-up.
All 22 GPU checks per canvas
passed and pin error was below 0.00001 mm. Physical specimen calibration,
mesh convergence, nonlinear curves and assignment to garment pieces remain
separate work; see [FabricSwatch.md](FabricSwatch.md).
