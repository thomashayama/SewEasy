"""Small physical test fixtures; geometry on CPU, simulation only in WebGPU."""
from functools import lru_cache

import numpy as np
import trimesh

from seweasy.meshgen.webgpu import build_scene


def colored(items, vertex_count, ids):
    used, colors = [set() for _ in range(vertex_count)], []
    for item in items:
        vertices = ids(item)
        forbidden = set().union(*(used[i] for i in vertices))
        color = 0
        while color in forbidden:
            color += 1
        while len(colors) <= color:
            colors.append([])
        colors[color].append(item)
        for i in vertices:
            used[i].add(color)
    ordered, batches = [], []
    for group in colors:
        batches.append([len(ordered), len(group)])
        ordered.extend(group)
    return ordered, batches


@lru_cache(maxsize=1)
def swatch_scene():
    # 80 mm overhang, 40 mm width, two rows locked inside the clamp.
    columns, rows, step, width, height = 10, 5, .01, .04, .12
    uv = np.array([[(x-1)*step, z*width/(rows-1)] for x in range(columns) for z in range(rows)])
    points = np.array([[x, height, z-width/2] for x, z in uv])
    faces = []
    for x in range(columns-1):
        for z in range(rows-1):
            a, b, c, d = x*rows+z, (x+1)*rows+z, x*rows+z+1, (x+1)*rows+z+1
            faces.extend(([a, c, b], [c, d, b]))
    faces = np.array(faces)
    # Visible clamp only; collision is deliberately off in this isolated test.
    clamp = trimesh.creation.box(extents=[.024, .006, .05])
    clamp.apply_translation([-.007, height, 0])
    scene = build_scene(dict(unsewn_vertices=points, uv=uv, uv_faces=faces, faces=faces,
                             face_panels=['swatch']*len(faces),
                             body_vertices=clamp.vertices, body_faces=clamp.faces),
                        dict(garment='fabric-swatch', resolution_cm=1., panel_stiffness={}, panels=1),
                        'clamped-fabric-swatch')
    # Retain the area-derived physical masses, including the part in the clamp.
    # Zero inverse mass means fixed, not a particle with zero physical mass.
    scene['vertex_mass_kg'] = [1/w for w in scene['inverse_mass']]
    pins = list(range(2*rows))
    for i in pins:
        scene['inverse_mass'][i] = 0
    scene['constraints'], scene['batches'] = colored(
        [c for c in scene['constraints'] if c[2] == 0], len(points), lambda c: c[:2])
    edges = {}
    for a, b, c in faces.tolist():
        for u, v, opposite in ((a, b, c), (b, c, a), (c, a, b)):
            edges.setdefault(tuple(sorted((u, v))), []).append((u, v, opposite))
    # Discrete-shell geometry factor l/h, h = (A0+A1)/(3*l).
    # E = D/2 * (l/h) * theta^2; XPBD compliance = 1/(D*l/h).
    # Base rigidity is replaced by apply_material before a preview is served.
    # Grinspun et al., Discrete Shells (2003), equation 2. Two corrections make
    # this grid bend like the rigidity it is given (docs/FabricSwatch.md):
    # STRUCTURED_GRID, and a clamp-line hinge that carries half a cell.
    rigidity = .00001  # N*m, neutral fallback
    hinges = []
    for sides in edges.values():
        if len(sides) != 2:
            continue
        a, b, c = sides[0]
        d = sides[1][2]
        edge = points[b]-points[a]
        area = (np.linalg.norm(np.cross(edge, points[c]-points[a]))
                + np.linalg.norm(np.cross(points[d]-points[a], edge))) / 2
        on_clamp_line = abs(points[a][0]) < 1e-12 and abs(points[b][0]) < 1e-12
        factor = 3*float(edge @ edge)/float(area) / STRUCTURED_GRID * (2 if on_clamp_line else 1)
        direction = uv[b]-uv[a]
        # Curvature acts perpendicular to the hinge. Approximate orthotropy;
        # no measured bend/twist coupling or Poisson response is claimed.
        warp_fraction = float(direction[1]**2 / (direction @ direction))
        hinges.append(dict(ids=[a, b, c, d], angle=0., compliance=1/(rigidity*factor),
                           geometry_factor=factor, warp_fraction=warp_fraction))
    scene['interior_hinges'], scene['interior_hinge_batches'] = colored(hinges, len(points), lambda h: h['ids'])
    scene['swatch'] = dict(pins=pins, sections=[list(range(x*rows, (x+1)*rows)) for x in range(1, columns)],
                           tip=list(range((columns-1)*rows, columns*rows)),
                           length_m=.08, width_m=width, height_m=height)
    return scene


# Discrete Shells' l/h assumes curvature is shared among three unstructured edge
# directions. On this right-triangle grid, bent along a mesh axis, only the
# cross edges and the diagonals fold, which over-counts rigidity by 2.4 on paper
# and 2.476 measured against a small-deflection cantilever. Without it the strip
# bent as if twice as stiff as the value entered.
STRUCTURED_GRID = 2.476


def elastica_drop_mm(rigidity, weight_gsm, length=.08, gravity=9.81):
    """Tip drop of a clamped, horizontal, inextensible strip under its own weight.

    The exact large-deflection answer the bend test should reproduce: with theta
    the downward slope, D theta'' = -q (L - s) cos(theta), theta(0) = 0, theta'(L) = 0.
    """
    from scipy.integrate import solve_bvp
    if not rigidity or not weight_gsm or rigidity <= 0 or weight_gsm <= 0:
        return None
    load = weight_gsm/1000*gravity

    def slope(s, y):
        return np.vstack((y[1], -load*(length-s)*np.cos(y[0])/rigidity))
    s = np.linspace(0, length, 400)
    guess = np.vstack((np.linspace(0, 1.2, s.size), np.full(s.size, 10.)))
    solution = solve_bvp(slope, lambda a, b: np.array([a[0], b[1]]), s, guess, max_nodes=200000, tol=1e-8)
    if not solution.success:
        return None
    fine = np.linspace(0, length, 8001)
    return float(np.trapz(np.sin(solution.sol(fine)[0]), fine)*1000)


DEFAULTS = dict(stretch_warp=1000., stretch_weft=1000., shear=100.,
                bend_warp=.00001, bend_weft=.00001, damping=14.)

# Step sizing for the loaded tests (docs/FabricSwatch.md, "Numerical range").
# XPBD converges in a substep only while a constraint's stiffness ratio
# sum(w |grad C|^2) dt^2 / compliance stays near one. A fixed 48 substeps put a
# stiff polyester near 400 and over-read its extension by 38%; holding the
# worst ratio at 2 keeps every measured sample within 0.2% of the exact strip.
FRAME = 1/60
STIFFNESS_RATIO = 2.
SUBSTEPS = (96, 1024)
LOADED_ITERATIONS = 4


def loaded_numerics(scene):
    """Substeps per frame that hold the stiffest membrane constraint at STIFFNESS_RATIO."""
    weights, worst = np.asarray(scene['inverse_mass'], float), 0.
    for membrane in scene['membranes']:
        u, v = np.asarray(membrane['u']), np.asarray(membrane['v'])
        w = weights[membrane['ids']]
        # |grad C|^2 per corner at rest: stretch along u, along v, and shear.
        for gradient, compliance in zip((u*u, v*v, u*u + v*v), membrane['compliance']):
            if compliance > 0:
                worst = max(worst, FRAME**2 * float(w @ gradient) / compliance)
    needed = int(np.ceil(np.sqrt(worst / STIFFNESS_RATIO))) if worst else SUBSTEPS[0]
    substeps = min(max(needed, SUBSTEPS[0]), SUBSTEPS[1])
    return dict(substeps=substeps, iterations=LOADED_ITERATIONS, stiffness_ratio=worst / substeps**2,
                validated=needed <= SUBSTEPS[1])


def apply_material(scene, properties, direction='warp', mode='bend'):
    """Compile SI surface properties into XPBD energy compliances (1/J)."""
    if direction not in ('warp', 'weft') or mode not in ('bend', 'stretch', 'shear'):
        raise ValueError('Unknown swatch direction or test.')
    from webapp.fabric_preview import with_weight
    result = with_weight(scene, properties['weight']['value'])
    applied = {key: dict(value=properties[key]['value'] if properties[key]['value'] is not None else default,
                        origin=properties[key]['origin'] if properties[key]['value'] is not None else 'assumed',
                        unit=properties[key]['unit']) for key, default in DEFAULTS.items()}
    if any(not np.isfinite(p['value']) or p['value'] > 3.4028235e38 for p in applied.values()):
        raise ValueError('These properties exceed the numeric range of the browser simulator.')
    applied_weight = properties['weight']['value']
    along, across = ('warp', 'weft') if direction == 'warp' else ('weft', 'warp')
    eu, ev, shear = (applied[k]['value'] for k in ('stretch_'+along, 'stretch_'+across, 'shear'))
    du, dv = (applied['bend_'+a]['value'] for a in (along, across))
    def compliance(stiffness):
        value = 1/stiffness if stiffness > 0 else -1.  # Zero disables a force; missing != zero.
        if not np.isfinite(value) or (value > 0 and not 1.17549435e-38 <= value <= 3.4028235e38):
            raise ValueError('These properties exceed the numeric range of the browser simulator.')
        return value
    for hinge in result['interior_hinges']:
        fraction = hinge['warp_fraction']
        rigidity = fraction*du + (1-fraction)*dv
        hinge['compliance'] = compliance(rigidity*hinge['geometry_factor'])
    uv = np.asarray(result['uv'])
    membranes = []
    for ids in result['faces']:
        a, b, c = uv[ids]
        matrix = np.column_stack((b-a, c-a))
        inv = np.linalg.inv(matrix)
        area = abs(float(np.linalg.det(matrix))) / 2
        membranes.append(dict(ids=ids,
            u=[-inv[0, 0]-inv[1, 0], inv[0, 0], inv[1, 0]],
            v=[-inv[0, 1]-inv[1, 1], inv[0, 1], inv[1, 1]],
            compliance=[compliance(area*k) for k in (eu, ev, shear)]))
    result['membranes'], result['membrane_batches'] = colored(membranes, len(uv), lambda m: m['ids'])
    result['external_forces'] = [[0., 0., 0.] for _ in uv]
    traction = 25. if mode == 'stretch' else 5. if mode == 'shear' else 0.
    # In-plane loading isolates membrane response without gravity masking it.
    # Trapezoidal edge quadrature gives total force = traction * strip width.
    tip = result['swatch']['tip']
    spacing = result['swatch']['width_m']/(len(tip)-1)
    for index, vertex in enumerate(tip):
        result['external_forces'][vertex][0 if mode == 'stretch' else 2] = traction*spacing*(.5 if index in (0, len(tip)-1) else 1.)
    result['fabric_test'].update(scope='orthotropic-material', direction=direction, mode=mode,
        applied=applied, traction_n_m=traction, damping=applied['damping']['value'],
        gravity=9.81 if mode == 'bend' else 0.,
        expected_extension_percent=traction/eu*100 if eu and mode == 'stretch' else None,
        expected_drop_mm=elastica_drop_mm(du, applied_weight, result['swatch']['length_m']) if mode == 'bend' else None)
    if mode != 'bend':
        result['fabric_test']['numerics'] = loaded_numerics(result)
    return result
