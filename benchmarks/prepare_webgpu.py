"""CPU-only export of SewEasy panel meshes and a mannequin BVH for WebGPU.

No simulated drape, Warp, Newton, or CUDA is used. Input mesh.npz files come
from prepare_cloth.py, which drafts and triangulates the original patterns.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def package(mesh, destination):
    from seweasy.meshgen.webgpu import build_scene
    with np.load(mesh) as archive:
        # Materialize compressed arrays once; build_scene indexes them repeatedly.
        data = {key: archive[key] for key in archive.files}
        meta = json.loads((mesh.parent / 'prepare.json').read_text())
        scene = build_scene(data, meta, mesh.parent.name)
    target = destination / f'{mesh.parent.name}.json'
    target.write_text(json.dumps(scene, separators=(',', ':')))
    print(f'{target.name}: {len(scene["vertices"])} vertices, {len(scene["faces"])} triangles')
    return dict(name=scene['name'], label=f"{meta['garment']} · {meta['resolution_cm']:g} cm", path=target.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--meshes', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/webgpu')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    meshes = args.meshes or [ROOT / f'output/simulator-benchmark/{name}/mesh.npz' for name in
                            ['t-shirt_1.5cm', 'element-top_1.5cm', 'dress-shirt_1.5cm', 't-shirt_1cm', 'dress-shirt_1cm']]
    manifest = [package(mesh, args.output) for mesh in meshes]
    (args.output / 'manifest.json').write_text(json.dumps(manifest))
    for source in (ROOT / 'benchmarks/webgpu').iterdir():
        if source.is_file():
            shutil.copyfile(source, args.output / source.name)

    for source in (ROOT / 'gui/webgpu').glob('*.js'):
        shutil.copyfile(source, args.output / source.name)
