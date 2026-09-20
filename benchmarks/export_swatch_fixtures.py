"""Write the solver inputs of the loaded swatch fixtures for benchmarks/swatch_reference.mjs.

Only what the solver reads is kept, so the file stays small and reviewable.
test_fabrics checks the committed fixtures still equal what the application
builds, so the JavaScript reference is always studying the real scenes.

    python benchmarks/export_swatch_fixtures.py [output.json]
"""
import json
from pathlib import Path
import sys

# weight g/m2, stretch warp/weft N/m, bending warp/weft N*m (None: the swatch's stated assumption).
# Polyester and voile are the STYLEM evaluation samples in docs/FabricSources.md; cupro is published.
SAMPLES = {
    'polyester dobby': (79.2, 6571.345, 3560.165, 1.989e-5, 1.357e-5),
    'cotton voile': (92., 1674.790, 338.036, None, 2.231e-6),
    'cupro': (105.6, 587.5116, 1035.2515, 1.0022226e-5, 1.6023748e-5),
}
KEYS = ('vertices', 'inverse_mass', 'membranes', 'membrane_batches', 'interior_hinges',
        'interior_hinge_batches', 'external_forces', 'swatch', 'fabric_test')


def scene(sample, direction, mode):
    from webapp.fabric_formats import properties
    from webapp.fabric_swatch import apply_material, swatch_scene
    weight, warp, weft, bend_warp, bend_weft = SAMPLES[sample]
    values = properties()
    for key, value in dict(weight=weight, stretch_warp=warp, stretch_weft=weft,
                           bend_warp=bend_warp, bend_weft=bend_weft).items():
        if value is not None:
            values[key].update(value=value, origin='reported')
    built = apply_material(swatch_scene(), values, direction, mode)
    result = {key: built[key] for key in KEYS}
    result['interior_hinges'] = [dict(ids=h['ids'], angle=h['angle'], compliance=h['compliance'])
                                 for h in built['interior_hinges']]
    return result


def fixtures():
    return {f'{sample} / {direction} / {mode}': scene(sample, direction, mode)
            for sample in SAMPLES for direction in ('warp', 'weft') for mode in ('stretch', 'shear', 'bend')}


if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name('swatch_fixtures.json'))
    target.write_text(json.dumps(fixtures(), separators=(',', ':')), encoding='utf-8')
    print(target, target.stat().st_size, 'bytes')
