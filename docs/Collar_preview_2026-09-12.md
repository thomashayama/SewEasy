# Dress-shirt collar browser regression

The collar now has functional pointed leaves, aligned roll-line endpoints,
matching mirrored seam orientation, and closed shoulder and center-back seams.
The front leaves are folded after the left half is mirrored; folding first let
automatic normal orientation reverse only the left leaf's stitch direction.

WebGPU preserves the signed angle at the collar roll line, instead of using an
opposite-vertex distance that cannot distinguish an inward fold from an outward
one. The hinge is active only when its seam endpoints are within 1.5 cm. Once
sewing finishes, collar seam junctions share their mass-weighted position and
motion history. This keeps multi-panel corners closed through body contact.
The collar remains free to move with the garment; it is not pinned to the body.

Collared shirts retain their drafted initial height. The old 6 cm lift could
assemble the collar around the jaw on a larger measurement profile.

## Reproduce

Use the existing CPU-only environment from `docs/Browser_preview.md`:

```powershell
tmp_webgpu_cpu/Scripts/python.exe -m unittest test_dress_shirt_collar test_body_fit test_browser_preview -q
node --test benchmarks/test_browser_drape.mjs benchmarks/test_camera.mjs benchmarks/test_collar_placement.mjs
tmp_webgpu_cpu/Scripts/python.exe benchmarks/prepare_webgpu.py
tmp_webgpu_cpu/Scripts/python.exe benchmarks/prepare_collar.py
python benchmarks/serve_webgpu.py
```

Open `http://127.0.0.1:8767/collar.html?scene=collar-default.json` and run
**1800 frames**, inspect Front/Back/Side, then **Save geometry**. Repeat with
`collar-fine.json` and `collar-custom.json`. The custom case is a synthetic 185 cm
profile with 120 cm bust and a 5 cm collar-point setting. It uses the same body
fitter as the studio. The fine case uses 1 cm triangles instead of 1.5 cm.

Analyze each saved capture using:

```powershell
tmp_webgpu_cpu/Scripts/python.exe benchmarks/analyze_collar.py output/webgpu/results/<capture>.json
```

The checker measures collar-only seam gaps, triangle stretch, signed fold error,
and exact-triangle mannequin distance at vertices, centroids and edge midpoints.
It rejects flipped-up tips, seams wider than 5 mm, or penetration deeper than
1 mm. GPU startup fixtures additionally verify signed fold recovery, delayed
hinge activation for separated panels, and mass-preserving junction closure.

## Recorded results

All three final cases ran for 1,800 frames (30 simulated seconds). Timings include
browser encoding, rendering and GPU completion, averaged over the run. The
studio displayed 60 fps with the default shirt and no browser errors.

| Case | Cloth vertices | Mean frame time | Max collar seam gap | Samples inside body | Fold error, 95th percentile |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default, 1.5 cm | 5,630 | 8.50 ms | 0 mm | 0 / 2,300 | 0.88° |
| Default, 1 cm | 12,322 | 11.79 ms | 0 mm | 0 / 5,311 | 3.24° |
| Custom, 1.5 cm | 7,532 | 10.79 ms | 0 mm | 0 / 2,810 | 0.41° |

Fourteen Python tests, eight Node tests and twelve browser GPU fixtures passed.
The [machine-readable results](../benchmarks/webgpu/results/2026-09-12-collar.json)
also retain the stretch measurements. Collar triangle stretch at the 95th
percentile was 7.7–10.5%; the most distorted individual triangle reached 57.4%
in the finer mesh. This remains a material-model limitation despite the stable
collar shape and closed stitches.

## Limits

This fixes collar construction and stability in the browser preview. Fabric is
still uncalibrated and local triangle stretch remains; a stable appearance does
not certify pattern fit or physical fabric accuracy. Body-contact sampling is
not a full triangle/self-intersection proof. The results concern the tested
desktop browser/GPU, not all mobile devices.
