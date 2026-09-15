"""A compact cutting-table layout for the studio, independent of assembly/export."""
from math import sqrt


def pack_panels(paths, gap=5, label_space=9):
    """Translate true, unprojected panel outlines without rotating or scaling them.

    Keep small construction pieces together above the main panels. A shelf
    reserves a caption below every piece, including very narrow collar stands.
    Coordinates stay in the pattern's centimetres, so rulers remain meaningful.
    """
    boxes = {name: path.bbox() for name, path in paths.items()}
    area = sum((max(24, b[1] - b[0]) + gap) * (b[3] - b[2] + label_space + gap)
               for b in boxes.values())
    target = max(max(b[1] - b[0] for b in boxes.values()), sqrt(area * 1.15))

    def order(name):
        group, _, local = name.rpartition('__')
        local = local or name
        kind = (0 if any(word in local for word in ('collar', 'stand', 'yoke')) else
                2 if any(word in local for word in ('cuff', 'pocket', 'waistband')) else 1)
        b = boxes[name]
        return group, kind, -(b[3] - b[2]), local

    rows, row, used, height, previous_group = [], [], 0, 0, None
    for name in sorted(paths, key=order):
        b = boxes[name]
        width = max(24, b[1] - b[0])
        group = order(name)[:2]
        if row and (used + width > target or group != previous_group):
            rows.append((row, used - gap, height))
            row, used, height = [], 0, 0
        row.append((name, used, width))
        used += width + gap
        height = max(height, b[3] - b[2] + label_space)
        previous_group = group
    if row:
        rows.append((row, used - gap, height))

    sheet_width = max(width for _, width, _ in rows) + gap * 2
    packed, labels, y = {}, {}, gap
    for row, width, height in rows:
        inset = (sheet_width - width) / 2
        for name, x, reserved in row:
            b = boxes[name]
            x += inset + (reserved - (b[1] - b[0])) / 2
            packed[name] = paths[name].translated(complex(x - b[0], y - b[2]))
            labels[name] = {'x': x + (b[1] - b[0]) / 2, 'y': y + b[3] - b[2] + 3.5}
        y += height + gap
    return packed, labels, (sheet_width, y)


def studio_svg(pattern, filename, **appearance):
    """Reuse the exporter's fabrics and fastener marks, with a GUI-only layout."""
    drawing = pattern.get_svg(filename, flat=True, with_text=False, view_ids=False,
                              margin=0, **appearance)
    paths, labels, size = pack_panels(pattern.last_panel_svg_paths)
    rendered = [element for element in drawing.elements if element.elementname == 'path']
    styles = {name: dict(element.attribs)
              for name, element in zip(pattern.last_panel_svg_paths, rendered)}
    # Rebuild positions; keep the existing fabric definitions and their IDs.
    drawing.elements = [drawing.defs]
    for name, path in paths.items():
        style = styles[name]
        style.pop('d', None)
        style.update(stroke='#294762', **{'stroke-width': '.7', 'vector-effect': 'non-scaling-stroke'})
        drawing.add(drawing.path(d=path.d() + ' Z', **style))
    pattern.last_panel_svg_paths = paths
    pattern._add_button_markers(drawing, flat=True)
    pattern._add_zipper_markers(drawing, flat=False)
    drawing.viewbox(0, 0, *size)
    drawing['width'], drawing['height'] = size
    return drawing, paths, labels, size
