"""Button hardware geometry for the 3D view.

Buttons are not simulated cloth -- they are placed onto the *draped* garment
by sampling its front-centre surface. This keeps them decoupled from the
fragile stitch/sim layer: given the final draped vertices and a button count,
`sample_seats` finds where the buttons sit, and `build_discs` makes the small
disc meshes for display.
"""
import numpy as np


def sample_seats(verts, count, diameter, top_frac=0.11, bottom_frac=0.06,
                 x_tol=3.0):
    """Locate `count` button seats down the front-centre of a draped garment.

    * verts    -- (N,3) draped garment vertices (cm)
    * count    -- number of buttons (<=0 -> no buttons)
    * diameter -- button diameter (cm)

    At evenly-spaced heights from just below the collar to near the hem, take
    the front-most (max Z) vertex near the centre line (|x| < x_tol). Returns
    a list of {pos:[x,y,z], normal:[x,y,z], diameter}.
    """
    verts = np.asarray(verts, dtype=float)
    if count <= 0 or len(verts) == 0:
        return []
    ymin, ymax = verts[:, 1].min(), verts[:, 1].max()
    ys = np.linspace(ymax - top_frac * (ymax - ymin),
                     ymin + bottom_frac * (ymax - ymin), count)
    band = max(0.5 * abs(ys[0] - ys[1]), 1.0) if count > 1 else 2.0
    seats = []
    for y in ys:
        m = (np.abs(verts[:, 1] - y) < band) & (np.abs(verts[:, 0]) < x_tol)
        if not m.any():
            continue
        p = verts[m][np.argmax(verts[m][:, 2])]
        seats.append({'pos': [0.0, float(p[1]), float(p[2])],
                      'normal': [0.0, 0.0, 1.0], 'diameter': float(diameter)})
    return seats


def seats_along_line(pts, count, diameter, top_frac=0.06, bottom_frac=0.05):
    """Place `count` button seats evenly (by arc length) along a draped line.

    * pts      -- (M,3) draped positions of the placket-labeled vertices
    * count    -- number of buttons (<=0 -> no buttons)
    * diameter -- button diameter (cm)

    Orders the points top (high Y) to bottom, measures cumulative 3D arc
    length, and drops `count` seats at even arc-length intervals (with small
    end margins). Unlike `sample_seats` this rides the *actual* placket seam,
    so buttons follow the real button line instead of the front-most surface
    (which, near the neck, is the protruding collar). Returns a list of
    {pos, normal, diameter}, or [] if there are too few points.
    """
    pts = np.asarray(pts, dtype=float)
    if count <= 0 or len(pts) < 2:
        return []
    # Top to bottom, dropping coincident welded vertices
    pts = pts[np.argsort(-pts[:, 1])]
    keep = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - keep[-1]) > 1e-4:
            keep.append(p)
    pts = np.asarray(keep)
    if len(pts) < 2:
        return []
    cum = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    total = cum[-1]
    if total <= 0:
        return []
    targets = np.linspace(top_frac * total, (1.0 - bottom_frac) * total, count)
    seats = []
    for t in targets:
        i = min(max(int(np.searchsorted(cum, t)), 1), len(pts) - 1)
        span = cum[i] - cum[i - 1]
        f = 0.0 if span <= 0 else (t - cum[i - 1]) / span
        p = pts[i - 1] * (1 - f) + pts[i] * f
        seats.append({'pos': [float(p[0]), float(p[1]), float(p[2])],
                      'normal': [0.0, 0.0, 1.0], 'diameter': float(diameter)})
    return seats


def build_discs(seats, color=(245, 245, 245, 255), thickness=0.2):
    """Build one trimesh mesh of all button discs, or None if no seats.

    Each disc is a thin cylinder centred on its seat, axis along the seat
    normal, sitting just proud of the fabric surface.
    """
    if not seats:
        return None
    import trimesh

    discs = []
    for s in seats:
        pos = np.asarray(s['pos'], dtype=float)
        nrm = np.asarray(s['normal'], dtype=float)
        nrm = nrm / (np.linalg.norm(nrm) or 1.0)
        c = trimesh.creation.cylinder(
            radius=s['diameter'] / 2, height=thickness, sections=20)
        c.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], nrm))
        c.apply_translation(pos + nrm * (thickness / 2 + 0.05))
        discs.append(c)
    mesh = trimesh.util.concatenate(discs)
    mesh.visual.face_colors = color
    return mesh
