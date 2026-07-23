"""Element tube top: a strapless, fitted bandeau top with a folded-down cuff.

Modelled on the Aritzia Element tube top (structured black crepe): a woven,
non-stretch strapless top that grips at the upper bust, nips in at the waist,
and flares gently to a high-hip A-line hem with a short side slit. Its defining
feature is a deep cuff folded down over the outside of the whole top edge.

Construction notes:
* Front and back are each a SINGLE panel cut on the fold (no center-front or
  center-back seam) -- like a paneled skirt -- joined by two side seams. This
  matches a real tube top (a CF seam would be wrong) and, crucially, lets each
  continuous cuff weld 1:1 to one full top edge. A cuff crossing a center seam
  makes a T-junction the box-mesh welder collapses.
* Strapless: the top edge is a straight, horizontal bandeau line. Fit comes
  from curved, waist-suppressed side seams (a bodice bust dart would
  over-constrain the drape on a static mannequin and isn't needed for the look).
* The fold-over cuff is a separate band per face (front, back), stitched along
  the top edge and pre-folded down over the outside so the fold survives the
  sim (a crease inside one panel springs flat -- see closures.pre_fold). It is
  folded only PART-way (see _CUFF_FOLD) so it stands off the torso at mesh-build
  time; gravity + a crisp cuff stiffness settle it into a pressed turn-down.
* Side slit: the lower part of each side seam is left unstitched (a vent).
"""
import numpy as np

import seweasy as pyg

from assets.garment_programs.bands import StraightBandPanel
from assets.garment_programs.closures import pre_fold


# Cuff bending stiffness: firm enough to read as a pressed, structured fold,
# soft enough that gravity lays the flap flat down the body during the sim
# (too stiff and it holds the initial fold angle out as a shelf).
_CUFF_STIFFNESS = 5.0

# Cuff fold angle (deg). NOT near-180: a flap folded flat lands coincident with
# the torso, and the box-mesh welder (which merges vertices by 3D proximity)
# fuses the two and the weld collapses. ~150 pre-folds the flap well down while
# still standing it a few cm off the torso at mesh-build time; gravity + the
# soft cuff stiffness then settle it into a flat, pressed turn-down.
_CUFF_FOLD = 150

# Center-back zipper (hardware marker, not a real seam -- the back is cut on the
# fold). The back top edge is tagged with this label so the 2D pattern draws
# the zip down the center; _ZIP_LENGTH is the fraction of garment height it runs.
_ZIP_LABEL = 'cb_zip'
_ZIP_LENGTH = 0.6


class ElementTopPanel(pyg.Panel):
    """Full front or back torso panel, symmetric and cut on the fold.

    y runs up from the hem (y=0) to the bandeau top edge; x is symmetric about
    center (0). Edge loop, CCW from the hem-left corner:
    hem -> right side (lower+upper) -> top -> left side (upper+lower).
    """

    def __init__(self, name, body, design, front=True) -> None:
        super().__init__(name)

        d = design['element_top']
        ease = d['ease']['v']
        shaping = d['waist_shaping']['v']
        flare = d['flare']['v']
        slit = d['side_slit']['v']

        # Vertical levels (cm) from the waist: bust apex, bandeau a bit higher
        bust_over_waist = body['waist_line'] - body['_bust_line']
        top_above_waist = bust_over_waist + d['top_rise']['v']
        hem_below_waist = d['length']['v'] * body['hips_line']
        y_top = hem_below_waist + top_above_waist
        y_waist = hem_below_waist

        # Half-panel circumference fractions (front vs back split of the body)
        if front:
            top_frac = (body['bust'] - body['back_width']) / 2 / body['bust']
            waist_frac = (body['waist'] - body['waist_back_width']) / 2 / body['waist']
            hip_frac = (body['hips'] - body['hip_back_width']) / 2 / body['hips']
        else:
            top_frac = body['back_width'] / 2 / body['bust']
            waist_frac = body['waist_back_width'] / 2 / body['waist']
            hip_frac = body['hip_back_width'] / 2 / body['hips']

        top_w = top_frac * ease * body['bust']
        self.width = top_w
        # Waist suppression: 0 keeps the bandeau width straight down; 1 follows
        # the body waist. A soft nip reads tailored without over-constraining.
        waist_w = pyg.utils.lin_interpolation(
            top_w, waist_frac * body['waist'], shaping)
        # Hem width tracks the HIP (plus a small `flare` ease), not the bust:
        # the top skims to the high hip and hangs nearly straight. Flaring off
        # the (wider) bust width instead overshoots the hip and reads as a
        # trumpet. Still never tighter than the waist.
        hip_w = hip_frac * body['hips']
        hem_w = max(hip_w * flare, waist_w)
        waist_w = min(waist_w, top_w, hem_w)

        y_mid = y_waist + 0.5 * (y_top - y_waist)

        # --- Edge loop (CCW from hem-left) ---
        hem = pyg.Edge([-hem_w, 0], [hem_w, 0])
        # Right side seam: two quadratics sharing a VERTICAL tangent at the
        # waist -> one smooth curve (flares to hem, nips at waist, out to top).
        sideR_lower = pyg.CurveEdge(
            hem.end, [waist_w, y_waist], [[waist_w, 0.5 * y_waist]],
            relative=False)
        sideR_upper = pyg.CurveEdge(
            sideR_lower.end, [top_w, y_top], [[waist_w, y_mid]], relative=False)
        top = pyg.Edge(sideR_upper.end, [-top_w, y_top])
        sideL_upper = pyg.CurveEdge(
            top.end, [-waist_w, y_waist], [[-waist_w, y_mid]], relative=False)
        sideL_lower = pyg.CurveEdge(
            sideL_upper.end, hem.start, [[-waist_w, 0.5 * y_waist]],
            relative=False)

        self.edges = pyg.EdgeSequence(
            hem, sideR_lower, sideR_upper, top, sideL_upper, sideL_lower)

        # Side slits: leave the lower (hem-side) fraction of each side unstitched
        right_stitched = pyg.EdgeSequence(sideR_lower, sideR_upper)
        left_stitched = pyg.EdgeSequence(sideL_upper, sideL_lower)
        if slit > 1e-3:
            # right lower runs hem -> waist: slit is the first (hem) fraction
            rparts = sideR_lower.subdivide_len([slit, 1 - slit])
            self.edges.substitute(sideR_lower, rparts)
            right_stitched = pyg.EdgeSequence(rparts[1], sideR_upper)
            # left lower runs waist -> hem: slit is the last (hem) fraction
            lparts = sideL_lower.subdivide_len([1 - slit, slit])
            self.edges.substitute(sideL_lower, lparts)
            left_stitched = pyg.EdgeSequence(sideL_upper, lparts[0])

        self.interfaces = {
            'top': pyg.Interface(self, top),
            'right': pyg.Interface(self, right_stitched),
            'left': pyg.Interface(self, left_stitched),
            'bottom': pyg.Interface(self, hem),
        }

        # Placement: hem at its world level; front/back offset in Z
        y0 = body['_waist_level'] - hem_below_waist
        self.translate_by([0, y0, 30 if front else -25])

    def length(self):
        return self.interfaces['right'].edges.length()


class ElementTubeTop(pyg.Component):
    """The full Element tube top: front + back panels joined at the side seams,
    with a continuous fold-over cuff across the front and across the back."""

    def __init__(self, body, design) -> None:
        super().__init__(self.__class__.__name__)
        self.design = design
        self.cuff_depth = design['element_top']['cuff_depth']['v']

        self.ftorso = ElementTopPanel('front', body, design, front=True)
        self.btorso = ElementTopPanel('back', body, design, front=False)

        # Side seams
        self.stitching_rules.append(
            (self.ftorso.interfaces['right'], self.btorso.interfaces['right']))
        self.stitching_rules.append(
            (self.ftorso.interfaces['left'], self.btorso.interfaces['left']))

        # Continuous fold-over cuffs (one per face, no vertical seams)
        self.fcuff = self._add_cuff('fcuff', self.ftorso)
        self.bcuff = self._add_cuff('bcuff', self.btorso)

        # Center-back zipper: the real top closes with an invisible zip down the
        # center back. The back is cut on the fold (no CB seam -- see class
        # docstring), so the zipper is a hardware marker (like buttons), not a
        # real opening: label the back top edge so the 2D pattern can draw the
        # zip down the center, and declare it for the 3D surface placement.
        self.btorso.interfaces['top'].edges.propagate_label(_ZIP_LABEL)

        self.interfaces = {
            'bottom': pyg.Interface.from_multiple(
                self.ftorso.interfaces['bottom'],
                self.btorso.interfaces['bottom']),
        }

    def _add_cuff(self, tag, torso):
        """Build one continuous cuff band welded 1:1 along a full top edge and
        pre-folded down over the outside. Its vertical edges are left free at
        the side seams -- seaming them there converges four seams (torso side +
        two fold seams + cuff side) and collapses the weld, exactly as the
        dress-shirt folded collar does."""
        cuff = StraightBandPanel(tag, 2 * torso.width, self.cuff_depth)
        top = torso.interfaces['top']
        cuff.place_by_interface(
            cuff.interfaces['bottom'], top, gap=0.5, alignment='center')
        self.stitching_rules.append((top, cuff.interfaces['bottom']))
        pre_fold(cuff, cuff.interfaces['bottom'].edges[0], _CUFF_FOLD)
        return cuff

    def assembly(self):
        """Standard assembly plus a crisp default stiffness on the cuff bands
        (so the fold-over reads as a pressed edge) and the center-back zipper."""
        spat = super().assembly()
        stiff = {}
        for p in spat.pattern['panels']:
            if 'cuff' in p:
                stiff[p] = _CUFF_STIFFNESS
        if stiff:
            spat.pattern.setdefault('panel_stiffness', {}).update(stiff)

        spat.pattern.setdefault('zippers', []).append({
            'placement': 'center_back',
            'length': _ZIP_LENGTH,
            'width': 1.2,
            'panel': 'back',
            'seam_label': _ZIP_LABEL,
        })
        return spat

    def length(self):
        return self.ftorso.length()
