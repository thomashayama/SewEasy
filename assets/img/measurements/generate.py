"""Generate per-measurement guide diagrams from the GGG body outline.

Each output SVG shows the mean-body outline with one measurement
indicated in the accent color: ellipses for circumferences, arrows for
distances, arcs for angles. Landmark heights are computed from the
mean_all body measurements themselves, so the indicator positions match
how GarmentCode defines each measurement (see
docs/Body Measurements GarmentCode.pdf).

Run from the repo root (deps: svgpathtools, pyyaml — already installed):

    python assets/img/measurements/generate.py
"""
import math
from pathlib import Path

import yaml
from svgpathtools import svg2paths, Line

REPO = Path(__file__).resolve().parents[3]
OUTLINE_SVG = REPO / 'assets/img/ggg_outline_mean_all.svg'
BODY_YAML = REPO / 'assets/bodies/mean_all.yaml'
OUT_DIR = Path(__file__).resolve().parent

ACCENT = '#c94f4f'        # selvedge red (see gui/theme.py)
OUTLINE_STROKE = '#c5b8d4'
OUTLINE_FILL = '#fdfbff'
STROKE_W = 5

# ---------------------------------------------------------------------------
# Outline geometry

paths, _ = svg2paths(str(OUTLINE_SVG))
outline = paths[0]
XMIN, XMAX, YMIN, YMAX = outline.bbox()
M = yaml.safe_load(BODY_YAML.read_text())['body']

H = M['height']
SCALE = (YMAX - YMIN) / H          # px per cm
CX = (XMIN + XMAX) / 2


def y_of(cm_from_floor):
    """Y pixel for a height above the floor (feet = bbox bottom)"""
    return YMAX - cm_from_floor * SCALE


def px(cm):
    return cm * SCALE


def cross(y):
    """Sorted x positions where the horizontal line at y crosses the outline"""
    line = Line(complex(XMIN - 20, y), complex(XMAX + 20, y))
    hits = outline.intersect(line)
    xs = sorted(outline.point(T1).real for (T1, _, _), _ in hits)
    # Merge near-duplicate hits at segment joints
    merged = []
    for x in xs:
        if not merged or x - merged[-1] > 1.0:
            merged.append(x)
    return merged


def torso_pair(y):
    """Left/right torso outline x at height y (the pair bracketing center)"""
    xs = cross(y)
    left = max((x for x in xs if x < CX), default=CX - 50)
    right = min((x for x in xs if x > CX), default=CX + 50)
    return left, right


# Landmark heights above the floor (cm)
NAPE = H - M['head_l']
BUST = NAPE - M['vert_bust_line']
UNDERBUST = BUST - 6
WAIST = NAPE - M['waist_line']
HIP = WAIST - M['hips_line']
CROTCH = HIP - M['crotch_hip_diff']
THIGH = CROTCH - 6
SHOULDER_DROP = math.tan(math.radians(M['shoulder_incl'])) * M['shoulder_w'] / 2
SHOULDER_END = NAPE - SHOULDER_DROP

# Arm axis: right shoulder point -> hand tip (arm posed at ~45 degrees).
# Only points laterally beyond the torso qualify as the hand — otherwise
# the feet win the projection along the down-right direction.
_shoulder_y = y_of(SHOULDER_END)
_, _shoulder_x = torso_pair(y_of(NAPE - 4))
_torso_right = torso_pair(y_of(WAIST))[1]
_dir = complex(math.sin(math.radians(M['arm_pose_angle'])),
               math.cos(math.radians(M['arm_pose_angle'])))  # down-right
_samples = [outline.point(i / 2000) for i in range(2001)]
_arm_pts = [p for p in _samples if p.real > _torso_right + px(3)]
_tip = max(_arm_pts,
           key=lambda p: ((p.real - _shoulder_x) * _dir.real
                          + (p.imag - _shoulder_y) * _dir.imag))
SHOULDER_PT = (_shoulder_x, _shoulder_y)
HAND_TIP = (_tip.real, _tip.imag)
WRIST_PT = tuple(s + 0.86 * (t - s) for s, t in zip(SHOULDER_PT, HAND_TIP))
ARM_ANGLE = math.degrees(math.atan2(HAND_TIP[1] - SHOULDER_PT[1],
                                    HAND_TIP[0] - SHOULDER_PT[0]))

# ---------------------------------------------------------------------------
# SVG element builders


def ellipse(y_cm, inset=0.0, width_pair=None, ry_ratio=0.16):
    y = y_of(y_cm)
    left, right = width_pair or torso_pair(y)
    left, right = left + inset, right - inset
    rx = (right - left) / 2
    return (f'<ellipse cx="{(left + right) / 2:.0f}" cy="{y:.0f}" '
            f'rx="{rx:.0f}" ry="{rx * ry_ratio:.0f}" '
            f'fill="none" stroke="{ACCENT}" stroke-width="{STROKE_W}"/>')


def vline(x, y1_cm, y2_cm, dashed=False):
    dash = ' stroke-dasharray="14 10"' if dashed else ''
    return (f'<line x1="{x:.0f}" y1="{y_of(y1_cm):.0f}" '
            f'x2="{x:.0f}" y2="{y_of(y2_cm):.0f}" '
            f'stroke="{ACCENT}" stroke-width="{STROKE_W}"{dash} '
            f'marker-start="url(#tick)" marker-end="url(#tick)"/>')


def hline(x1, x2, y_cm, dashed=False):
    dash = ' stroke-dasharray="14 10"' if dashed else ''
    y = y_of(y_cm)
    return (f'<line x1="{x1:.0f}" y1="{y:.0f}" x2="{x2:.0f}" y2="{y:.0f}" '
            f'stroke="{ACCENT}" stroke-width="{STROKE_W}"{dash} '
            f'marker-start="url(#tick)" marker-end="url(#tick)"/>')


def seg(p1, p2, dashed=False, ticks=True):
    dash = ' stroke-dasharray="14 10"' if dashed else ''
    marks = ' marker-start="url(#tick)" marker-end="url(#tick)"' if ticks else ''
    return (f'<line x1="{p1[0]:.0f}" y1="{p1[1]:.0f}" '
            f'x2="{p2[0]:.0f}" y2="{p2[1]:.0f}" '
            f'stroke="{ACCENT}" stroke-width="{STROKE_W}"{dash}{marks}/>')


def arc(center, radius, deg1, deg2):
    a1, a2 = math.radians(deg1), math.radians(deg2)
    p1 = (center[0] + radius * math.cos(a1), center[1] + radius * math.sin(a1))
    p2 = (center[0] + radius * math.cos(a2), center[1] + radius * math.sin(a2))
    return (f'<path d="M {p1[0]:.0f} {p1[1]:.0f} '
            f'A {radius:.0f} {radius:.0f} 0 0 1 {p2[0]:.0f} {p2[1]:.0f}" '
            f'fill="none" stroke="{ACCENT}" stroke-width="{STROKE_W}"/>')


def dot(p, r=9):
    return f'<circle cx="{p[0]:.0f}" cy="{p[1]:.0f}" r="{r}" fill="{ACCENT}"/>'


def thigh_pair():
    """Cross-section of the left (viewer's left) thigh"""
    y = y_of(THIGH)
    xs = [x for x in cross(y) if abs(x - CX) < px(M['hips'] / 3.5)]
    left = [x for x in xs if x < CX]
    return (min(left), max(left)) if len(left) >= 2 else (CX - 60, CX - 10)


def bust_offset():
    return px(M['bust_points'] / 2)


# ---------------------------------------------------------------------------
# One entry per measurement: list of overlay SVG elements

lt, rt = None, None  # filled lazily below where needed

DIAGRAMS = {
    # Circumferences
    'waist': [ellipse(WAIST)],
    'bust': [ellipse(BUST)],
    'underbust': [ellipse(UNDERBUST)],
    'hips': [ellipse(HIP)],
    'leg_circ': [ellipse(THIGH, width_pair=thigh_pair(), ry_ratio=0.25)],
    'wrist': ['<g transform="rotate({:.0f} {:.0f} {:.0f})">'.format(
                  ARM_ANGLE - 90, *WRIST_PT)
              + f'<ellipse cx="{WRIST_PT[0]:.0f}" cy="{WRIST_PT[1]:.0f}" '
                f'rx="{px(M["wrist"]) / math.pi / 2 + 6:.0f}" ry="10" '
                f'fill="none" stroke="{ACCENT}" stroke-width="{STROKE_W}"/></g>'],
    # Back widths (between balance lines, shown as torso-width bars)
    'waist_back_width': [hline(*torso_pair(y_of(WAIST)), WAIST)],
    'back_width': [hline(*torso_pair(y_of(BUST)), BUST)],
    'hip_back_width': [hline(*torso_pair(y_of(HIP)), HIP)],
    # Distances
    'height': [vline(XMIN - 30, 0, H)],
    'head_l': [vline(CX + px(14), NAPE, H)],
    'neck_w': [hline(CX - px(M['neck_w'] / 2), CX + px(M['neck_w'] / 2), NAPE)],
    'shoulder_w': [seg((CX - px(M['shoulder_w'] / 2), y_of(SHOULDER_END)),
                       (CX + px(M['shoulder_w'] / 2), y_of(SHOULDER_END)))],
    'waist_line': [vline(CX, NAPE, WAIST)],
    'waist_over_bust_line': [
        seg((CX - bust_offset(), y_of(NAPE - 1)),
            (CX - bust_offset(), y_of(BUST)), ticks=False),
        seg((CX - bust_offset(), y_of(BUST)),
            (CX - bust_offset(), y_of(WAIST)), ticks=False),
        dot((CX - bust_offset(), y_of(NAPE - 1))),
        dot((CX - bust_offset(), y_of(WAIST)))],
    'bust_line': [vline(CX - bust_offset(), SHOULDER_END + M['shoulder_incl'] / 10, BUST)],
    'vert_bust_line': [vline(CX + px(6), NAPE, BUST)],
    'arm_length': [seg(SHOULDER_PT, WRIST_PT)],
    'armscye_depth': [vline(torso_pair(y_of(BUST))[1] - px(3), SHOULDER_END,
                            BUST + 3, dashed=True)],
    'bust_points': [hline(CX - bust_offset(), CX + bust_offset(), BUST),
                    dot((CX - bust_offset(), y_of(BUST))),
                    dot((CX + bust_offset(), y_of(BUST)))],
    'bum_points': [hline(CX - px(M['bum_points'] / 2),
                         CX + px(M['bum_points'] / 2), HIP),
                   dot((CX - px(M['bum_points'] / 2), y_of(HIP))),
                   dot((CX + px(M['bum_points'] / 2), y_of(HIP)))],
    'hips_line': [vline(torso_pair(y_of(HIP))[1] + 30, WAIST, HIP)],
    'crotch_hip_diff': [vline(CX, HIP, CROTCH)],
    # Angles
    'shoulder_incl': [
        seg((CX + px(M['neck_w'] / 2), y_of(NAPE)),
            (CX + px(M['shoulder_w'] / 2), y_of(SHOULDER_END))),
        seg((CX + px(M['neck_w'] / 2), y_of(NAPE)),
            (CX + px(M['shoulder_w'] / 2 + 3), y_of(NAPE)), dashed=True,
            ticks=False),
        arc((CX + px(M['neck_w'] / 2), y_of(NAPE)), px(9), 0,
            M['shoulder_incl'])],
    'hip_inclination': [
        seg((torso_pair(y_of(WAIST))[1], y_of(WAIST)),
            (torso_pair(y_of(HIP))[1], y_of(HIP))),
        seg((torso_pair(y_of(WAIST))[1], y_of(WAIST)),
            (torso_pair(y_of(WAIST))[1], y_of(HIP - 2)), dashed=True,
            ticks=False),
        arc((torso_pair(y_of(WAIST))[1], y_of(WAIST)), px(14),
            90 - M['hip_inclination'], 90)],
    'arm_pose_angle': [
        seg(SHOULDER_PT, WRIST_PT, ticks=False),
        seg(SHOULDER_PT, (SHOULDER_PT[0], SHOULDER_PT[1] + px(26)),
            dashed=True, ticks=False),
        arc(SHOULDER_PT, px(15), 90 - M['arm_pose_angle'], 90)],
}

# ---------------------------------------------------------------------------
# Write the SVGs

MARGIN = 60
VIEW = (f'{XMIN - MARGIN:.0f} {YMIN - MARGIN:.0f} '
        f'{XMAX - XMIN + 2 * MARGIN:.0f} {YMAX - YMIN + 2 * MARGIN:.0f}')

outline_d = outline.d()
TEMPLATE = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEW}">
  <defs>
    <marker id="tick" markerWidth="4" markerHeight="12" refX="2" refY="6"
            orient="auto">
      <rect x="1" y="0" width="2.5" height="12" fill="{ACCENT}"/>
    </marker>
  </defs>
  <path d="{outline_d}" fill="{OUTLINE_FILL}" stroke="{OUTLINE_STROKE}"
        stroke-width="2.5"/>
  {{overlay}}
</svg>
'''


def main():
    for key, elements in DIAGRAMS.items():
        svg = TEMPLATE.format(overlay='\n  '.join(elements))
        (OUT_DIR / f'{key}.svg').write_text(svg, encoding='utf-8')
    print(f'Wrote {len(DIAGRAMS)} diagrams to {OUT_DIR}')


if __name__ == '__main__':
    main()
