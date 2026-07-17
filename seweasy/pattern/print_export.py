"""True-scale, tiled multipage PDF export for home printing.

Takes a pattern's flat SVG (whose user units are centimeters), tiles it
across standard sheets of paper at 1:1 scale, and merges the pages into a
single PDF: a cover page with printing instructions, a 5 cm calibration
square, and an assembly map, followed by the tile pages. Each tile has a
dashed trim frame and a grid label (A1, A2, ...) so the printed sheets can
be cut out and taped edge-to-edge.

This module is fork-specific (not part of upstream GarmentCode).
"""

import io
import math
import re
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter
from svgpathtools import svg2paths

# Page dimensions in cm
PAGE_SIZES_CM = {
    'letter': (21.59, 27.94),
    'a4': (21.0, 29.7),
}
MARGIN_CM = 1.0          # printer-safe margin; also the trim frame inset
PANEL_NAME_FONT_CM = 1.2  # replaces the 7 cm on-screen annotation size
LABEL_FONT_CM = 0.35
PRINT_STROKE_CM = 0.08   # cutting-line weight on paper (source uses 0.2)


def _svg_inner(svg_text: str) -> str:
    """The content between the root <svg ...> tags"""
    match = re.search(r'<svg[^>]*>', svg_text, re.DOTALL)
    end = svg_text.rfind('</svg>')
    return svg_text[match.end():end]


def _svg_viewbox(svg_text: str):
    match = re.search(r'viewBox="([^"]+)"', svg_text)
    return [float(v) for v in match.group(1).replace(',', ' ').split()]


def _page_pdf(page_svg: str) -> PdfReader:
    pdf_bytes = cairosvg.svg2pdf(bytestring=page_svg.encode('utf-8'))
    return PdfReader(io.BytesIO(pdf_bytes))


def save_print_pdf(pattern, out_pdf_path, page_size='letter',
                   margin=MARGIN_CM) -> Path:
    """Write a 1:1-scale multipage PDF of `pattern` (a VisPattern).

    Raises EmptyPatternError (from get_svg) if the pattern has no panels.
    """
    out_pdf_path = Path(out_pdf_path)
    page_w, page_h = PAGE_SIZES_CM[page_size]
    tile_w = page_w - 2 * margin
    tile_h = page_h - 2 * margin

    # Flat, unfilled pattern SVG with panel names (user units == cm)
    tmp_svg = out_pdf_path.with_suffix('.tmp.svg')
    dwg = pattern.get_svg(
        str(tmp_svg),
        with_text=True, view_ids=False,
        flat=True, fill_panels=False,
        margin=1,
    )
    dwg.save()
    svg_text = tmp_svg.read_text()

    # Panel bounding boxes (for skipping tiles with no content)
    paths, _ = svg2paths(str(tmp_svg))
    panel_bboxes = [p.bbox() for p in paths if len(p) > 0]  # (x0, x1, y0, y1)
    tmp_svg.unlink()

    # Panel-name annotations are sized for screen viewing (7 user units
    # = 7 cm on paper); shrink them to print scale
    svg_text = svg_text.replace('font-size="7"', f'font-size="{PANEL_NAME_FONT_CM}"')
    inner_map = _svg_inner(svg_text)
    # Thinner cutting lines at print scale
    inner = inner_map.replace('stroke-width="0.2"', f'stroke-width="{PRINT_STROKE_CM}"')
    x0, y0, width, height = _svg_viewbox(svg_text)

    # Tile grid, with the pattern centered in it
    cols = max(1, math.ceil(width / tile_w))
    rows = max(1, math.ceil(height / tile_h))
    grid_x0 = x0 - (cols * tile_w - width) / 2
    grid_y0 = y0 - (rows * tile_h - height) / 2

    def tile_has_content(r, c):
        tx0 = grid_x0 + c * tile_w
        ty0 = grid_y0 + r * tile_h
        for bx0, bx1, by0, by1 in panel_bboxes:
            if bx0 < tx0 + tile_w and bx1 > tx0 \
                    and by0 < ty0 + tile_h and by1 > ty0:
                return True
        return False

    kept_tiles = [(r, c) for r in range(rows) for c in range(cols)
                  if tile_has_content(r, c)]

    name = pattern.name
    writer = PdfWriter()

    # --- Cover page: instructions, calibration square, assembly map ---
    square = 5  # cm
    sq_top = margin + 6.3
    sq_caption_y = sq_top + square + 0.7
    map_title_y = sq_caption_y + 1.4
    map_top = map_title_y + 0.5
    map_avail_w = page_w - 2 * margin
    map_avail_h = page_h - margin - map_top
    map_scale = min(map_avail_w / (cols * tile_w), map_avail_h / (rows * tile_h))
    map_x = margin + (map_avail_w - cols * tile_w * map_scale) / 2
    map_y = map_top

    map_tiles = []
    for r, c in kept_tiles:
        tx = map_x + c * tile_w * map_scale
        ty = map_y + r * tile_h * map_scale
        map_tiles.append(
            f'<rect x="{tx:.3f}" y="{ty:.3f}" '
            f'width="{tile_w * map_scale:.3f}" height="{tile_h * map_scale:.3f}" '
            f'fill="none" stroke="#9aa3b2" stroke-width="0.03"/>'
            f'<text x="{tx + 0.25:.3f}" y="{ty + 0.65:.3f}" font-size="0.5" '
            f'fill="#9aa3b2" font-family="sans-serif">{chr(65 + r)}{c + 1}</text>'
        )
    map_pattern_tx = map_x - grid_x0 * map_scale
    map_pattern_ty = map_y - grid_y0 * map_scale

    instructions = [
        f'{len(kept_tiles)} pattern pages ({page_size.capitalize()}), scale 1:1.',
        'Print ALL pages at 100% / "Actual size" - do not "fit to page".',
        'Check the calibration square below with a ruler before cutting.',
        'Cut each page along its dashed frame, then tape the pages',
        'edge-to-edge following the map. Labels read row-letter, column-number.',
    ]
    instr_svg = ''.join(
        f'<text x="{margin}" y="{margin + 2.2 + i * 0.85:.2f}" font-size="0.5" '
        f'fill="#2b2f36" font-family="sans-serif">{line}</text>'
        for i, line in enumerate(instructions)
    )

    cover = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}cm" height="{page_h}cm" viewBox="0 0 {page_w} {page_h}">
<text x="{margin}" y="{margin + 1.0}" font-size="0.9" font-weight="bold" fill="#1d2b42" font-family="sans-serif">SewEasy - {name}</text>
{instr_svg}
<rect x="{margin}" y="{sq_top}" width="{square}" height="{square}" fill="none" stroke="#c94f4f" stroke-width="0.05" stroke-dasharray="0.4,0.25"/>
<text x="{margin}" y="{sq_caption_y:.2f}" font-size="0.5" fill="#c94f4f" font-family="sans-serif">This square must measure exactly 5 x 5 cm (1.97 x 1.97 in)</text>
<text x="{margin}" y="{map_title_y:.2f}" font-size="0.6" fill="#2b2f36" font-family="sans-serif">Assembly map (not to scale)</text>
<g transform="translate({map_pattern_tx:.4f},{map_pattern_ty:.4f}) scale({map_scale:.5f})">{inner_map}</g>
{''.join(map_tiles)}
</svg>'''
    writer.append(_page_pdf(cover))

    # --- Tile pages (blank tiles are skipped) ---
    for r, c in kept_tiles:
        tx = margin - (grid_x0 + c * tile_w)
        ty = margin - (grid_y0 + r * tile_h)
        label = f'{chr(65 + r)}{c + 1}'
        page_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{page_w}cm" height="{page_h}cm" viewBox="0 0 {page_w} {page_h}">
<defs><clipPath id="frame"><rect x="{margin}" y="{margin}" width="{tile_w}" height="{tile_h}"/></clipPath></defs>
<g clip-path="url(#frame)"><g transform="translate({tx:.4f},{ty:.4f})">{inner}</g></g>
<rect x="{margin}" y="{margin}" width="{tile_w}" height="{tile_h}" fill="none" stroke="#9aa3b2" stroke-width="0.02" stroke-dasharray="0.4,0.25"/>
<text x="{margin}" y="{page_h - margin + 0.55:.2f}" font-size="{LABEL_FONT_CM}" fill="#5a6270" font-family="sans-serif">SewEasy - {name} - {label} (row {r + 1}/{rows}, col {c + 1}/{cols}) - print at 100%</text>
</svg>'''
        writer.append(_page_pdf(page_svg))

    with open(out_pdf_path, 'wb') as f:
        writer.write(f)
    return out_pdf_path
