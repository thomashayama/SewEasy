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
    vertices = np.asarray(box.vertices, dtype=np.float64) * 0.01
    faces = np.asarray(box.faces, dtype=np.int32)
    uv = np.asarray(box.vertex_texture, dtype=np.float64) * 0.01
    uv_faces = np.asarray(box.faces_with_texture, dtype=np.int32)[:, [1, 3, 5]]
    rest = uv[uv_faces]
    dm = np.stack([rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]], axis=-1)
    if np.any(np.abs(np.linalg.det(dm)) < 1e-12):
        raise ValueError('Degenerate 2D rest triangle')
    body_mesh = trimesh.load(ROOT / 'assets/bodies/mean_all.obj', process=False)
    # Both original body and pattern positions share the same origin.
    # Apply the original draper's ground shift, after converting to metres.
    body_v = np.array(body_mesh.vertices)
    shift = max(0.0, -body_v[:, 1].min())
    body_v[:, 1] += shift
    vertices[:, 1] += shift
    # Face ownership is needed for per-panel stiffness and garment diagnostics.
    texture_panel = []
    unsewn = []
    for panel_name in box.panelNames:
        texture_panel.extend([panel_name] * len(box.panels[panel_name].panel_vertices))
        panel = box.panels[panel_name]
        unsewn.extend(panel.rot_trans_panel(panel.panel_vertices))
    face_panels = np.asarray(texture_panel)[uv_faces[:, 0]]
    # Newton's panel helper requires positive 2D winding. Reflect the local
    # x axis of reversed panels, leaving the world-space surface unchanged.
    for panel_name in box.panelNames:
        ids = np.flatnonzero(face_panels == panel_name)
        signed = np.linalg.det(dm[ids])
        if np.all(signed < 0):
            uv[np.unique(uv_faces[ids]), 0] *= -1
        elif not np.all(signed > 0):
            raise ValueError(f'Inconsistent rest winding in {panel_name}')
    np.savez_compressed(directory / 'mesh.npz', vertices=vertices, faces=faces,
                        uv=uv, uv_faces=uv_faces, body_vertices=body_v,
                        body_faces=np.asarray(body_mesh.faces, dtype=np.int32),
                        face_panels=face_panels,
                        unsewn_vertices=np.asarray(unsewn) * 0.01 + [0, shift, 0])
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
