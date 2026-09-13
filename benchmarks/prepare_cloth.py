"""Draft real SewEasy garments into solver-neutral meshes, in metres.

Run from the repository root with the isolated benchmark environment.
Panel coordinates are retained separately from welded 3D positions: the
assembled mesh is NOT the fabric rest shape. No patched Warp is imported.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assets.bodies.body_params import BodyParameters
from assets.garment_programs.meta_garment import MetaGarment
from seweasy.meshgen.boxmeshgen import BoxMesh
from seweasy.pattern.core import BasicPattern


def prepare(name, resolution, output):
    directory = output / f'{name}_{resolution:g}cm'
    directory.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    body = BodyParameters(str(ROOT / 'assets/bodies/mean_all.yaml'))
    design = yaml.safe_load((ROOT / f'assets/design_params/{name}.yaml').read_text())['design']
    garment = MetaGarment(name, body, design)
    pattern = garment.assembly()
    BasicPattern.serialize(pattern, str(directory), to_subfolder=False)
    pattern.get_svg(directory / 'pattern.svg', with_text=False, view_ids=False).save()
    body.save(directory)
    draft_s = time.perf_counter() - start
    start = time.perf_counter()
    box = BoxMesh(directory / f'{name}_specification.json', resolution)
    box.load()
    mesh_s = time.perf_counter() - start
    from seweasy.meshgen.webgpu import panel_mesh_data
    data = panel_mesh_data(box, trimesh.load(ROOT / 'assets/bodies/mean_all.obj', process=False))
    np.savez_compressed(directory / 'mesh.npz', **data)
    vertices, faces = data['vertices'], data['faces']
    initial = trimesh.Trimesh(vertices, faces, process=False)
    initial.export(directory / 'initial.obj')
    metadata = dict(garment=name, resolution_cm=resolution, vertices=len(vertices),
                    triangles=len(faces), panels=len(box.panelNames), draft_s=draft_s,
                    mesh_s=mesh_s, units='metres', body='mean_all',
                    sewn_topology='shared seam vertices (SewEasy BoxMesh)',
                    topology_fixed=True,
                    panel_stiffness={n: pattern.pattern.get('panel_stiffness', {}).get(n, 1.0)
                                     for n in box.panelNames})
    (directory / 'prepare.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata), flush=True)
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--garments', nargs='+', default=['t-shirt', 'dress-shirt', 'element-top'])
    parser.add_argument('--resolution', type=float, default=1.5)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/simulator-benchmark')
    args = parser.parse_args()
    for name in args.garments:
        prepare(name, args.resolution, args.output)
