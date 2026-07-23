"""Procedural fabric patterns (pinstripe, polka dot, gingham, ...).

A "fabric" here is a background colour plus an optional woven/printed motif.
The same small parameter set drives two renderers so the 2D pattern view and
the 3D drape agree:

* ``fabric_image`` -- a tileable raster swatch (PIL) used as the drape's
  fabric-grain texture (see meshgen texture_utils): the motif ends up mapped
  onto the cloth in flat-pattern / grain-aligned space.
* ``fabric_svg_pattern`` -- an SVG ``<pattern>`` tile (as an svgwrite element)
  filling the panels in the 2D sewing-pattern SVG.

Config shape (carried in the spec as ``pattern['fabric']`` and in the design
as a ``fabric`` section)::

    {'kind': 'pinstripe', 'fg': '#ffffff', 'bg': '#2b4a7a', 'scale': 0.6}

``scale`` is the motif spacing in centimetres (stripe pitch / dot pitch).
``kind='plain'`` (or fg==bg) means no motif -- a solid ``bg`` fabric.
"""
import numpy as np

# Registered pattern kinds (order = GUI dropdown order; 'plain' first)
KINDS = ['plain', 'pinstripe', 'stripe', 'polka_dot', 'gingham', 'windowpane']

# Sensible default motif spacing (cm) per kind, used when scale is unset
_DEFAULT_SCALE = {
    'plain': 1.0, 'pinstripe': 0.6, 'stripe': 2.0,
    'polka_dot': 1.6, 'gingham': 1.0, 'windowpane': 3.0,
}


def default_scale(kind):
    return _DEFAULT_SCALE.get(kind, 1.0)


def _rgb(color):
    """Hex or (r,g,b[,a]) -> (r,g,b) uint8 tuple."""
    if isinstance(color, str):
        c = color.lstrip('#')
        if len(c) == 3:
            c = ''.join(ch * 2 for ch in c)
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(v) for v in color[:3])


def is_patterned(cfg):
    """True if the fabric config asks for a visible motif."""
    if not cfg:
        return False
    kind = cfg.get('kind', 'plain')
    if kind == 'plain':
        return False
    return _rgb(cfg.get('fg', '#ffffff')) != _rgb(cfg.get('bg', '#ffffff'))


# --------------------------------------------------------------------------
# Raster swatch for the 3D drape texture

def fabric_image(kind, fg, bg, scale_cm, px_per_cm=12, extent_cm=210):
    """Render a tileable fabric swatch as a PIL RGB image.

    * scale_cm  -- motif spacing in cm (stripe pitch / dot pitch)
    * px_per_cm -- raster resolution; must match the drape's
      ``fabric_grain_resolution`` so the motif comes out at ``scale_cm``
    * extent_cm -- swatch size in cm; big enough to cover a garment's UV atlas

    The motif is grain-aligned: vertical stripes run along the pattern's Y
    axis, dots sit on a square grid, etc.
    """
    fg = _rgb(fg)
    bg = _rgb(bg)
    n = max(8, int(round(extent_cm * px_per_cm)))
    per = max(2, int(round(scale_cm * px_per_cm)))     # motif period in px
    img = np.empty((n, n, 3), dtype=np.uint8)
    img[:] = bg

    xs = np.arange(n)
    if kind == 'pinstripe':
        # thin single-pixel-ish vertical lines every `per`
        lw = max(1, per // 12)
        col = (xs % per) < lw
        img[:, col] = fg
    elif kind == 'stripe':
        # bold vertical bands: half period fg, half bg
        col = (xs % per) < (per // 2)
        img[:, col] = fg
    elif kind == 'windowpane':
        # thin grid lines (both axes) every `per`
        lw = max(1, per // 22)
        line = (xs % per) < lw
        img[line, :] = fg
        img[:, line] = fg
    elif kind == 'gingham':
        # woven check: half-period bands on both axes, overlap darker
        band = (xs % per) < (per // 2)
        half = ((np.asarray(fg, float) + np.asarray(bg, float)) / 2
                ).astype(np.uint8)
        img[band, :] = half           # horizontal bands (blended)
        img[:, band] = half           # vertical bands (blended)
        img[np.ix_(band, band)] = fg  # overlap = full fg
    elif kind == 'polka_dot':
        r = max(1.0, per * 0.28)                 # dot radius
        cx = (xs % per)
        # offset every other row by half a period (brick layout)
        yy, xx = np.mgrid[0:n, 0:n]
        row = yy // per
        shift = np.where(row % 2 == 0, 0, per // 2)
        dx = np.minimum((xx + shift) % per, per - (xx + shift) % per)
        dy = np.minimum(yy % per, per - yy % per)
        mask = (dx * dx + dy * dy) <= r * r
        img[mask] = fg
    # 'plain' (and unknown) -> solid bg
    from PIL import Image
    return Image.fromarray(img, 'RGB')


# --------------------------------------------------------------------------
# SVG <pattern> tile for the 2D sewing-pattern view

def fabric_svg_pattern(dwg, kind, fg, bg, tile, pattern_id):
    """Build an svgwrite ``<pattern>`` element (tile size ``tile`` in the SVG's
    user units) and return (pattern_element, fill_url). Add the element to the
    SVG <defs> and use ``fill_url`` as a panel's fill. Returns (None, bg) for a
    plain fabric.
    """
    if kind == 'plain' or _rgb(fg) == _rgb(bg):
        return None, bg
    s = float(tile)
    pat = dwg.pattern(
        id=pattern_id, insert=(0, 0), size=(s, s),
        patternUnits='userSpaceOnUse')
    pat.add(dwg.rect(insert=(0, 0), size=(s, s), fill=bg))
    if kind == 'pinstripe':
        pat.add(dwg.rect(insert=(0, 0), size=(s * 0.09, s), fill=fg))
    elif kind == 'stripe':
        pat.add(dwg.rect(insert=(0, 0), size=(s * 0.5, s), fill=fg))
    elif kind == 'windowpane':
        w = s * 0.05
        pat.add(dwg.rect(insert=(0, 0), size=(s, w), fill=fg))
        pat.add(dwg.rect(insert=(0, 0), size=(w, s), fill=fg))
    elif kind == 'gingham':
        half = _blend_hex(fg, bg)
        pat.add(dwg.rect(insert=(0, 0), size=(s, s * 0.5), fill=half,
                         opacity=1.0))
        pat.add(dwg.rect(insert=(0, 0), size=(s * 0.5, s), fill=half,
                         opacity=0.6))
        pat.add(dwg.rect(insert=(0, 0), size=(s * 0.5, s * 0.5), fill=fg))
    elif kind == 'polka_dot':
        r = s * 0.22
        for cx, cy in [(s * 0.25, s * 0.25), (s * 0.75, s * 0.75)]:
            pat.add(dwg.circle(center=(cx, cy), r=r, fill=fg))
    return pat, f'url(#{pattern_id})'


def _blend_hex(a, b):
    ra, rb = _rgb(a), _rgb(b)
    m = tuple((x + y) // 2 for x, y in zip(ra, rb))
    return '#%02x%02x%02x' % m


# --------------------------------------------------------------------------
# Drape integration

# Raster resolution of the baked fabric swatch. Must be passed to the mesh
# texturer as `fabric_grain_resolution` so the motif comes out at `scale` cm.
DRAPE_PX_PER_CM = 11
# Swatch extent (cm): must cover the garment's UV atlas or the motif stretches
DRAPE_EXTENT_CM = 220


def build_uv_config(base_uv_config, fabric_cfg, out_dir):
    """Return a copy of `base_uv_config` set up to bake `fabric_cfg`'s motif
    into the drape's fabric texture, writing the swatch PNG into `out_dir`.

    For a plain/absent fabric the base config is returned unchanged (the
    garment keeps its neutral texture + solid fabric-colour tint).
    """
    cfg = dict(base_uv_config)
    if not is_patterned(fabric_cfg):
        return cfg
    from pathlib import Path
    kind = fabric_cfg['kind']
    scale = float(fabric_cfg.get('scale') or default_scale(kind))
    img = fabric_image(kind, fabric_cfg['fg'], fabric_cfg['bg'], scale,
                       px_per_cm=DRAPE_PX_PER_CM, extent_cm=DRAPE_EXTENT_CM)
    path = Path(out_dir) / 'fabric_pattern.png'
    img.save(path)
    cfg['fabric_grain_texture_path'] = str(path)
    cfg['fabric_grain_resolution'] = DRAPE_PX_PER_CM
    # The swatch already carries the full fabric (bg + motif): show it opaque
    # and drop the flat panel fill so the print isn't washed out. Seam
    # outlines are still drawn.
    cfg['background_alpha'] = 1.0
    cfg['color_alpha'] = 0.0
    cfg['panel_color'] = fabric_cfg['bg']
    return cfg
