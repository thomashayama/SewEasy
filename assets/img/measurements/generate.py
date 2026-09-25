"""Generate the body-measurement guide diagrams from the default mannequin.

Each diagram is the neutral mannequin (assets/bodies/mean_all.obj) rendered
from the side that shows the measurement best (front, back, side or a
three-quarter turn), cropped to where it is taken, with the tape drawn from
the mesh itself: circumferences are real cross-sections at the landmark
heights the pattern framework uses (seweasy.meshgen.body_fit.levels),
lengths follow the body surface or run vertically, as each measurement is
defined (docs/Body Measurements GarmentCode.pdf). The front of a ring is
solid, the part behind the body dashed.

The body is a small CPU rasterisation (no GPU, no OpenGL), embedded in each
SVG as WebP under vector annotations, so text and lines stay sharp.

Run from the repo root:

    python assets/img/measurements/generate.py
"""
import base64
import io
import math
from pathlib import Path
import sys

import numpy as np
import trimesh
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from seweasy.meshgen.body_fit import ANGLES, arm_frame, levels, mannequin_measurements  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
MESH = trimesh.load(REPO / 'assets/bodies/mean_all.obj', process=False)
M = {k: v if k in ANGLES else v / 100 for k, v in mannequin_measurements('all').items()}
L = levels(M)

# Palette: a muslin dress form on warm paper, measured in the studio's selvedge red.
PAPER = np.array([246, 243, 237])
MUSLIN = np.array([226, 219, 207])
EDGE = np.array([150, 141, 128])
ACCENT = '#c2413b'
GUIDE = '#7b8594'
INK = '#2b2f36'

WIDTH, HEIGHT = 400, 500          # SVG units; the body renders at 2x for sharpness
SUPERSAMPLE = 2


# --------------------------------------------------------------- camera

def _rot_y(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])


def _rot_x(deg):
    a = math.radians(deg)
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


class View:
    """Orthographic camera: `yaw` turns the body (0 front, 180 back, 90 its left side), `pitch` looks down."""

    def __init__(self, yaw=0, pitch=0):
        self.R = _rot_x(pitch) @ _rot_y(yaw)

    def project(self, points):
        """World metres -> (x right, y down, depth towards the camera)."""
        p = np.atleast_2d(points) @ self.R.T
        return np.stack([p[:, 0], -p[:, 1], p[:, 2]], axis=1)


FRONT, BACK, SIDE = View(0, 4), View(180, 4), View(90, 0)
TURNED = View(-28, 14)            # three-quarter from above: rings read as rings


# --------------------------------------------------------------- rendering

def render(view, crop, size):
    """Shade the mannequin inside `crop` (x0, y0, x1, y1 in camera metres) at `size` pixels."""
    w, h = size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE
    x0, y0, x1, y1 = crop
    sx, sy = w / (x1 - x0), h / (y1 - y0)
    p = view.project(MESH.vertices)
    px, py, depth = (p[:, 0] - x0) * sx, (p[:, 1] - y0) * sy, p[:, 2]
    normals = MESH.vertex_normals @ view.R.T
    zbuf = np.full((h, w), -np.inf)
    nbuf = np.zeros((h, w, 3))
    faces = MESH.faces
    fx, fy = px[faces], py[faces]
    lo_x, hi_x = np.floor(fx.min(1)).astype(int), np.ceil(fx.max(1)).astype(int)
    lo_y, hi_y = np.floor(fy.min(1)).astype(int), np.ceil(fy.max(1)).astype(int)
    keep = (hi_x >= 0) & (lo_x < w) & (hi_y >= 0) & (lo_y < h)
    for f in np.nonzero(keep)[0]:
        a, b, c = faces[f]
        ax, ay, bx, by, cx, cy = px[a], py[a], px[b], py[b], px[c], py[c]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        xs = np.arange(max(lo_x[f], 0), min(hi_x[f], w - 1) + 1)
        ys = np.arange(max(lo_y[f], 0), min(hi_y[f], h - 1) + 1)
        if not len(xs) or not len(ys):
            continue
        gx, gy = np.meshgrid(xs + .5, ys + .5)
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not inside.any():
            continue
        d = l1 * depth[a] + l2 * depth[b] + l3 * depth[c]
        region = (slice(ys[0], ys[-1] + 1), slice(xs[0], xs[-1] + 1))
        nearer = inside & (d > zbuf[region])
        if not nearer.any():
            continue
        zbuf[region][nearer] = d[nearer]
        n = l1[..., None] * normals[a] + l2[..., None] * normals[b] + l3[..., None] * normals[c]
        nbuf[region][nearer] = n[nearer]
    covered = np.isfinite(zbuf)
    n = nbuf / np.maximum(np.linalg.norm(nbuf, axis=2, keepdims=True), 1e-9)
    key = np.array([-.45, .55, .70]); key /= np.linalg.norm(key)
    fill = np.array([.65, .05, .76]); fill /= np.linalg.norm(fill)
    light = (.34 + .56 * np.clip(n @ key, 0, 1) + .16 * np.clip(n @ fill, 0, 1)
             + .06 * np.clip(n[..., 1], 0, 1))
    image = np.where(covered[..., None], np.clip(MUSLIN * light[..., None], 0, 255), PAPER)
    # A fine outline keeps the silhouette crisp against the paper.
    mask = Image.fromarray((covered * 255).astype(np.uint8))
    rim = np.array(mask.filter(ImageFilter.MaxFilter(3))) > 0
    rim &= ~(np.array(mask.filter(ImageFilter.MinFilter(3))) > 0)
    image[rim] = image[rim] * .35 + EDGE * .65
    picture = Image.fromarray(image.astype(np.uint8)).resize(size, Image.LANCZOS)
    buffer = io.BytesIO()
    picture.save(buffer, 'WEBP', quality=82, method=6)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


# --------------------------------------------------------------- body geometry

def loops(origin, normal):
    section = MESH.section(plane_origin=origin, plane_normal=normal)
    return [np.asarray(d) for d in section.discrete] if section is not None else []


def torso_ring(y):
    rings = [r for r in loops([0, y, 0], [0, 1, 0]) if r[:, 0].min() < 0 < r[:, 0].max()]
    return max(rings, key=lambda r: np.ptp(r[:, 0]))


def leg_ring(y, side=1):
    rings = [r for r in loops([0, y, 0], [0, 1, 0]) if r[:, 0].mean() * side > .02]
    return min(rings, key=lambda r: abs(r[:, 0].mean() - side * .1))


def arm_ring(t, side=1):
    joint, axis, _ = arm_frame(M, side)
    centre = joint + t * M['arm_length'] * axis
    rings = loops(centre, axis)
    return min(rings, key=lambda r: np.linalg.norm(r.mean(0) - centre)), centre


def hit(origin, direction):
    """First surface point along a ray."""
    points, _, _ = MESH.ray.intersects_location([origin], [direction])
    if not len(points):
        raise ValueError(f'No surface along {origin} {direction}')
    return points[np.argmin(np.linalg.norm(points - origin, axis=1))]


def shoulder_tip(side):
    joint, _, _ = arm_frame(M, side)
    return hit([joint[0] * .96, L['top'] + .1, 0], [0, -1, 0])


def sagittal(x, keep):
    """The body's outline in the vertical plane x = const, as points satisfying `keep`, top down."""
    points = np.concatenate(loops([x, 0, 0], [1, 0, 0]))
    points = points[keep(points)]
    return points[np.argsort(-points[:, 1])]


def side_points(ring):
    return ring[np.argmin(ring[:, 0])], ring[np.argmax(ring[:, 0])]


def half(ring, back):
    """The front (or back) half of a ring, between its two side points, in order."""
    i, j = np.argmin(ring[:, 0]), np.argmax(ring[:, 0])
    first = np.roll(ring, -i, axis=0)
    k = (j - i) % len(ring)
    a, b = first[:k + 1], np.vstack([first[k:], first[:1]])
    pick = a if (a[:, 2].mean() < b[:, 2].mean()) == back else b
    return pick


def bust_point(side):
    ring = torso_ring(L['bust'])
    candidates = ring[ring[:, 0] * side > .03]
    return candidates[np.argmax(candidates[:, 2])]


def seat_point(side):
    ring = torso_ring(L['hips'])
    candidates = ring[ring[:, 0] * side > .03]
    return candidates[np.argmin(candidates[:, 2])]


# --------------------------------------------------------------- drawing

class Diagram:
    """Annotations in world metres, projected by one view; cropped around them."""

    def __init__(self, view, minimum=.6):
        self.view = view
        self.items = []
        self.focus = []
        self.minimum = minimum

    def _track(self, points):
        self.focus.append(self.view.project(np.atleast_2d(points))[:, :2])

    def ring(self, points):
        self.items.append(('ring', np.asarray(points)))
        self._track(points)

    def path(self, points, ends=True):
        self.items.append(('path', np.asarray(points), ends))
        self._track(points)

    def line(self, a, b, ends=True):
        self.path([a, b], ends)

    def dot(self, p, label=None, anchor='start', offset=(8, 4)):
        self.items.append(('dot', np.asarray(p), label, anchor, offset))
        self._track(p)

    def level(self, y, label):
        """A dashed guide across the body at a landmark height."""
        self.items.append(('level', y, label))

    def angle(self, vertex, reference, measured, label):
        self.items.append(('angle', np.asarray(vertex), np.asarray(reference), np.asarray(measured), label))
        self._track([vertex, reference, measured])

    def note(self, p, label, anchor='start', offset=(10, 4)):
        self.items.append(('note', np.asarray(p), label, anchor, offset))
        self._track(p)

    def context(self, *points):
        """Extra body points the crop must show."""
        self._track(np.asarray(points))

    def _labels(self, scale):
        """Camera-space corners of every label box at this scale (metres)."""
        corners = []
        for item in self.items:
            if item[0] in ('dot', 'note') and item[2]:
                _, p, label, anchor, (ox, oy) = item
                (x, y, _), = self.view.project(p)
                width = (len(label) * 7.4 + 6) / scale
                dx = ox / scale if anchor == 'start' else -ox / scale if anchor == 'end' else 0
                left = x + dx - (width if anchor == 'end' else width / 2 if anchor == 'middle' else 0)
                top = y + (oy - 12) / scale
                corners += [[left, top], [left + width, top + 16 / scale]]
        return np.array(corners).reshape(-1, 2)

    def crop(self, margin=.09):
        box = self._crop(np.vstack(self.focus), margin)
        labels = self._labels(WIDTH / (box[2] - box[0]))
        if len(labels):
            box = self._crop(np.vstack([*self.focus, labels]), margin)
        return box

    def _crop(self, pts, margin):
        minimum = self.minimum
        x0, y0 = pts.min(0) - margin
        x1, y1 = pts.max(0) + margin
        body = self.view.project(MESH.vertices)
        bx0, by0 = body[:, :2].min(0) - .03
        bx1, by1 = body[:, :2].max(0) + .03
        if y1 - y0 < minimum:
            c = (y0 + y1) / 2
            y0, y1 = c - minimum / 2, c + minimum / 2
        aspect = WIDTH / HEIGHT
        if (x1 - x0) / (y1 - y0) < aspect:
            c, half_w = (x0 + x1) / 2, (y1 - y0) * aspect / 2
            x0, x1 = c - half_w, c + half_w
        else:
            c, half_h = (y0 + y1) / 2, (x1 - x0) / aspect / 2
            y0, y1 = c - half_h, c + half_h
        # Prefer not to look past the floor or far above the head.
        shift = max(0, y1 - by1)
        y0, y1 = y0 - shift, y1 - shift
        return x0, y0, x1, y1

    def badge(self, p, number):
        self.items.append(('badge', np.asarray(p), number))

    def svg(self, title):
        return document(WIDTH, HEIGHT, title, self.layer(self.crop()))

    def layer(self, crop, width=WIDTH, height=HEIGHT):
        """The body and its marks, drawn into a width x height box."""
        x0, y0, x1, y1 = crop
        scale = width / (x1 - x0)

        def xy(points):
            p = self.view.project(np.atleast_2d(points))
            return np.stack([(p[:, 0] - x0) * scale, (p[:, 1] - y0) * scale], axis=1), p[:, 2]

        def d_of(pts):
            return 'M' + 'L'.join(f'{x:.1f} {y:.1f}' for x, y in pts)

        body = render(self.view, crop, (width * 2, height * 2))   # 2x for high-density screens
        out = [f'<image href="data:image/webp;base64,{body}" x="0" y="0" width="{width}" height="{height}"/>']
        marks = []
        for item in self.items:
            kind = item[0]
            if kind == 'level':
                _, y, label = item
                (lx, ly), = xy([[0, y, 0]])[0][:1]
                out.append(f'<path d="M0 {ly:.1f}H{width}" stroke="{GUIDE}" stroke-width="1.2" '
                           f'stroke-dasharray="5 4" fill="none" opacity=".75"/>')
                out.append(text(width - 10, ly - 7, label, 'end', GUIDE))
            elif kind == 'ring':
                pts, depth = xy(np.vstack([item[1], item[1][:1]]))
                front = depth >= np.median(depth)
                for visible in (False, True):
                    runs, run = [], []
                    for k in range(len(pts) - 1):
                        if front[k] == visible or front[k + 1] == visible:
                            run += [pts[k], pts[k + 1]]
                        elif run:
                            runs.append(run); run = []
                    if run:
                        runs.append(run)
                    style = (f'stroke-width="3.2"' if visible else
                             f'stroke-width="2.2" stroke-dasharray="6 5" opacity=".6"')
                    for r in runs:
                        out.append(f'<path d="{d_of(r)}" fill="none" stroke="{ACCENT}" {style} '
                                   f'stroke-linecap="round" stroke-linejoin="round"/>')
            elif kind == 'path':
                pts, _ = xy(item[1])
                out.append(f'<path d="{d_of(pts)}" fill="none" stroke="{ACCENT}" stroke-width="3.2" '
                           f'stroke-linecap="round" stroke-linejoin="round"/>')
                if item[2]:
                    for end, before in ((pts[0], pts[1]), (pts[-1], pts[-2])):
                        v = end - before
                        v = v / (np.linalg.norm(v) or 1)
                        n = np.array([-v[1], v[0]]) * 9
                        marks.append(f'<path d="M{end[0] - n[0]:.1f} {end[1] - n[1]:.1f}L{end[0] + n[0]:.1f} '
                                     f'{end[1] + n[1]:.1f}" stroke="{ACCENT}" stroke-width="3.2" stroke-linecap="round"/>')
            elif kind in ('dot', 'note'):
                _, p, label, anchor, (ox, oy) = item
                (px, py), = xy(p)[0][:1]
                if kind == 'dot':
                    marks.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{ACCENT}" stroke="#fff" stroke-width="1.5"/>')
                if label:
                    dx = ox if anchor == 'start' else -ox if anchor == 'end' else 0
                    marks.append(text(px + dx, py + oy, label, anchor, INK))
            elif kind == 'angle':
                _, vertex, reference, measured, label = item
                (vx, vy), (rx, ry), (mx, my) = xy(np.vstack([vertex, reference, measured]))[0]
                out.append(f'<path d="M{vx:.1f} {vy:.1f}L{rx:.1f} {ry:.1f}" stroke="{GUIDE}" stroke-width="1.5" '
                           f'stroke-dasharray="5 4" fill="none"/>')
                out.append(f'<path d="M{vx:.1f} {vy:.1f}L{mx:.1f} {my:.1f}" stroke="{ACCENT}" stroke-width="3.2" '
                           f'stroke-linecap="round" fill="none"/>')
                a0, a1 = math.atan2(ry - vy, rx - vx), math.atan2(my - vy, mx - vx)
                r = 44 if abs(math.remainder(a1 - a0, 2 * math.pi)) > .35 else 90
                sweep = 1 if (a1 - a0) % (2 * math.pi) < math.pi else 0
                out.append(f'<path d="M{vx + r * math.cos(a0):.1f} {vy + r * math.sin(a0):.1f}A{r} {r} 0 0 {sweep} '
                           f'{vx + r * math.cos(a1):.1f} {vy + r * math.sin(a1):.1f}" stroke="{ACCENT}" '
                           f'stroke-width="2" fill="none"/>')
                mid = (a0 + a1) / 2 if abs(a1 - a0) < math.pi else (a0 + a1) / 2 + math.pi
                marks.append(text(vx + (r + 16) * math.cos(mid), vy + (r + 16) * math.sin(mid) + 4, label, 'middle', INK))
            elif kind == 'badge':
                _, p, number = item
                (bx, by), = xy(p)[0][:1]
                marks.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="11" fill="{INK}" stroke="#fff" stroke-width="2"/>'
                             f'<text x="{bx:.1f}" y="{by + 4.5:.1f}" text-anchor="middle" fill="#fff" '
                             f'style="font-size:12px">{number}</text>')
        return out + marks


def document(width, height, title, elements):
    return '\n'.join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{title}</title>',
        '<style>text{font-family:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;'
        'font-size:13px;font-weight:600}.halo{stroke:#f6f3ed;stroke-width:4px;stroke-linejoin:round;'
        'fill:#f6f3ed}</style>',
        *elements, '</svg>'])


# --------------------------------------------------------------- the measurements

def text(x, y, label, anchor, fill):
    common = f'x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"'
    return f'<text {common} class="halo">{label}</text><text {common} fill="{fill}">{label}</text>'


def circumference(y, label, *, ring=None, view=TURNED, level=None):
    d = Diagram(view)
    d.ring(ring if ring is not None else torso_ring(y))
    d.level(y, level or label)
    return d


def diagrams():
    top, nape, waist, bust, hips, crotch = (L[k] for k in ('top', 'nape', 'waist', 'bust', 'hips', 'crotch'))
    back_z = MESH.vertices[:, 2].min()
    front_z = MESH.vertices[:, 2].max()
    result = {}

    # Height: floor to crown, as taken against a wall.
    d = Diagram(SIDE)
    crown = hit([0, top + .2, 0], [0, -1, 0])
    wall = back_z - .04
    d.line([0, 0, wall], [0, top, wall])
    d.path([[0, top, wall], [0, top, crown[2]]], ends=False)
    d.dot(crown, 'crown', 'start', (8, -8))
    d.note([0, 0, wall], 'floor', 'start', (10, -6))
    d.context([0, 0, front_z], [0, top, 0])
    result['height'] = d

    result['bust'] = circumference(bust, 'bust')
    result['underbust'] = circumference(L['underbust'], 'underbust')
    result['waist'] = circumference(waist, 'natural waist')
    result['hips'] = circumference(hips, 'fullest hip')
    d = circumference(crotch - .015, 'thigh', ring=leg_ring(crotch - .015), level='top of thigh')
    d.context([0, hips, 0], [0, crotch - .25, 0])
    result['leg_circ'] = d

    ring, centre = arm_ring(1)
    d = Diagram(FRONT)
    d.ring(ring)
    d.note(centre, 'wrist bone', 'end', (-24, -16))
    d.context(centre + [0, .12, 0], centre - [0, .12, 0])
    result['wrist'] = d

    # Shoulder width: shoulder point to shoulder point across the back.
    d = Diagram(BACK)
    right, left = shoulder_tip(-1), shoulder_tip(1)
    d.line(right, left)
    d.dot(right, 'shoulder point', 'start', (4, -14))
    d.dot(left)
    d.context([0, bust - .05, 0], [0, top, 0])
    result['shoulder_w'] = d

    # Arm length: shoulder point down the outside of the arm to the wrist bone.
    d = Diagram(FRONT)
    joint, axis, across = arm_frame(M, 1)
    outer = [shoulder_tip(1)]
    for t in np.linspace(.12, 1, 18):
        r, c = arm_ring(t)
        outer.append(r[np.argmax((r - c) @ across)])
    d.path(outer)
    d.dot(outer[0], 'shoulder point', 'end', (-10, -10))
    d.dot(outer[-1], 'wrist bone', 'end', (10, 18))
    d.context([0, waist, 0])
    result['arm_length'] = d

    # Back length: nape down the spine to the waist.
    d = Diagram(BACK)
    spine = sagittal(0, lambda p: (p[:, 2] < 0) & (p[:, 1] <= nape) & (p[:, 1] >= waist))
    d.path(spine)
    d.dot(spine[0], 'nape', 'start', (10, 4))
    d.level(waist, 'natural waist')
    d.context([0, top, 0], [0, hips, 0])
    result['waist_line'] = d

    # Waist to hip and hip to crotch: vertical, at the side.
    side_x = lambda ring: ring[:, 0].max()   # noqa: E731
    for key, (upper, lower, a, b) in dict(hips_line=(waist, hips, 'natural waist', 'fullest hip'),
                                          crotch_hip_diff=(hips, crotch, 'fullest hip', 'crotch')).items():
        d = Diagram(SIDE)
        ring = torso_ring(upper)
        z = ring[np.argmax(ring[:, 0])][2]
        d.line([side_x(ring), upper, z], [side_x(ring), lower, z])
        d.level(upper, a)
        d.level(lower, b)
        d.context([0, upper + .2, 0], [0, lower - .15, 0])
        result[key] = d

    # Inseam: crotch down the inside of the leg to the floor.
    d = Diagram(FRONT)
    inner = []
    for y in np.linspace(crotch - .012, .07, 26):
        r = leg_ring(y)
        inner.append(r[np.argmin(r[:, 0])])
    inner = np.array(inner)
    inner = np.vstack([inner, [inner[-1, 0], 0, inner[-1, 2]]])
    d.path(inner)
    d.dot(inner[0], 'crotch', 'start', (10, 2))
    d.note(inner[-1], 'floor', 'start', (10, -4))
    d.context([0, hips + .05, 0], [0, 0, 0])
    result['inseam'] = d

    # Back portions of three circumferences, side line to side line.
    for key, y, label in (('back_width', bust, 'bust level'), ('waist_back_width', waist, 'natural waist'),
                          ('hip_back_width', hips, 'fullest hip')):
        d = Diagram(BACK)
        arc = half(torso_ring(y), back=True)
        d.path(arc)
        d.dot(arc[0], 'side line', 'middle', (0, 24))
        d.dot(arc[-1], 'side line', 'middle', (0, 24))
        d.level(y, label)
        d.context([0, y + .2, 0], [0, y - .2, 0])
        result[key] = d

    # Front length over the bust, and its shoulder-to-bust-point part.
    bp = bust_point(1)
    neck_base = nape - .01
    front = sagittal(bp[0], lambda p: (p[:, 2] > -.02) & (p[:, 1] >= waist) & (p[:, 1] <= neck_base))
    # One sheet of surface only: the plane can also graze the arm.
    front = front[np.abs(front[:, 0] - bp[0]) < 1e-6]
    keep = [front[0]]
    for q in front[1:]:
        if np.linalg.norm(q - keep[-1]) < .06:
            keep.append(q)
    front = np.array(keep)
    for key, lower, label in (('waist_over_bust_line', waist, 'natural waist'), ('bust_line', bust, 'bust point')):
        d = Diagram(View(60, 0))
        seg = front[front[:, 1] >= lower - 1e-6]
        d.path(seg)
        d.dot(seg[0], 'shoulder', 'end', (-10, -6))
        if key == 'bust_line':
            d.dot(bp, 'bust point', 'start', (10, 4))
        else:
            d.level(waist, 'natural waist')
        d.context([0, top - .05, 0], [0, waist - .08, 0])
        result[key] = d

    # Vertical drops, drawn beside the body in profile.
    for key, upper, lower, a, b, z in (('vert_bust_line', nape, bust, 'nape', 'bust level', front_z + .03),
                                       ('head_l', top, nape, 'crown', 'nape', back_z - .02)):
        d = Diagram(SIDE)
        d.line([0, upper, z], [0, lower, z])
        d.level(upper, a)
        d.level(lower, b)
        d.context([0, upper + .08, 0], [0, lower - .12, 0])
        result[key] = d

    # Armscye depth: shoulder level down to the armpit, on the back.
    d = Diagram(BACK)
    tip = shoulder_tip(1)
    x = tip[0] - .035
    depth = M['armscye_depth']
    z = hit([x, tip[1] - depth / 2, back_z - .2], [0, 0, 1])[2]
    d.line([x, tip[1], z], [x, tip[1] - depth, z])
    d.level(tip[1], 'shoulder level')
    d.level(tip[1] - depth, 'bottom of armpit')
    d.context([0, top, 0], [0, bust - .08, 0])
    result['armscye_depth'] = d

    # Neck width across the back of the neck base.
    d = Diagram(BACK)
    neck = torso_ring(nape - .005)
    a, b = side_points(neck)
    d.line(a, b)
    d.level(nape, 'neck base')
    d.context([0, top, 0], [0, bust, 0])
    result['neck_w'] = d

    # Point-to-point widths.
    d = Diagram(FRONT)
    d.line(bust_point(-1), bust_point(1))
    d.dot(bust_point(-1))
    d.dot(bust_point(1), 'bust point', 'start', (8, 16))
    d.context([0, nape, 0], [0, waist, 0])
    result['bust_points'] = d
    d = Diagram(BACK)
    d.line(seat_point(1), seat_point(-1))
    d.dot(seat_point(1))
    d.dot(seat_point(-1), 'fullest seat point', 'start', (8, 16))
    d.context([0, waist, 0], [0, crotch - .1, 0])
    result['bum_points'] = d

    # Angles.
    d = Diagram(FRONT, minimum=.45)
    upper, lower = torso_ring(waist), torso_ring(hips)
    w, hp = upper[np.argmax(upper[:, 0])], lower[np.argmax(lower[:, 0])]
    d.angle(w, w + [0, -(waist - hips) * 1.1, 0], hp + (hp - w) * .1, 'hip angle')
    d.context(w + [0, .12, 0], hp - [0, .1, 0], [0, waist, 0])
    result['hip_inclination'] = d
    d = Diagram(FRONT, minimum=.34)
    neck_side = side_points(torso_ring(nape - .005))[1]
    tip = shoulder_tip(1)
    d.angle(neck_side, [tip[0] + .03, neck_side[1], neck_side[2]], tip, 'slope')
    d.dot(neck_side, 'neck base', 'end', (10, -10))
    d.dot(tip, 'shoulder point', 'start', (8, 18))
    d.context([0, nape + .06, 0], [0, bust + .04, 0])
    result['shoulder_incl'] = d
    return result


def overview(parts):
    """Front, side and back with every essential measurement, numbered in measuring order."""
    from webapp.measurement_guide import GUIDE
    order = [k for k, e in GUIDE.items() if e['essential'] and k in parts]
    views = ((View(0, 0), ('bust', 'underbust', 'waist', 'hips', 'leg_circ', 'wrist', 'arm_length', 'inseam')),
             (SIDE, ('height', 'hips_line')),
             (View(180, 0), ('shoulder_w', 'waist_line')))
    panel_w, panel_h = 300, 500
    elements = []
    for index, (view, keys) in enumerate(views):
        d = Diagram(view)
        for key in keys:
            lines = [item for item in parts[key].items if item[0] in ('ring', 'path')]
            d.items += lines
            points = np.vstack([item[1] for item in lines])
            screen = view.project(points)
            # The badge sits at the measurement's outer end, away from the body's centre line.
            spot = points[np.argmax(np.abs(screen[:, 0]) + (0 if key != 'height' else -screen[:, 1]))]
            if key in ('waist_line', 'hips_line', 'inseam', 'arm_length'):
                spot = points[len(points) // 2]
            d.badge(spot, order.index(key) + 1)
        body = view.project(MESH.vertices)
        (x0, y0), (x1, y1) = body[:, :2].min(0) - .04, body[:, :2].max(0) + .04
        cx, cy, half_h = (x0 + x1) / 2, (y0 + y1) / 2, (y1 - y0) / 2
        half_w = max((x1 - x0) / 2, half_h * panel_w / panel_h)
        half_h = half_w * panel_h / panel_w
        crop = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
        elements.append(f'<g transform="translate({index * panel_w} 0)">')
        elements += d.layer(crop, panel_w, panel_h)
        elements.append('</g>')
    return document(panel_w * len(views), panel_h, 'Where each measurement is taken', elements)


def main():
    from webapp.measurement_guide import GUIDE
    made = diagrams()
    missing = [k for k in GUIDE if k not in made]
    if missing:
        raise SystemExit(f'No diagram for: {missing}')
    for key, d in made.items():
        (OUT_DIR / f'{key}.svg').write_text(d.svg(GUIDE[key]['label']), encoding='utf-8')
        print('wrote', key)
    (OUT_DIR / 'overview.svg').write_text(overview(made), encoding='utf-8')
    print('wrote overview')


if __name__ == '__main__':
    main()
