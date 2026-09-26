"""Procedural hair for the 3D preview, shaped on a fitted mannequin.

Hair is described by a small JSON-able dict kept with a body profile (see
``DEFAULT_HAIR``) and built here into a triangle mesh on the fitted body, so
every body gets hair that fits its own head. It is drawn only: it takes no
part in cloth collision. Coordinates are the body's metres, y up, facing +z;
the person's left is +x.

The mesh is assembled from up to four parts:

* a scalp cap: the head above a hairline (forehead, temples, over the ears,
  nape) cut out along that curve and lifted along the surface normals, fuller
  on top and feathered at the hairline; a fringe lowers the hairline over the
  forehead, and coily hair lifts it into a rounded shape instead;
* a curtain: longer loose hair falling from the widest part of the head, as a
  thick sheet that clears the neck and back and rests on the shoulders;
* a bun or a ponytail for tied hair.

Strands run along each part's ``uv`` v coordinate; the preview's shader
draws them from it.
"""
import math

import numpy as np

# Where hair ends, as positions on the length scale; the fractions place a
# stop between the crown and the landmarks the measurements give.
LENGTH_STOPS = ('Bald', 'Buzz', 'Short', 'Ear', 'Chin', 'Shoulder', 'Mid-back', 'Waist')
MAX_LENGTH = len(LENGTH_STOPS) - 1

TEXTURES = {'straight': 'Straight', 'wavy': 'Wavy', 'curly': 'Curly', 'coily': 'Coily'}
FRINGES = {'none': 'None', 'full': 'Full', 'side': 'Side-swept'}
PARTS = {'none': 'Swept back', 'left': 'Left', 'center': 'Centre', 'right': 'Right'}
TIES = {'none': 'Loose', 'bun': 'Bun', 'low_bun': 'Low bun', 'ponytail': 'Ponytail'}

# Natural shades, darkest first; any '#rrggbb' is accepted.
HAIR_COLORS = {
    '#16120f': 'Black', '#2b1f19': 'Soft black', '#3a2a22': 'Dark brown', '#5a3d2b': 'Brown',
    '#7d5a3c': 'Light brown', '#6e3421': 'Auburn', '#9a4a26': 'Copper', '#b98452': 'Dark blonde',
    '#d2ac72': 'Golden blonde', '#e5d3ad': 'Platinum', '#8c8781': 'Grey', '#dcd9d4': 'White',
}

DEFAULT_HAIR = dict(style='short', color='#3a2a22', length=2.0, volume=.5, texture='straight',
                    fringe='none', part='none', tie='none', recede=0.0)

# Starting points; any of them can then be adjusted.
PRESETS = {
    'bald': ('Bald', dict(length=0.0)),
    'buzz': ('Buzz cut', dict(length=1.0, volume=.3)),
    'short': ('Short', dict(length=2.0, volume=.5)),
    'side_part': ('Side part', dict(length=2.6, volume=.6, part='left')),
    'curly_short': ('Short curls', dict(length=2.5, volume=.7, texture='curly')),
    'afro': ('Afro', dict(length=3.6, volume=.85, texture='coily')),
    'bob': ('Bob', dict(length=4.0, volume=.5, part='center')),
    'bangs': ('Bob with bangs', dict(length=4.0, volume=.5, fringe='full')),
    'shoulder': ('Shoulder length', dict(length=5.0, volume=.55, texture='wavy', part='left')),
    'long': ('Long', dict(length=6.3, volume=.5, part='center')),
    'long_wavy': ('Long waves', dict(length=6.3, volume=.65, texture='wavy', part='right')),
    'bun': ('Bun', dict(length=5.5, volume=.5, tie='bun')),
    'ponytail': ('Ponytail', dict(length=6.0, volume=.5, tie='ponytail')),
}


def preset(key: str, color: str = None) -> dict:
    """A preset's full description, in `color` or the default one."""
    hair = dict(DEFAULT_HAIR, **PRESETS[key][1], style=key)
    if color:
        hair['color'] = color
    return clean_hair(hair)


def matching_preset(hair: dict):
    """The preset these values are, if they are one unchanged."""
    shape = {k: v for k, v in clean_hair(hair).items() if k not in ('style', 'color')}
    for key in PRESETS:
        if {k: v for k, v in preset(key).items() if k not in ('style', 'color')} == shape:
            return key
    return None


def clean_hair(hair) -> dict:
    """A valid description; anything missing or unknown takes its default."""
    hair = hair if isinstance(hair, dict) else {}
    out = dict(DEFAULT_HAIR)

    def number(key, low, high):
        try:
            value = float(hair[key])
        except (KeyError, TypeError, ValueError):
            return
        if math.isfinite(value):
            out[key] = round(min(high, max(low, value)), 3)

    number('length', 0., MAX_LENGTH)
    number('volume', 0., 1.)
    number('recede', 0., 1.)
    for key, allowed in (('texture', TEXTURES), ('fringe', FRINGES), ('part', PARTS), ('tie', TIES)):
        if hair.get(key) in allowed:
            out[key] = hair[key]
    color = hair.get('color')
    if isinstance(color, str) and len(color) == 7 and color[0] == '#':
        try:
            int(color[1:], 16)
            out['color'] = color.lower()
        except ValueError:
            pass
    style = hair.get('style')
    out['style'] = style if style in PRESETS or style == 'custom' else out['style']
    return out


def has_hair(hair) -> bool:
    return clean_hair(hair)['length'] >= .15


# --------------------------------------------------------------------------
# Geometry

REFERENCE_HALF_WIDTH = .08     # the neutral mannequin's skull, at temple height
# Hair on the back and shoulders lies over the garment being draped, which the
# hair cannot see: keep this far (m) off the skin there.
GARMENT_ROOM = .022

# Hairline depth below the crown (m, reference head) by angle from the front:
# forehead, temple recess, sideburn in front of the ear, over the ear, nape.
HAIRLINE = np.array([[0, .061], [.5, .066], [.9, .084], [1.2, .124], [1.36, .117], [1.55, .103],
                     [1.82, .106], [2.1, .138], [2.55, .172], [math.pi, .19]])


def _smooth(edge0, edge1, x):
    t = np.clip((np.asarray(x, dtype=float) - edge0) / (edge1 - edge0), 0., 1.)
    return t * t * (3 - 2 * t)


def _hairline(theta):
    a = np.abs(theta)
    i = np.clip(np.searchsorted(HAIRLINE[:, 0], a) - 1, 0, len(HAIRLINE) - 2)
    a0, d0 = HAIRLINE[i, 0], HAIRLINE[i, 1]
    a1, d1 = HAIRLINE[i + 1, 0], HAIRLINE[i + 1, 1]
    return d0 + (d1 - d0) * _smooth(0, 1, (a - a0) / (a1 - a0))


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _noise(p, frequency):
    """Smooth pseudo-random values in [-1, 1] over 3D points."""
    q = np.asarray(p) * frequency
    return (np.sin(q[..., 0] * 1.7 + np.sin(q[..., 1] * 2.3)) * np.sin(q[..., 1] * 1.3 + q[..., 2] * .7)
            + np.sin(q[..., 2] * 2.1 + np.sin(q[..., 0] * 1.1))) / 2


class Head:
    """Where the head is: crown height, a centre inside the skull, a size factor."""

    def __init__(self, vertices):
        v = vertices
        self.top = float(v[:, 1].max())

        def band(depth, half=.006):
            return v[(np.abs(self.top - depth - v[:, 1]) < half) & (np.abs(v[:, 0]) < .13)]

        skull, temples = band(.05), band(.08)
        x0, x1 = temples[:, 0].min(), temples[:, 0].max()
        z0, z1 = skull[:, 2].min(), skull[:, 2].max()
        self.half_width = (x1 - x0) / 2
        self.scale = self.half_width / REFERENCE_HALF_WIDTH
        self.centre = np.array([(x0 + x1) / 2, self.top - .1 * self.scale, (z0 + z1) / 2])
        self.back = float(z0)


def _vertex_normals(vertices, faces):
    normals = np.zeros_like(vertices)
    corners = vertices[faces]
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    for k in range(3):
        np.add.at(normals, faces[:, k], face_normals)
    return _unit(normals)


def _landmarks(head, measurements):
    """Heights where hair of each length ends, from the crown down."""
    s, top = head.scale, head.top
    m = measurements or {}
    head_l = float(m.get('head_l', 26.3)) / 100
    back = float(m.get('waist_line', 36.9)) / 100
    nape = top - head_l
    return np.array([top, top, top - .06 * s, top - .15 * s, top - .235 * s,
                     nape - .03, nape - .5 * back, nape - back + .03])


class _Parts:
    """Mesh parts collected into one set of arrays."""

    def __init__(self):
        self.points, self.uv, self.shade, self.faces, self.count = [], [], [], [], 0

    def add(self, points, uv, shade, faces):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        self.points.append(points)
        self.uv.append(np.asarray(uv, dtype=float).reshape(-1, 2))
        self.shade.append(np.broadcast_to(np.asarray(shade, dtype=float), (len(points),)).copy())
        self.faces.append(np.asarray(faces, dtype=np.int64).reshape(-1, 3) + self.count)
        self.count += len(points)


def hair_mesh(vertices, faces, hair, measurements=None, normals=None):
    """The hair mesh for a description on a body, or None for no hair.

    Returns dict(positions (n,3), uv (n,2), shade (n,), faces (m,3),
    texture) with float32/int32 arrays; `shade` darkens the hair's
    underside and `texture` indexes TEXTURES.
    """
    hair = clean_hair(hair)
    if not has_hair(hair):
        return None
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int64)
    normals = _vertex_normals(vertices, faces) if normals is None else np.asarray(normals, dtype=float)
    head = Head(vertices)
    stops = _landmarks(head, measurements)
    parts = _Parts()
    tied = hair['tie'] != 'none'
    coily = hair['texture'] == 'coily' and not tied
    cap = _cap(vertices, faces, normals, head, hair, coily, tied)
    if cap is None:
        return None
    parts.add(*cap)
    length = hair['length']
    if tied:
        _tie(parts, vertices, head, hair, stops)
    elif not coily and _end_height(length, stops) < head.top - .085 * head.scale - .015:
        body = _RadialMap(vertices, head, _end_height(length, stops))
        _curtain(parts, head, hair, stops, body, cap[0])
    points = np.concatenate(parts.points)
    return dict(positions=points.astype(np.float32), uv=np.concatenate(parts.uv).astype(np.float32),
                shade=np.concatenate(parts.shade).astype(np.float32),
                faces=np.concatenate(parts.faces).astype(np.int32),
                texture=list(TEXTURES).index(hair['texture']))


def _end_height(length, stops):
    """Where hair of this length ends."""
    return float(np.interp(length, np.arange(len(stops)), stops))


def _hairline_depth(theta, hair, head, loose):
    """Depth of the hairline below the crown (m) by angle from the front."""
    s = head.scale
    depth = _hairline(theta)
    a = np.abs(theta)
    # A receding hairline rises at the temples first, then at the front.
    recede = hair['recede'] * (.022 + .03 * np.exp(-((a - .72) / .28) ** 2)) * (1 - _smooth(.9, 1.3, a))
    depth = np.maximum(depth - recede, .018)
    if loose and hair['fringe'] != 'none' and hair['length'] >= 1.8:
        if hair['fringe'] == 'full':
            fringe = .097 - .012 * _smooth(.45, .95, a)
        else:
            # Swept away from the part: longest on the far side of the forehead.
            away = -1. if hair['part'] == 'left' else 1.
            fringe = .07 + .033 * _smooth(-.95, .7, np.sign(theta) * a * away * -1)
        fringe = np.where(a < 1.05, fringe * (1 - _smooth(.85, 1.05, a)) + depth * _smooth(.85, 1.05, a), 0)
        depth = np.maximum(depth, fringe)
    return depth * s


def _cap(vertices, faces, normals, head, hair, coily, tied):
    s, top = head.scale, head.top
    cx, cy, cz = head.centre
    depth = top - vertices[:, 1]
    near = (depth < .26 * s) & (np.abs(vertices[:, 0] - cx) < .13 * s)
    theta = np.arctan2(vertices[:, 0] - cx, vertices[:, 2] - cz)
    loose = not tied
    above = np.full(len(vertices), -1.)
    above[near] = _hairline_depth(theta[near], hair, head, loose) - depth[near]
    natural = np.full(len(vertices), -1.)
    natural[near] = _hairline(theta[near]) * s - depth[near]
    # Cut along the hairline itself, not along the mesh's triangles, so the
    # edge is as smooth as the hairline curve.
    inside = above > 0
    candidates = faces[inside[faces].any(axis=1)]
    points, norms, rise, fringe, out_faces = [], [], [], [], []
    index, cut = {}, {}

    def vertex(i):
        if i not in index:
            index[i] = len(points)
            points.append(vertices[i]); norms.append(normals[i]); rise.append(above[i])
            fringe.append(natural[i] <= 0)
        return index[i]

    def crossing(i, j):
        key = (i, j) if i < j else (j, i)
        if key not in cut:
            t = above[i] / (above[i] - above[j])
            points.append(vertices[i] + (vertices[j] - vertices[i]) * t)
            n = normals[i] + (normals[j] - normals[i]) * t
            norms.append(n / max(np.linalg.norm(n), 1e-12))
            rise.append(0.)
            fringe.append((natural[i] + (natural[j] - natural[i]) * t) <= 0)
            cut[key] = len(points) - 1
        return cut[key]

    for face in candidates.tolist():
        flags = [inside[i] for i in face]
        polygon = []
        for k in range(3):
            here, following = face[k], face[(k + 1) % 3]
            if flags[k]:
                polygon.append(vertex(here))
            if flags[k] != flags[(k + 1) % 3]:
                polygon.append(crossing(here, following))
        for k in range(1, len(polygon) - 1):
            out_faces.append((polygon[0], polygon[k], polygon[k + 1]))
    if not out_faces:
        return None
    p, n = np.array(points), _unit(np.array(norms))
    rise, fringe = np.array(rise), np.array(fringe)
    d = top - p[:, 1]
    crown = 1 - _smooth(0, .1 * s, d)       # volume sits on top; the hairline lies flat
    length, volume = hair['length'], hair['volume']
    if tied:
        thickness = (.0035 + .002 * volume) * np.ones(len(p))
    elif length <= 1:
        thickness = .0035 * length * np.ones(len(p))
    elif length <= 2:
        thickness = .0035 + (length - 1) * (.0025 + .011 * crown)
    else:
        thickness = .006 + (.011 + .009 * min(length - 2, 2) / 2) * crown
    thickness = thickness * (.55 + .9 * volume) * {'straight': 1, 'wavy': 1.15, 'curly': 1.5, 'coily': 1.5}[hair['texture']]
    # A fringe lies over the forehead: no crown volume, a blunt edge.
    thickness = np.where(fringe, (.005 + .004 * volume) * (1 + .3 * (hair['texture'] != 'straight')), thickness)
    feather = np.where(fringe, np.maximum(.55, _smooth(0, .006 * s, rise)), np.maximum(.12, _smooth(0, .016 * s, rise)))
    if loose and hair['part'] != 'none' and length > 1.4:
        # A parting: the hair dips to the scalp along a line from the forehead to the crown.
        xp = cx + {'left': .032, 'center': 0., 'right': -.032}[hair['part']] * s
        along = _smooth(cz - .045 * s, cz + .01 * s, p[:, 2]) * (1 - _smooth(.085 * s, .1 * s, d)) * (~fringe)
        thickness = thickness * (1 - .6 * along * np.exp(-((p[:, 0] - xp) / (.0045 * s)) ** 2))
    if hair['texture'] in ('curly', 'coily') and not tied:
        thickness = thickness * (1 + .14 * _noise(p, 90))
    lift = thickness * feather * s
    if coily:
        lifted = _afro(p, n, head, hair, rise)
    else:
        lifted = p + n * lift[:, None]
    uv = _cap_flow(lifted, head, hair, fringe, tied)
    shade = .82 + .18 * _smooth(0, .03 * s, rise)
    return lifted, uv, shade, np.array(out_faces)


def _afro(p, n, head, hair, rise):
    """Coily hair grows outward: lift the scalp onto a rounded shape."""
    s = head.scale
    centre = head.centre + [0, .012 * s, -.01 * s]
    extra = (.008 + .016 * max(hair['length'] - 1, 0)) * (.6 + .8 * hair['volume']) * s
    q = p - centre
    radius = np.linalg.norm(q, axis=1)
    direction = q / radius[:, None]
    ellipsoid = np.array([head.half_width + extra * .85, .11 * s + extra, .105 * s + extra * .95])
    reach = 1 / np.sqrt(((direction / ellipsoid) ** 2).sum(axis=1))
    reach = reach * (1 + .07 * _noise(p, 70))
    outward = _unit(direction * .7 + n * .3)
    # Rounded down to the hairline over a distance that grows with the size.
    height = np.maximum(reach - radius, .006 * s) * _smooth(0, .02 * s + .9 * extra, rise) + .003 * s
    return p + outward * height[:, None]


def _cap_flow(points, head, hair, fringe, tied):
    """Strand coordinates: across (u) and along (v) the way hair is combed."""
    centre = head.centre
    if tied:
        pole = _tie_direction(hair)
    else:
        pole = _unit({'none': [0, .55, .85], 'left': [.38, 1, -.15], 'center': [0, 1, -.1],
                      'right': [-.38, 1, -.15]}[hair['part']])
    radius = .085 * head.scale
    q = points - centre
    e1 = _unit(np.cross([0, 1, 0] if abs(pole[1]) < .9 else [1, 0, 0], pole))
    e2 = np.cross(pole, e1)
    along = np.arccos(np.clip(_unit(q) @ pole, -1, 1))
    around = np.arctan2(q @ e2, q @ e1)
    uv = np.stack([around * radius * np.sin(np.maximum(along, .2)), along * radius], axis=1)
    # A fringe falls straight down over the forehead.
    uv[fringe] = np.stack([points[fringe, 0], head.top - points[fringe, 1]], axis=1)
    return uv


class _RadialMap:
    """How far the body reaches from the head's vertical axis, by angle and height."""

    BINS = 96
    STEP = .01

    def __init__(self, vertices, head, bottom):
        cx, _, cz = head.centre
        self.top = head.top - .06 * head.scale
        self.rows = int(math.ceil((self.top - bottom) / self.STEP)) + 4
        keep = (vertices[:, 1] <= self.top + .02) & (vertices[:, 1] >= self.top - self.rows * self.STEP)
        v = vertices[keep]
        dx, dz = v[:, 0] - cx, v[:, 2] - cz
        r = np.hypot(dx, dz)
        near = r < .34
        a = ((np.arctan2(dx, dz)[near] + math.pi) / (2 * math.pi) * self.BINS).astype(int) % self.BINS
        y = np.clip(((self.top - v[near, 1]) / self.STEP).astype(int), 0, self.rows - 1)
        grid = np.zeros((self.BINS, self.rows))
        np.maximum.at(grid, (a, y), r[near])
        for _ in range(3):      # fill gaps between vertices
            grown = np.maximum(grid, np.maximum(np.roll(grid, 1, 0), np.roll(grid, -1, 0)))
            grown[:, 1:] = np.maximum(grown[:, 1:], grid[:, :-1])
            grown[:, :-1] = np.maximum(grown[:, :-1], grid[:, 1:])
            grid = np.where(grid > 0, grid, grown)
        self.grid = grid

    def reach(self, theta, y):
        a = int(round((theta + math.pi) / (2 * math.pi) * self.BINS)) % self.BINS
        row = int(np.clip((self.top - y) / self.STEP, 0, self.rows - 1))
        return float(self.grid[a, row])


def _curtain(parts, head, hair, stops, body, cap_points):
    """Loose hair below the ears: a thick sheet falling from the widest part of
    the head, clearing the neck and back and resting on the shoulders."""
    s = head.scale
    cx, _, cz = head.centre
    length, volume, texture = hair['length'], hair['volume'], hair['texture']
    y_top = head.top - .07 * s
    y_len = _end_height(length, stops)
    front = 1.02
    cols = 64
    unwrapped = np.linspace(front, 2 * math.pi - front, cols)       # continuous across the back
    thetas = np.where(unwrapped > math.pi, unwrapped - 2 * math.pi, unwrapped)
    # The cap's outer radius at the top of the curtain, per column.
    near = np.abs(cap_points[:, 1] - y_top) < .014 * s
    cp = cap_points[near]
    cap_theta = np.arctan2(cp[:, 0] - cx, cp[:, 2] - cz)
    cap_r = np.hypot(cp[:, 0] - cx, cp[:, 2] - cz)
    thick = (.009 + .013 * volume) * {'straight': 1, 'wavy': 1.15, 'curly': 1.45, 'coily': 1.5}[texture] * s
    # Hair just below the ears lies close; full thickness comes with length.
    thick *= .25 + .75 * float(_smooth(.03, .15, y_top - y_len))
    flare = {'straight': .02, 'wavy': .06, 'curly': .14, 'coily': .14}[texture] * (.4 + 1.2 * volume)
    step = .01
    heights = np.arange(y_top, y_len - step, -step)
    radius = np.zeros((cols, len(heights)))
    angle = np.zeros((cols, len(heights)))
    floor = np.zeros((cols, len(heights)))      # the closest the hair may come to the body
    ends = np.zeros(cols)
    shoulder, nape = stops[5], stops[5] + .03
    for c, theta in enumerate(thetas):
        diff = np.abs((cap_theta - theta + math.pi) % (2 * math.pi) - math.pi)
        r = float(cap_r[diff < .12].max()) if (diff < .12).any() else body.reach(theta, y_top) + thick
        r -= .003
        # Hair beside the face stops at the shoulders; behind them it falls
        # down the back, gathering toward the spine rather than fanning out.
        side = _smooth(2.25, 1.7, abs(theta))
        own_end = y_len + (max(y_len, shoulder + .01) - y_len) * side
        behind = (theta - math.copysign(math.pi, theta))
        end = heights[-1]
        for k, y in enumerate(heights):
            t = math.copysign(math.pi, theta) + behind * (1 - .42 * float(_smooth(nape + .02, nape - .14, y)))
            reach = body.reach(t, y)
            # Below the nape hair lies over clothes, not skin: leave room for them.
            clear = .004 + GARMENT_ROOM * float(_smooth(nape + .03, nape - .05, y))
            if reach + clear - r > .022 and y < y_top - .04:
                end = y      # a shelf, like the top of a shoulder: the hair rests here
                radius[c, k:], angle[c, k:], floor[c, k:] = r, t, r
                break
            # Hair follows the head in and out gently, never into the body,
            # and leaves room for its own thickness where it can.
            r = min(max(reach + clear + thick, r - .45 * step), r + .8 * step)
            r = max(r, reach + clear) + flare * step * float(_smooth(0, .06, y_top - y))
            radius[c, k], angle[c, k], floor[c, k] = r, t, reach + clear
        ends[c] = max(end, own_end)
    # Ends shift smoothly from column to column, never below where hair rests.
    shelf = ends.copy()
    kernel = np.exp(-np.linspace(-2, 2, 7) ** 2)
    kernel /= kernel.sum()
    smoothed = np.convolve(np.pad(ends, 3, mode='edge'), kernel, mode='valid')
    ends = np.maximum(smoothed, shelf)
    if texture != 'straight':
        ends = ends + .012 * np.sin(unwrapped * 9.7) * (texture != 'wavy') + .006 * np.sin(unwrapped * 5.3)
    ends = np.minimum(ends, y_top - .02)
    rows = int(np.clip((y_top - ends.min()) / .012, 6, 52))
    fraction = np.linspace(0, 1, rows)
    outer = np.zeros((cols, rows, 3)); inner = np.zeros((cols, rows, 3)); uv = np.zeros((cols, rows, 2))
    wave = {'straight': (0, 1), 'wavy': (.005, .075), 'curly': (.008, .032), 'coily': (.008, .03)}[texture]
    for c, theta0 in enumerate(thetas):
        ys = y_top - (y_top - ends[c]) * fraction
        r = np.interp(-ys, -heights, radius[c])
        theta = np.interp(-ys, -heights, angle[c])
        down = y_top - ys
        tip = _smooth(ends[c] + .05, ends[c], ys)             # 0 above the last 5 cm, 1 at the end
        low = np.interp(-ys, -heights, floor[c]) + .002
        r = r + (np.minimum(low, r) - r) * .85 * tip ** 2
        amplitude = wave[0] * s * _smooth(0, .05, down)
        r = r + amplitude * np.sin(2 * math.pi * down / wave[1] + theta * 3)
        t = theta + amplitude / np.maximum(r, .05) * .8 * np.cos(2 * math.pi * down / wave[1] + theta * 5)
        edge = .35 + .65 * float(_smooth(0, 5, min(c, cols - 1 - c)))
        width = thick * (1 - .85 * tip) * edge
        for grid, rr in ((outer, r), (inner, r - width)):
            grid[c, :, 0] = cx + rr * np.sin(t)
            grid[c, :, 1] = ys
            grid[c, :, 2] = cz + rr * np.cos(t)
        uv[c, :, 0] = unwrapped[c] * .1 * s
        uv[c, :, 1] = .1 * s + down
    index = np.arange(cols * rows).reshape(cols, rows)
    a, b, c_, d = index[:-1, :-1], index[1:, :-1], index[:-1, 1:], index[1:, 1:]
    quads = np.stack([np.stack([a, c_, b], -1), np.stack([b, c_, d], -1)], 2).reshape(-1, 3)
    n = cols * rows
    rim_faces = []
    last = index[:, -1]
    for i in range(cols - 1):      # the ends: outer to inner
        rim_faces += [(last[i], last[i + 1], n + last[i]), (last[i + 1], n + last[i + 1], n + last[i])]
    for column in (index[0], index[-1]):      # the front edges beside the face
        for k in range(rows - 1):
            rim_faces += [(column[k], n + column[k], column[k + 1]), (column[k + 1], n + column[k], n + column[k + 1])]
    points = np.concatenate([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    shade = np.concatenate([np.ones(n), np.full(n, .5)])
    parts.add(points, np.concatenate([uv.reshape(-1, 2)] * 2), shade,
              np.concatenate([quads, quads[:, ::-1] + n, np.array(rim_faces, dtype=np.int64).reshape(-1, 3)]))


def _tie_direction(hair):
    return _unit({'bun': [0, .75, -.66], 'low_bun': [0, -.12, -1], 'ponytail': [0, .32, -1]}[hair['tie']])


def _skull_point(vertices, head, direction):
    """Where a ray from the head's centre leaves the skull."""
    q = vertices - head.centre
    distance = np.linalg.norm(q, axis=1)
    close = (distance < .16 * head.scale) & (_unit(q) @ direction > .985)
    reach = distance[close].max() if close.any() else .09 * head.scale
    return head.centre + direction * reach


def _tie(parts, vertices, head, hair, stops):
    s = head.scale
    direction = _tie_direction(hair)
    root = _skull_point(vertices, head, direction) + direction * .004 * s
    length, volume = hair['length'], hair['volume']
    if hair['tie'] in ('bun', 'low_bun'):
        size = (.022 + .0045 * min(length, MAX_LENGTH)) * (.8 + .4 * volume) * s
        radii = np.array([size, size, size * .78])
        parts.add(*_ellipsoid(root + direction * radii[2] * .6, radii, direction))
        return
    # A ponytail: a tapering tube from the tie, curving back and falling under gravity.
    end = _end_height(length, stops)
    body = _RadialMap(vertices, head, end - .05)
    cx, _, cz = head.centre
    base = (.015 + .011 * volume) * s
    path, tangent, p = [root], direction.copy(), root.copy()
    travelled, total = 0., max(root[1] - end, .08) + .04
    while travelled < total and len(path) < 200:
        tangent = _unit(tangent + np.array([0, -.7, 0]))
        p = p + tangent * .01
        theta = math.atan2(p[0] - cx, p[2] - cz)
        r = math.hypot(p[0] - cx, p[2] - cz)
        room = GARMENT_ROOM * float(_smooth(stops[5] + .06, stops[5] - .02, p[1]))
        need = body.reach(theta, p[1]) + base + .004 + room if p[1] < head.top - .06 * s else 0
        if p[1] < head.top - .2 * s:
            need = max(need, r - .5 * .01)       # below the head it settles against the back
        if r < need or p[1] < head.top - .2 * s:
            p = np.array([cx + need * math.sin(theta), p[1], cz + need * math.cos(theta)])
        travelled += .01
        path.append(p)
    path = np.array(path)
    f = np.linspace(0, 1, len(path))
    radius = base * (.7 + .55 * _smooth(0, .12, f)) * (1 - .78 * _smooth(.5, 1, f))
    parts.add(*_tube(path, radius))


def _ellipsoid(centre, radii, axis, rows=14, cols=28):
    """An ellipsoid whose shortest radius lies along `axis`, swirled like a bun."""
    e1 = _unit(np.cross([0, 1, 0] if abs(axis[1]) < .9 else [1, 0, 0], axis))
    e2 = np.cross(axis, e1)
    lat = np.linspace(-math.pi / 2, math.pi / 2, rows + 1)[:, None]
    lon = np.linspace(0, 2 * math.pi, cols + 1)[None, :]
    local = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat) * np.ones_like(lon)], -1)
    points = centre + (local[..., 0:1] * radii[0] * e1 + local[..., 1:2] * radii[1] * e2 + local[..., 2:3] * radii[2] * axis)
    uv = np.stack([lat * radii[0] * np.ones_like(lon), lon * radii[0] * np.cos(lat)], -1)
    index = np.arange((rows + 1) * (cols + 1)).reshape(rows + 1, cols + 1)
    a, b, c, d = index[:-1, :-1], index[:-1, 1:], index[1:, :-1], index[1:, 1:]
    faces = np.stack([np.stack([a, c, b], -1), np.stack([b, c, d], -1)], 2).reshape(-1, 3)
    return points.reshape(-1, 3), uv.reshape(-1, 2), 1., faces


def _tube(path, radius, sides=12):
    tangents = _unit(np.gradient(path, axis=0))
    normal = _unit(np.cross(tangents[0], [1, 0, 0]))
    rings, uv = [], []
    around = np.linspace(0, 2 * math.pi, sides + 1)
    distance = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    for k, (p, t) in enumerate(zip(path, tangents)):
        normal = _unit(normal - t * (normal @ t))       # parallel transport
        binormal = np.cross(t, normal)
        rings.append(p + radius[k] * (np.cos(around)[:, None] * normal + np.sin(around)[:, None] * binormal))
        uv.append(np.stack([around * radius[0], np.full(sides + 1, distance[k])], -1))
    index = np.arange(len(path) * (sides + 1)).reshape(len(path), sides + 1)
    a, b, c, d = index[:-1, :-1], index[:-1, 1:], index[1:, :-1], index[1:, 1:]
    faces = np.stack([np.stack([a, b, c], -1), np.stack([b, d, c], -1)], 2).reshape(-1, 3)
    return np.concatenate(rings), np.concatenate(uv), 1., faces


def covered_head(panel_names) -> bool:
    """A hood covers the head: hair would show through it."""
    return any('hood' in str(name).lower() for name in panel_names)
