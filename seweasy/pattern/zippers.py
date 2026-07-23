"""Zipper hardware geometry for the 3D view.

Like buttons (see buttons.py), a zipper is NOT simulated cloth -- it is a
marker placed onto the *draped* garment so the fragile stitch/sim layer stays
untouched. A garment declares a zipper in its assembled pattern:

    pattern['zippers'] = [{
        'placement': 'center_back',  # or 'center_front'
        'length': 0.6,               # fraction of garment height, from the top
        'width': 1.2,                # tape width (cm)
        'panel': 'back',             # panel to draw the 2D marker down (center)
        'seam_label': 'cb_zip',      # OR a labeled seam edge for the 2D marker
    }]

`center_seam_line` finds where the zipper sits on the draped mesh (the actual
center-front / center-back surface line), and `build_zipper` makes a small
tape+chain+pull mesh for display. The 2D pattern marker is drawn separately by
the pattern renderer (see wrappers._add_zipper_markers).
"""
import numpy as np


def center_seam_line(verts, placement='center_back', length=0.6,
                     top_frac=0.02, x_tol=3.0, n=40):
    """Trace the center-front / center-back line down a draped garment.

    * verts     -- (N,3) draped garment vertices (cm)
    * placement -- 'center_back' (rides the max-depth back) or 'center_front'
    * length    -- how far down to run, as a fraction of garment height
    * n         -- number of samples along the line

    At evenly-spaced heights from just below the top edge downward, take the
    vertex nearest the center line (|x| < x_tol) that is furthest to the back
    (min Z) or front (max Z). Returns an (M,3) polyline top->bottom, or an
    empty array if the garment has no vertices near the center line.
    """
    verts = np.asarray(verts, dtype=float)
    if len(verts) == 0:
        return np.empty((0, 3))
    back = (placement == 'center_back')
    ymin, ymax = verts[:, 1].min(), verts[:, 1].max()
    span = ymax - ymin
    ys = np.linspace(ymax - top_frac * span, ymax - length * span, n)
    band = max(0.5 * span / n, 0.6)
    pts = []
    for y in ys:
        m = (np.abs(verts[:, 1] - y) < band) & (np.abs(verts[:, 0]) < x_tol)
        if not m.any():
            continue
        sub = verts[m]
        p = sub[np.argmin(sub[:, 2])] if back else sub[np.argmax(sub[:, 2])]
        pts.append([0.0, float(p[1]), float(p[2])])  # snap to x=0 (center)
    return np.asarray(pts)


def build_zipper(line, placement='center_back', width=1.2,
                 tape_color=(30, 30, 32, 255), chain_color=(150, 150, 155, 255),
                 pull_color=(120, 120, 125, 255)):
    """Build a trimesh of a closed zipper riding `line`, or None.

    A dark tape ribbon with a lighter raised center chain and a small pull tab
    near the top. The ribbon lies just proud of the fabric, offset along the
    outward (front/back) normal so it does not z-fight the garment surface.
    """
    line = np.asarray(line, dtype=float)
    if len(line) < 2:
        return None
    import trimesh

    outward = np.array([0.0, 0.0, -1.0]) if placement == 'center_back' \
        else np.array([0.0, 0.0, 1.0])

    def ribbon(half_w, lift):
        """Triangulated strip of the given half-width, lifted off the surface."""
        left, right = [], []
        for i, p in enumerate(line):
            t = line[min(i + 1, len(line) - 1)] - line[max(i - 1, 0)]
            tn = np.linalg.norm(t)
            t = t / tn if tn > 1e-6 else np.array([0.0, -1.0, 0.0])
            side = np.cross(t, outward)
            sn = np.linalg.norm(side)
            side = side / sn if sn > 1e-6 else np.array([1.0, 0.0, 0.0])
            base = p + outward * lift
            left.append(base + side * half_w)
            right.append(base - side * half_w)
        v = np.array(left + right)
        m = len(line)
        faces = []
        for i in range(m - 1):
            a, b, c, d = i, i + 1, m + i, m + i + 1
            faces.append([a, b, c])
            faces.append([b, d, c])
        return trimesh.Trimesh(vertices=v, faces=faces, process=False)

    parts = []
    tape = ribbon(width / 2, 0.15)
    tape.visual.face_colors = tape_color
    parts.append(tape)
    chain = ribbon(width * 0.18, 0.28)
    chain.visual.face_colors = chain_color
    parts.append(chain)

    # Pull tab: a small flat box just below the top of the zipper
    top = line[0]
    t = line[1] - line[0]
    tn = np.linalg.norm(t)
    t = t / tn if tn > 1e-6 else np.array([0.0, -1.0, 0.0])
    pull = trimesh.creation.box(extents=(width * 0.7, width * 1.1, 0.2))
    pull.apply_translation(top + t * (width * 0.9) + outward * 0.32)
    pull.visual.face_colors = pull_color
    parts.append(pull)

    return trimesh.util.concatenate(parts)
