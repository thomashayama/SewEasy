# Fabric sources and importer validation

Checked 2026-09-18. A fiber name is not a constitutive model: use a specific
construction, weight, finish and supplier article. These are candidates and
format checks, not a newly published standard-fabric catalog.

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
