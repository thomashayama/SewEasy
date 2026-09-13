"""Attach rigid shirt buttons to material triangles, without GPU/server work."""
import numpy as np
import trimesh


def button_attachments(box, pattern, data):
    if 'fasteners' in pattern:
        return fastener_attachments(box, pattern['fasteners'], data)
    groups = list(pattern.get('button_groups', []))
    if pattern.get('buttons'):
        groups.append(pattern['buttons'])
    if not groups:
        return []
    offsets, offset = {}, 0
    for name in box.panelNames:
        offsets[name] = offset
        offset += len(box.panels[name].panel_vertices)
    positions = data['unsewn_vertices']
    faces = data['uv_faces']
    result = []

    def attach(name, point, diameter, role):
        panel_faces = faces[np.asarray(data['face_panels']) == name]
        triangles = positions[panel_faces]
        closest = trimesh.triangles.closest_point(triangles, np.tile(point, (len(triangles), 1)))
        index = np.argmin(np.linalg.norm(closest - point, axis=1))
        triangle = triangles[index]
        weights = trimesh.triangles.points_to_barycentric(triangle[None], closest[index:index+1])[0]
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        result.append(dict(ids=panel_faces[index].tolist(), weights=weights.tolist(),
                           radius_m=float(diameter) / 200, normal_sign=1 if normal[2] >= 0 else -1,
                           panel=name, role=role))

    for config in groups:
        count = int(config.get('count', 0))
        if count <= 0:
            continue
        diameter = float(config.get('diameter', 1.3))
        allowed = config.get('panels', box.panelNames)
        for name in allowed:
            panel = box.panels[name]
            ids = sorted({i for edge in panel.edges if edge.label == config.get('placket_label', 'button_placket')
                          for i in edge.vertex_range})
            if len(ids) < 2:
                continue
            line = positions[np.asarray(ids) + offsets[name]]
            line = line[np.argsort(-line[:, 1])]
            length = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
            for t in np.linspace(.06, .94, count):
                distance = t * length[-1]
                index = min(max(1, int(np.searchsorted(length, distance))), len(line)-1)
                fraction = (distance-length[index-1]) / max(length[index]-length[index-1], 1e-12)
                attach(name, line[index-1]*(1-fraction)+line[index]*fraction, diameter, 'placket')
        # A smaller neck-band button and one on each barrel cuff complete the
        # shirt hardware. They use their own cloth triangles, not a body anchor.
        for name in allowed:
            local = name.split('__')[-1]
            if local != 'right_stand_front' and local not in ('sl_left_cuff_f', 'sl_right_cuff_f'):
                continue
            ids = np.unique(faces[np.asarray(data['face_panels']) == name])
            points = positions[ids]
            target = points.mean(axis=0)
            if local == 'right_stand_front':
                target[0] = points[:, 0].max() - .002
            attach(name, target, min(diameter, 1.1), 'neck' if local == 'right_stand_front' else 'cuff')
    return result


def fastener_attachments(box, fasteners, data):
    """Map authored button and hole seats to distinct material triangles.

    A fastener transfers load between these two triangles. Neither endpoint is
    attached to the mannequin; no front stitch or nearest-world-point welding
    substitutes for the authored connection.
    """
    if not fasteners:
        return []
    offsets, offset = {}, 0
    for name in box.panelNames:
        offsets[name] = offset
        offset += len(box.panels[name].panel_vertices)
    positions, faces = data['unsewn_vertices'], data['uv_faces']
    center = np.asarray(data['body_vertices']).mean(axis=0)

    def anchor(seat):
        name = seat['panel']
        panel_faces = faces[np.asarray(data['face_panels']) == name]
        local = np.asarray(box.panels[name].panel_vertices)
        triangles = np.pad(local[panel_faces-offsets[name]], ((0,0),(0,0),(0,1)))
        point = np.array([*seat['position'], 0.])
        closest = trimesh.triangles.closest_point(triangles, np.tile(point, (len(triangles),1)))
        distances = np.linalg.norm(closest-point, axis=1)
        index = np.argmin(distances)
        if distances[index] > .01:
            raise ValueError(f'Button seat lies outside {name}: {seat["position"]}')
        weights = trimesh.triangles.points_to_barycentric(triangles[index:index+1], closest[index:index+1])[0]
        uv = np.asarray(data['uv'])[panel_faces[index]]
        local_triangle = triangles[index,:,:2]
        transform = np.linalg.solve(local_triangle[1:]-local_triangle[0], uv[1:]-uv[0])
        direction = np.asarray(seat['direction']) @ transform
        direction /= np.linalg.norm(direction)
        world = positions[panel_faces[index]]
        normal = np.cross(world[1]-world[0],world[2]-world[0])
        return dict(panel=name, ids=panel_faces[index].tolist(), weights=weights.tolist(),
                    normal_sign=1 if np.dot(normal,world.mean(axis=0)-center)>=0 else -1,
                    uv_center=(weights@uv).tolist(), uv_direction=direction.tolist())

    result=[]
    for f in fasteners:
        a,b=anchor(f['button']),anchor(f['buttonhole'])
        if a['panel']==b['panel']:
            raise ValueError('Button and buttonhole must connect separate panels')
        result.append(dict(**a, id=f['id'], hole=b, role=f['role'], radius_m=f['diameter_cm']/200,
                           clearance_m=f['clearance_m'], compliance=f['compliance'], closed=f['closed']))
    return result
