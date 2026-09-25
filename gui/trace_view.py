"""Pattern projector: the current pattern at true scale on a projector or TV.

The studio hands its drafted pieces to /trace through the browser's user
storage: outlines as polylines in centimetres, in the studio's own cutting
layout, with button and zipper marks assigned to their pieces. The page is a
browser-only tool (trace_view.js): calibration against four corner squares,
moving and turning pieces, and every drawing step run locally, so nothing
crosses the connection while you work at the cutting table.
"""
import json
import math
from pathlib import Path
from xml.etree import ElementTree

from nicegui import app, ui

HERE = Path(__file__).parent
STORAGE_KEY = 'trace_pattern'
# A curve's polyline samples every 2 mm: far finer than a pencil line.
SAMPLE_CM = 0.2
DIGITS = 3   # 0.01 mm

for name in ('trace_view.js', 'trace_geometry.js', 'trace_view.css'):
    app.add_static_file(local_file=HERE / name, url_path=f'/trace-assets/{name}', max_cache_age=0)


def _point(z):
    return [round(z.real, DIGITS), round(z.imag, DIGITS)]


def _curve_points(segment):
    """Points from a curve's start (not its end) no more than SAMPLE_CM apart.

    A curve's parameter does not run at constant speed, so evenly spaced
    parameters are only the start: any gap still too long is halved.
    """
    count = max(4, math.ceil(segment.length() / SAMPLE_CM))
    ts = [i / count for i in range(count + 1)]
    points = [segment.point(t) for t in ts]
    i = 0
    while i < len(ts) - 1:
        if abs(points[i + 1] - points[i]) > SAMPLE_CM and ts[i + 1] - ts[i] > 1e-6:
            t = (ts[i] + ts[i + 1]) / 2
            ts.insert(i + 1, t)
            points.insert(i + 1, segment.point(t))
        else:
            i += 1
    return points[:-1]


def polyline(path):
    """A closed svgpathtools path as polyline points in cm. Corners stay exact; curves are sampled."""
    points = []
    for segment in path:
        if type(segment).__name__ == 'Line':
            points.append(_point(segment.start))
        else:
            points.extend(_point(z) for z in _curve_points(segment))
    return points


def _number(element, key):
    try:
        return float(element.get(key))
    except (TypeError, ValueError):
        return None


def markers(svg_file):
    """Button seats, buttonholes and zipper marks: the top-level circles, lines and rects of the studio SVG.

    The fabric fills' own circles and lines live in <defs> and are skipped.
    """
    result = []
    for element in ElementTree.parse(svg_file).getroot():
        tag = element.tag.rsplit('}', 1)[-1]
        if tag == 'circle':
            values = [_number(element, k) for k in ('cx', 'cy', 'r')]
            kind = 'circle'
        elif tag == 'line':
            values = [_number(element, k) for k in ('x1', 'y1', 'x2', 'y2')]
            kind = 'line'
        elif tag == 'rect':
            values = [_number(element, k) for k in ('x', 'y', 'width', 'height')]
            kind = 'rect'
        else:
            continue
        if None not in values:
            mark = dict(kind=kind, values=[round(v, DIGITS) for v in values])
            if kind == 'circle' and element.get('fill') not in (None, 'none'):
                mark['kind'] = 'dot'   # a button's centre, not its outline
            result.append(mark)
    return result


def _center(marker):
    v = marker['values']
    if marker['kind'] in ('circle', 'dot'):
        return v[0], v[1]
    if marker['kind'] == 'line':
        return (v[0] + v[2]) / 2, (v[1] + v[3]) / 2
    return v[0] + v[2] / 2, v[1] + v[3] / 2


def assign_markers(pieces, found):
    """Give each mark to the smallest piece whose bounding box holds its centre, so it moves with that piece."""
    for marker in found:
        x, y = _center(marker)
        holders = [p for p in pieces if p['bbox'][0] <= x <= p['bbox'][2] and p['bbox'][1] <= y <= p['bbox'][3]]
        if holders:
            owner = min(holders, key=lambda p: (p['bbox'][2] - p['bbox'][0]) * (p['bbox'][3] - p['bbox'][1]))
            owner['markers'].append(marker)


def payload(state):
    """What /trace needs from a studio (gui.callbacks.GUIState), or None before a pattern is drafted."""
    pattern = state.pattern_state
    if not pattern.svg_filename or not pattern.panel_svg_paths:
        return None
    pieces = []
    for name, path in pattern.panel_svg_paths.items():
        x0, x1, y0, y1 = path.bbox()
        pieces.append(dict(id=name, label=state.panel_label(name), outline=polyline(path),
                           bbox=[round(v, DIGITS) for v in (x0, y0, x1, y1)], markers=[]))
    assign_markers(pieces, markers(pattern.svg_path()))
    title = getattr(getattr(state, 'ui_outfit_title', None), 'text', None) or 'Pattern'
    units = None
    if getattr(state, 'user', None):
        from webapp.profiles import get_units
        units = get_units(state.user['email'])
    return dict(title=title, pieces=pieces, units=units,
                # Layouts are remembered per set of pieces, not per edit.
                key='|'.join(sorted(pattern.panel_svg_paths)))


def _script_json(data):
    """JSON safe inside a <script> element, whatever a piece or garment is called."""
    return json.dumps(data, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e') \
        .replace('&', '\\u0026')


@ui.page('/trace', title='SewEasy — Pattern projector')
def trace_page():
    from gui import theme
    data = app.storage.user.get(STORAGE_KEY)
    ui.add_head_html(theme.HEAD_HTML + '<link rel="stylesheet" href="/trace-assets/trace_view.css">')
    ui.add_body_html(f'<script type="application/json" id="se-trace-data">{_script_json(data)}</script>'
                     '<div id="se-trace" class="se-trace" tabindex="-1"></div>'
                     '<script type="module" src="/trace-assets/trace_view.js"></script>')
