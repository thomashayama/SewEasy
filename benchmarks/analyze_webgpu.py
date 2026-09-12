"""CPU-only offline quality/export checks for browser-generated positions."""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/webgpu'


def analyze(path):
    capture = json.loads(path.read_text())
    report, vertices = capture['report'], np.asarray(capture['positions'])
    scene = json.loads((OUTPUT / f"{report['scene']}.json").read_text())
    faces, uv = np.asarray(scene['faces']), np.asarray(scene['uv'])
    uv[:, 0] *= report['settings']['width']
    assert vertices.shape == (report['vertices'], 3) and np.isfinite(vertices).all()
    rest, world = uv[faces], vertices[faces]
    dm = np.stack([rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]], axis=-1)
    ds = np.stack([world[:, 1] - world[:, 0], world[:, 2] - world[:, 0]], axis=-1)
    singular = np.linalg.svd(ds @ np.linalg.inv(dm), compute_uv=False)
    body = trimesh.Trimesh(scene['body_vertices'], scene['body_faces'], process=False)
    inside = np.concatenate([body.contains(chunk) for chunk in np.array_split(vertices, 30)])
    depths = []
    if inside.any():
        for chunk in np.array_split(vertices[inside], max(1, int(inside.sum()) // 50)):
            depths.extend(trimesh.proximity.closest_point(body, chunk)[1].tolist())
    metrics = dict(body_inside_vertices=int(inside.sum()), body_penetration_max_mm=max(depths, default=0)*1000,
                   triangle_stretch_p95=float(np.percentile(singular[:, 0], 95)),
                   triangle_stretch_max=float(singular[:, 0].max()),
                   body_watertight=bool(body.is_watertight),
                   note='Vertex containment only; triangle-level body and self-intersection counts not measured')
    cloth = trimesh.Trimesh(vertices, faces, process=False)
    cloth.visual.vertex_colors = [67, 124, 169, 255]
    body.visual.vertex_colors = [195, 179, 165, 255]
    glb = path.with_suffix('.glb')
    trimesh.Scene({'garment': cloth, 'body': body}).export(glb)
    reloaded = trimesh.load(glb, force='scene', process=False)
    assert sum(len(g.faces) for g in reloaded.geometry.values()) == len(faces) + len(body.faces)
    report['offline_quality'] = metrics
    report['artifact_validation'] = 'Finite positions, vertex/triangle counts, GLB export and reload passed'
    dest = path.with_suffix('.analysis.json')
    dest.write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(file=path.name, scene=report['scene'], fps=report['updates_per_second'],
                          gpu_ms=report['gpu_physics_ms_median'], **metrics)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='*', type=Path)
    args = parser.parse_args()
    paths = args.results or [p for p in sorted((OUTPUT / 'results').glob('*.json'))
                             if not p.name.endswith('.analysis.json')]
    for path in paths:
        analyze(path)
