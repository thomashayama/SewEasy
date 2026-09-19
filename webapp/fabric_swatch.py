"""A small cantilever fixture, built on CPU and simulated only in WebGPU.

This isolates density using a shared, *assumed* bending coefficient. It does
not convert a vendor's FAB stiffness coefficient into an SI bending modulus.
"""
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
    # E = kB * (l/h) * theta^2; XPBD compliance = 1/(2*kB*l/h).
    # Shared diagnostic coefficient, NOT this fabric's measured rigidity.
    # Grinspun et al., Discrete Shells (2003), equation 2.
    coefficient = .00025  # N*m, assumed for both strips
    hinges = []
    for sides in edges.values():
        if len(sides) != 2:
            continue
        a, b, c = sides[0]
        d = sides[1][2]
        edge = points[b]-points[a]
        area = (np.linalg.norm(np.cross(edge, points[c]-points[a]))
                + np.linalg.norm(np.cross(points[d]-points[a], edge))) / 2
        factor = 3*float(edge @ edge)/float(area)
        hinges.append(dict(ids=[a, b, c, d], angle=0., compliance=1/(2*coefficient*factor)))
    scene['interior_hinges'], scene['interior_hinge_batches'] = colored(hinges, len(points), lambda h: h['ids'])
    scene['swatch'] = dict(pins=pins, sections=[list(range(x*rows, (x+1)*rows)) for x in range(1, columns)],
                           tip=list(range((columns-1)*rows, columns*rows)),
                           length_m=.08, width_m=width, height_m=height,
                           assumed_bending_coefficient_nm=coefficient)
    return scene
