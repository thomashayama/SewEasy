"""CPU fitting of the existing mannequin to a measurement profile.

This is a smooth, fixed-topology approximation, not reconstruction of a scan.
Lengths control anatomical landmarks; measured mesh sections control girths.
No learned body model, remote service or GPU dependency is involved.
"""
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import trimesh
import yaml

ROOT = Path(__file__).resolve().parents[2]
ANGLES = {'arm_pose_angle', 'shoulder_incl', 'hip_inclination'}
GIRTHS = ('hips', 'waist', 'underbust', 'bust')
FITTED = (*GIRTHS, 'height', 'head_l', 'waist_line', 'hips_line', 'vert_bust_line',
          'crotch_hip_diff', 'shoulder_w', 'shoulder_incl', 'neck_w',
          'arm_length', 'arm_pose_angle', 'wrist', 'leg_circ')


def section_rings(mesh, origin, normal=(0, 1, 0)):
    """Closed section components, keeping arms/legs separate from the torso."""
    segments = trimesh.intersections.mesh_plane(mesh, normal, origin)
    if not len(segments):
        raise ValueError('Body measurement plane misses the mannequin')
    _, ids = np.unique(np.round(segments.reshape(-1, 3), 6), axis=0, return_inverse=True)
    ids = ids.reshape(-1, 2)
    graph = coo_matrix((np.ones(len(ids)), (ids[:, 0], ids[:, 1])),
                       shape=(ids.max() + 1,) * 2)
    _, labels = connected_components(graph, directed=False)
    groups = labels[ids[:, 0]]
    return [segments[groups == g] for g in np.unique(groups)]


def perimeter(segments):
    return float(np.linalg.norm(segments[:, 1] - segments[:, 0], axis=1).sum())


def levels(m):
    nape = m['height'] - m['head_l']
    waist = nape - m['waist_line']
    bust = nape - m['vert_bust_line']
    hips = waist - m['hips_line']
    return dict(hips=hips, waist=waist, bust=bust,
                # The profile has no underbust height. Retain the template's
                # relative ribcage placement between waist and bust.
                underbust=waist + .52 * (bust - waist),
                crotch=hips - m['crotch_hip_diff'], nape=nape, top=m['height'])


def arm_frame(m, side):
    angle = np.deg2rad(m['arm_pose_angle'])
    joint = np.array([side * m['shoulder_w'] / 2,
        levels(m)['nape'] - np.tan(np.deg2rad(m['shoulder_incl'])) *
        (m['shoulder_w'] - m['neck_w']) / 2, 0.])
    return joint, np.array([side * np.sin(angle), -np.cos(angle), 0.]), \
        np.array([side * np.cos(angle), np.sin(angle), 0.])


def measure_mesh(mesh, m):
    """Independent section measurements on the final triangulated surface."""
    heights = levels(m)
    result = {'height': float(np.ptp(mesh.vertices[:, 1]))}
    for key in GIRTHS:
        rings = section_rings(mesh, [0, heights[key], 0])
        # At these levels the torso surrounds the centerline. Arms are separate.
        torso = [r for r in rings if r[:, :, 0].min() < 0 < r[:, :, 0].max()]
        if not torso:
            raise ValueError(f'Cannot measure the {key} section on this body')
        result[key] = perimeter(max(torso, key=perimeter))
    wrists, thighs = [], []
    for side in (-1, 1):
        joint, axis, _ = arm_frame(m, side)
        point = joint + m['arm_length'] * axis
        ring = min(section_rings(mesh, point, axis),
                   key=lambda r: np.linalg.norm(r.mean((0, 1)) - point))
        wrists.append(perimeter(ring))
        candidates = section_rings(mesh, [0, heights['crotch'] - .015, 0])
        ring = min(candidates, key=lambda r: abs(r.mean((0, 1))[0] - side * .1))
        thighs.append(perimeter(ring))
    result.update(wrist=float(np.mean(wrists)), leg_circ=float(np.mean(thighs)))
    return result


@lru_cache(maxsize=1)
def _template():
    mesh = trimesh.load(ROOT / 'assets/bodies/mean_all.obj', process=False)
    raw = yaml.safe_load((ROOT / 'assets/bodies/mean_all.yaml').read_text())['body']
    measurements = {k: float(v) if k in ANGLES else float(v) / 100
                    for k, v in raw.items()}
    groups = json.loads((ROOT / 'assets/bodies/ggg_body_segmentation.json').read_text())
    edges = mesh.edges_unique
    rows, cols = np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]]
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(mesh.vertices),) * 2).tocsr()
    degree = np.asarray(graph.sum(axis=1)).ravel()
    weights = {}
    for key in ('left_arm', 'right_arm', 'left_leg', 'right_leg'):
        w = np.zeros(len(mesh.vertices)); w[groups[key]] = 1
        # Blend across anatomical boundaries to avoid cracks or hard steps.
        for _ in range(16):
            w = .5 * w + .5 * (graph @ w) / np.maximum(degree, 1)
        weights[key] = w
    return mesh, measurements, weights, measure_mesh(mesh, measurements)


def _deform(mesh, base, target, weights, factors):
    v = mesh.vertices
    source, dest = levels(base), levels(target)
    names = ('crotch', 'hips', 'waist', 'underbust', 'bust', 'nape', 'top')
    ys = [0, *[source[k] for k in names]]
    yt = [0, *[dest[k] for k in names]]
    if np.any(np.diff(yt) <= .005):
        raise ValueError('These measurements put body landmarks out of order')
    out = v.copy()
    out[:, 1] = PchipInterpolator(ys, yt)(v[:, 1].clip(0, ys[-1]))
    # Circumference correction is radial at each anatomical ring. Shoulder and
    # neck width have their own controls above the bust; the head retains detail.
    upper_y = [source['bust'] + .55 * (source['nape'] - source['bust']), source['nape'], source['top']]
    widths = [factors[k] for k in GIRTHS]
    sy = [0, source['hips'], source['waist'], source['underbust'], source['bust'], *upper_y]
    sx = [factors['hips'], *widths, target['shoulder_w']/base['shoulder_w'],
          target['neck_w']/base['neck_w'], target['head_l']/base['head_l']]
    sz = [factors['hips'], *widths, np.sqrt(factors['bust']),
          target['neck_w']/base['neck_w'], target['head_l']/base['head_l']]
    out[:, 0] *= PchipInterpolator(sy, sx)(v[:, 1].clip(0, sy[-1]))
    out[:, 2] *= PchipInterpolator(sy, sz)(v[:, 1].clip(0, sy[-1]))
    torso = out.copy()
    for side, name in ((1, 'left'), (-1, 'right')):
        joint, axis, across = arm_frame(base, side)
        new_joint, new_axis, new_across = arm_frame(target, side)
        relative = v - joint
        along = relative @ axis
        radial = np.interp(along, [0, base['arm_length'] * .55, base['arm_length']],
                           [np.sqrt(factors['bust']), np.sqrt(factors['wrist']), factors['wrist']])
        new_along = np.minimum(along, base['arm_length']) * target['arm_length']/base['arm_length'] \
            + np.maximum(0, along - base['arm_length']) * np.sqrt(factors['wrist'])
        arm = new_joint + new_along[:, None] * new_axis \
            + ((relative @ across) * radial)[:, None] * new_across
        arm[:, 2] += relative[:, 2] * radial
        out += weights[f'{name}_arm'][:, None] * (arm - torso)
        leg = torso.copy()
        radial = np.interp(v[:, 1], [0, .2, source['crotch'] - .015, source['hips'] + .08],
                           [np.sqrt(target['height']/base['height']), np.sqrt(factors['leg_circ']),
                            factors['leg_circ'], factors['hips']])
        center = side * .1
        leg[:, 0] = center * factors['hips'] + (v[:, 0] - center) * radial
        leg[:, 2] = v[:, 2] * radial
        out += weights[f'{name}_leg'][:, None] * (leg - torso)
    return trimesh.Trimesh(out, mesh.faces.copy(), process=False)


@lru_cache(maxsize=8)
def _fit_cached(key):
    mesh, base, weights, measured = _template()
    raw = dict(key)
    target = {k: v if k in ANGLES else v / 100 for k, v in raw.items()}
    same = all(abs(target[k] - base[k]) < 1e-7 for k in FITTED)
    factors = {k: target[k] / measured[k] for k in (*GIRTHS, 'wrist', 'leg_circ')}
    fitted = mesh.copy()
    if not same:
        for _ in range(6):
            fitted = _deform(mesh, base, target, weights, factors)
            actual = measure_mesh(fitted, target)
            if max(abs(actual[k] - target[k]) for k in factors) < .003:
                break
            for k in factors:
                factors[k] *= target[k] / actual[k]
    actual = measure_mesh(fitted, target)
    errors = {k: abs(actual[k] - target[k]) * 100 for k in actual}
    if not np.isfinite(fitted.vertices).all() or fitted.area_faces.min() < 1e-12 or fitted.volume <= 0:
        raise ValueError('These measurements could not produce a valid preview body')
    if not same and max(errors.values()) > 1:
        raise ValueError('Body fitting could not match this profile within 1 cm. Check the measurements.')
    report = dict(kind='default' if same else 'custom',
        measurements={k: dict(target_cm=round(target[k]*100, 2), actual_cm=round(actual[k]*100, 2),
                             error_cm=round(errors[k], 3)) for k in actual},
        max_error_cm=round(max(errors.values()), 3),
        fitted_parameters=list(FITTED),
        approximated_parameters=[k for k in raw if k not in FITTED],
        note='Default mannequin' if same else 'Measurement-fitted mannequin · approximate body shape')
    return fitted.vertices.copy(), fitted.faces.copy(), report


def fit_body(measurements):
    """Return a private mesh + measured fit report; cache only deterministic CPU work."""
    _, base, _, _ = _template()
    values = {k: float(measurements.get(k, v if k in ANGLES else v*100))
              for k, v in base.items()}
    if not all(np.isfinite(v) and (k in ANGLES or v > 0) for k, v in values.items()):
        raise ValueError('Body measurements must be finite positive numbers')
    if not np.isfinite(values['arm_pose_angle']) or not 0 <= values['arm_pose_angle'] <= 90:
        raise ValueError('Arm pose angle must be between 0 and 90 degrees')
    vertices, faces, report = _fit_cached(tuple(sorted(values.items())))
    return trimesh.Trimesh(vertices.copy(), faces.copy(), process=False), json.loads(json.dumps(report))
