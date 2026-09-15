# Trouser drape regression

Trouser leg panels now account for the fitted waistband's depth in their rise.
The initial placement has no extra vertical gap below the band. In the browser,
the waist and each leg are arranged around the corresponding mannequin section
before sewing; the material UVs, pattern outlines and sewing connections stay
unchanged. Stitch closure starts from these arranged positions, rather than
the old flat-panel distances. No fitting pins or precomputed drape are used.

The waistband uses maximum-distance constraints spanning several mesh edges to
propagate tension, coupled with its triangle strain, seams and body contact.
This prevents the band stretching down over the hips and opening its attachment
seam under the weight of long trousers. The library preset has a moderate taper;
existing saved flare and length settings are preserved.

Generate the default, wide-leg, short, synthetic larger-body and shirt/trouser
outfit scenes, then run the regression checks:

```powershell
python benchmarks/prepare_trousers.py
python -m unittest test_trousers test_thumbnails -q
node --test benchmarks/test_trousers.mjs
python benchmarks/serve_webgpu.py --port 8767
```

In the browser harness choose each `trousers-*` scene, run **Measure 300 frames**,
and inspect the front, side and back. Use **Save result & geometry** to archive
the actual GPU positions and diagnostics in `output/webgpu/results/`.

The September 14, 2026 browser checks covered all five cases. The original
trousers dragged at ground level and had a 5.3 mm 95th-percentile seam gap.
The corrected default drape had hems about 4 cm above ground and a seam-gap
95th percentile below 0.001 mm; the worst local gap was 8.1 mm. The larger-body
case also stayed above ground, and the shorts and layered outfit remained
assembled. All checks had finite geometry and no reported GPU errors.
Simulation remains approximate: the default 95th-percentile triangle stretch
was 8.8%, above the solver's 2% target, despite the improved waistband behavior.

Thumbnail cache version 2 invalidates earlier drapes. All six standard library
images were regenerated in the browser; saved garments/outfits refresh through
the same queue on Home. See [thumbnail regeneration](Thumbnail_renders.md).
