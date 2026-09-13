"""CPU mesh packaging for browser WebGPU cloth simulation. No GPU dependencies."""
import time

import numpy as np
import trimesh


def bvh(vertices, faces):
    triangles = vertices[faces]
    centers = triangles.mean(axis=1)
    nodes, ordered = [], []

    def split(ids):
        index = len(nodes)
        lo, hi = triangles[ids].min(axis=(0, 1)), triangles[ids].max(axis=(0, 1))
        node = dict(lo=lo.tolist(), hi=hi.tolist(), escape=0, start=0, count=0)
        nodes.append(node)
        if len(ids) <= 4:
            node.update(start=len(ordered), count=len(ids))
            ordered.extend(ids.tolist())
        else:
            axis = np.argmax(np.ptp(centers[ids], axis=0))
            ids = ids[np.argsort(centers[ids, axis], kind='stable')]
            middle = len(ids) // 2
            split(ids[:middle])
            split(ids[middle:])
        node['escape'] = len(nodes)
    split(np.arange(len(faces)))
    return nodes, faces[ordered]


def build_scene(data, meta, name):
    """Build browser solver input from triangulated panels, entirely on CPU."""
    started = time.perf_counter()
    positions, uv, faces = data['unsewn_vertices'], data['uv'], data['uv_faces']
    n = len(positions)
    world_ids = np.full(n, -1, dtype=np.int32)
    for f, wf in zip(faces, data['faces']):
        for a, b in zip(f, wf):
            assert world_ids[a] in (-1, b), 'Ambiguous sewn vertex mapping'
            world_ids[a] = b
    assert np.all(world_ids >= 0)
    rest = uv[faces]
    area = np.abs(np.cross(rest[:, 1]-rest[:, 0], rest[:, 2]-rest[:, 0])) / 2
    assert np.all(area > 1e-12)
    mass = np.zeros(n)
    np.add.at(mass, faces.ravel(), np.repeat(area * 0.3 / 3, 3))
    assert np.all(mass > 0)
    edges, incident, neighbors = {}, [[] for _ in range(n)], [set() for _ in range(n)]
    for fi, (a, b, c) in enumerate(faces):
        for u, v, opposite in [(a, b, c), (b, c, a), (c, a, b)]:
            edges.setdefault(tuple(sorted((int(u), int(v)))), []).append((int(opposite), fi))
            neighbors[u].add(int(v))
            neighbors[v].add(int(u))
        for u in (a, b, c):
            incident[u].append(fi)
    vertex_panels = [''] * n
    for f, panel in zip(faces, data['face_panels']):
        for i in f:
            assert vertex_panels[i] in ('', str(panel))
            vertex_panels[i] = str(panel)
    constraints = []
    for (a, b), sides in edges.items():
        delta = uv[a] - uv[b]
        constraints.append([a, b, 0, float(delta[0]), float(delta[1]), 1.0, 0.0])
        if len(sides) == 2:
            a, b = sides[0][0], sides[1][0]
            delta = uv[a] - uv[b]
            panel = str(data['face_panels'][sides[0][1]])
            stiff = float(meta['panel_stiffness'].get(panel, 1))
            constraints.append([a, b, 1, float(delta[0]), float(delta[1]), 1/stiff, 0.0])
    # Preserve the authored fold where the tube-top cuff joins its bodice.
    # Stitches alone join points but provide no hinge resistance, allowing the
    # cuff to flip above the neckline. Rest distances use the local seam frame
    # and original panel-normal angle, independent of their unsewn separation.
    sewn_edges = {}
    for (a, b), sides in edges.items():
        if len(sides) == 1:
            if world_ids[a] > world_ids[b]:
                a, b = b, a
            sewn_edges.setdefault((world_ids[a], world_ids[b]), []).append((a, b, *sides[0]))
    creases = 0
    for sides in sewn_edges.values():
        if len(sides) != 2:
            continue
        names = {str(data['face_panels'][side[3]]) for side in sides}
        if names not in ({'front', 'fcuff'}, {'back', 'bcuff'}):
            continue
        along, heights, normals = [], [], []
        for a, b, opposite, fi in sides:
            axis = uv[b]-uv[a]
            axis /= np.linalg.norm(axis)
            offset = uv[opposite]-uv[a]
            along.append(np.dot(offset, axis))
            heights.append(abs(np.cross(axis, offset)))
            tri = positions[faces[fi]]
            normal = np.cross(tri[1]-tri[0], tri[2]-tri[0])
            normals.append(normal/np.linalg.norm(normal))
        across = np.sqrt(max(0, heights[0]**2+heights[1]**2+2*heights[0]*heights[1]*np.dot(*normals)))
        a, b = sides[0][2], sides[1][2]
        stiffness = max(float(meta['panel_stiffness'].get(name, 1)) for name in names)
        constraints.append([a, b, 1, float(along[0]-along[1]), float(across), 1/stiffness, 0.])
        neighbors[a].add(b)
        neighbors[b].add(a)
        creases += 1
    seam_count = 0
    for sewn in np.unique(world_ids):
        ids = np.flatnonzero(world_ids == sewn)
        for b in ids[1:]:
            a = int(ids[0])
            constraints.append([a, int(b), 2, 0., 0., 1., float(np.linalg.norm(positions[a]-positions[b]))])
            seam_count += 1
    # Each dispatch may write both constraint endpoints without atomics.
    # A color cannot contain two constraints sharing any vertex.
    used, colors = [set() for _ in range(n)], []
    for constraint in constraints:
        a, b = constraint[:2]
        forbidden = used[a] | used[b]
        color = 0
        while color in forbidden:
            color += 1
        while len(colors) <= color:
            colors.append([])
        colors[color].append(constraint)
        used[a].add(color)
        used[b].add(color)
    batches, ordered = [], []
    for color in colors:
        ids = [p for c in color for p in c[:2]]
        assert len(set(ids)) == len(ids), 'Constraint color has a write race'
        batches.append([len(ordered), len(color)])
        ordered.extend(color)
    body = trimesh.Trimesh(data['body_vertices'], data['body_faces'], process=False)
    nodes, body_faces = bvh(body.vertices, body.faces)
    scene = dict(name=name, garment=meta['garment'], resolution_cm=meta['resolution_cm'],
                 vertices=positions.tolist(), inverse_mass=(1 / mass).tolist(), uv=uv.tolist(),
                 faces=faces.tolist(), vertex_panels=vertex_panels, sewn_ids=world_ids.tolist(), constraints=ordered, batches=batches,
                 incident_faces=incident, neighbors=[sorted(x) for x in neighbors],
                 body_vertices=body.vertices.tolist(), body_normals=body.vertex_normals.tolist(),
                 body_faces=body_faces.tolist(), body_bvh=nodes,
                 seams=seam_count, crease_constraints=creases, panels=meta['panels'],
                 initialization='Unsewn original panel transforms; no precomputed drape',
                 preparation_seconds=time.perf_counter()-started)
    return scene


def panel_mesh_data(box, body_mesh):
    """Preserve authored panel transforms and 2D rest shape, in metres."""
    vertices = np.asarray(box.vertices, dtype=np.float64) * 0.01
    faces = np.asarray(box.faces, dtype=np.int32)
    uv = np.asarray(box.vertex_texture, dtype=np.float64) * 0.01
    uv_faces = np.asarray(box.faces_with_texture, dtype=np.int32)[:, [1, 3, 5]]
    rest = uv[uv_faces]
    dm = np.stack([rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]], axis=-1)
    if np.any(np.abs(np.linalg.det(dm)) < 1e-12):
        raise ValueError('Degenerate 2D rest triangle')
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
    return dict( vertices=vertices, faces=faces,
                        uv=uv, uv_faces=uv_faces, body_vertices=body_v,
                        body_faces=np.asarray(body_mesh.faces, dtype=np.int32),
                        face_panels=face_panels,
                        unsewn_vertices=np.asarray(unsewn) * 0.01 + [0, shift, 0])
