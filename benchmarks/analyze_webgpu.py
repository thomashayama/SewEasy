"""CPU-only offline quality/export checks for browser-generated positions."""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
import igl

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/webgpu'


def analyze(path, surface=False):
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
    if 'triangle_stretch_p95' in report['quality']:
        assert np.isclose(np.percentile(singular[:, 0], 95), report['quality']['triangle_stretch_p95'], atol=5e-6)
        assert np.isclose(singular[:, 0].max(), report['quality']['triangle_stretch_max'], atol=5e-6)
    body = trimesh.Trimesh(scene['body_vertices'], scene['body_faces'], process=False)
    assert body.is_watertight and body.volume > 0, 'Signed-distance validation requires an outward, closed body'
    points = vertices
    if surface:
        samples = np.concatenate([(world[:, 0]+world[:, 1])*.5, (world[:, 0]+world[:, 2])*.5,
                                  (world[:, 1]+world[:, 2])*.5, world.mean(axis=1)])
        points = np.concatenate([vertices, samples])
    # C++ triangle-distance queries avoid materializing enormous Python ray/
    # triangle candidate arrays. Cross-check the sign independently with ray
    # parity at every negative sample, the 64 nearest points and 128 spread out.
    distance = igl.signed_distance(points, np.asarray(body.vertices), np.asarray(body.faces),
                                   igl.SIGNED_DISTANCE_TYPE_PSEUDONORMAL)[0]
    checks = np.unique(np.concatenate([np.flatnonzero(distance < -1e-7),
                                       np.argsort(np.abs(distance))[:64],
                                       np.linspace(0, len(points)-1, min(128, len(points))).astype(int)]))
    checks = checks[np.abs(distance[checks]) > 1e-6]
    ray_inside = np.concatenate([body.contains(chunk) for chunk in np.array_split(points[checks], max(1, len(checks)//400))])
    assert np.array_equal(ray_inside, distance[checks] < 0), 'Body sign disagrees with independent ray parity'
    inside = distance[:len(vertices)] < -1e-7
    depths = -distance[:len(vertices)][inside]
    metrics = dict(body_inside_vertices=int(inside.sum()), body_penetration_max_mm=max(depths, default=0)*1000,
                   triangle_stretch_p95=float(np.percentile(singular[:, 0], 95)),
                   triangle_stretch_max=float(singular[:, 0].max()),
                   body_watertight=bool(body.is_watertight), ray_parity_cross_checks=len(checks),
                   containment_method='CPU libigl triangle distance/pseudonormal sign, cross-checked with trimesh ray parity',
                   containment_tolerance_m=1e-7,
                   note='Vertex containment only; triangle-level body and self-intersection counts not measured')
    if surface:
        sample_inside = distance[len(vertices):] < -1e-7
        metrics.update(body_surface_samples=len(samples), body_inside_surface_samples=int(sample_inside.sum()),
                       note='Exact-body containment at vertices, three edge midpoints and each triangle centroid; not a full intersection or self-contact proof')
    cloth = trimesh.Trimesh(vertices, faces, process=False)
    cloth.visual.vertex_colors = [67, 124, 169, 255]
    body.visual.vertex_colors = [195, 179, 165, 255]
    glb = path.with_suffix('.glb')
    trimesh.Scene({'garment': cloth, 'body': body}).export(glb)
    reloaded = trimesh.load(glb, force='scene', process=False)
    assert sum(len(g.faces) for g in reloaded.geometry.values()) == len(faces) + len(body.faces)
    assert sum(len(g.vertices) for g in reloaded.geometry.values()) == len(vertices) + len(body.vertices)
    assert all(np.isfinite(g.vertices).all() for g in reloaded.geometry.values())
    report['offline_quality'] = metrics
    report['artifact_validation'] = 'Finite positions, vertex/triangle counts, GLB export and reload passed'
    dest = path.with_suffix('.analysis.json')
    dest.write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(file=path.name, scene=report['scene'], fps=report['updates_per_second'],
                          gpu_ms=report['gpu_physics_ms_median'], **metrics)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='*', type=Path)
    parser.add_argument('--surface', action='store_true', help='Also check edge midpoints and triangle centroids against the body')
    args = parser.parse_args()
    paths = args.results or [p for p in sorted((OUTPUT / 'results').glob('*.json'))
                             if not p.name.endswith('.analysis.json')]
    for path in paths:
        analyze(path, args.surface)
