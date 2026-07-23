"""Classic dress shirt: button-front placket, collar stand with fold-over
collar, curved shirttail hem, barrel cuffs, and parametric waist shaping
that follows the wearer's measurements — one block drafts for any body.

Construction notes:
* The button stand is drafted as a center-front extension on both fronts
  (`placket_width` per side). For draping, the two front edges are stitched
  together along the button line — a buttoned-closed shirt — which adds the
  stand width as front ease.
* No back yoke: the armhole is cut into the side/shoulder corner of one
  panel (see pyg.ops.cut_corner), and a yoke seam would cross that cut.
* Sleeves reuse the standard Sleeve component; a barrel cuff is a CuffBand.
"""
from copy import deepcopy

import numpy as np

import seweasy as pyg

from assets.garment_programs.base_classes import BaseBodicePanel
from assets.garment_programs.bands import StraightBandPanel
from assets.garment_programs import sleeves
from assets.garment_programs import collars
from assets.garment_programs.closures import pre_fold

# Fold angles for the collar falls over the stand (degrees). The fall is
# pre-folded down-and-forward so it starts draped over the stand; the SOFT
# fall stiffness (below) then lets it settle onto the chest/shoulders as a
# real turndown instead of the rigid "wings" a stiff fall propped out at these
# angles. The back needs a touch more fold to clear the neck. See
# closures.pre_fold. NOTE: a flat rectangular fall still domes slightly on the
# curved neckline (a truly flat lie needs a curve-cut fall panel).
_COLLAR_FRONT_FOLD = 150
_COLLAR_BACK_FOLD = 160

# Edge label marking the center-front button placket (buttons placed along it)
_BUTTON_PLACKET_LABEL = 'button_placket'

# Default bending-stiffness multipliers (crisp, interfaced-fabric look).
# The collar STAND is firm so the neck band holds its shape; the collar FALL
# is only lightly stiffened so it drapes/rolls onto the chest as a turndown
# (a fully-stiff fall props out rigidly as "wings"). The barrel cuff is firm
# so it holds a clean cylinder instead of drooping into a soft tube.
_COLLAR_STAND_STIFFNESS = 15.0
_COLLAR_FALL_STIFFNESS = 6.0
_CUFF_STIFFNESS = 12.0


class DressShirtPanel(BaseBodicePanel):
    """Half of a dress shirt torso (front or back).

    Shared geometry: straight upper side (armhole region), curved waist
    shaping below it, shirttail hem. The front adds the placket extension.
    """

    def __init__(self, name, body, design, front=True) -> None:
        super().__init__(name, body, design)
        d = design['dress_shirt']

        ease = d['ease']['v']
        shaping = d['waist_shaping']['v']
        hem_rise = d['hem_curve']['v']
        ext = d['placket_width']['v'] if front else 0

        # Fractions of the full circumference this panel covers
        if front:
            chest_frac = (body['bust'] - body['back_width']) / 2 / body['bust']
            waist_frac = (body['waist'] - body['waist_back_width']) / 2 / body['waist']
            hip_frac = (body['hips'] - body['hip_back_width']) / 2 / body['hips']
        else:
            chest_frac = body['back_width'] / 2 / body['bust']
            waist_frac = body['waist_back_width'] / 2 / body['waist']
            hip_frac = body['hip_back_width'] / 2 / body['hips']

        chest_w = chest_frac * ease * body['bust']
        self.width = chest_w
        # Waist suppression: 0 keeps the boxy chest width, 1 follows the body
        waist_w = pyg.utils.lin_interpolation(
            chest_w, waist_frac * ease * body['waist'], shaping)
        # The skirt of the shirt must clear the hips regardless of shaping
        hem_w = max(hip_frac * ease * body['hips'], waist_w)

        sh_tan = np.tan(np.deg2rad(body['_shoulder_incl']))
        shoulder_incl = sh_tan * chest_w

        length = d['length']['v'] * body['waist_line']
        if front:
            # Adjusted for shoulder inclination for correct sleeve fitting
            # (same as the T-shirt block)
            fb_diff = (chest_frac - (0.5 - chest_frac)) * body['bust']
            length -= sh_tan * fb_diff

        # Vertical levels, y=0 at the hem; strictly ordered
        # hem_rise < y_waist < y_chest so short shirts degrade gracefully
        # (shallower armholes, smaller tails) instead of self-intersecting
        upper_side_len = min(body['_armscye_depth'] * 2.2 + 2, 0.55 * length)
        y_chest = length - upper_side_len
        y_waist = np.clip(length - body['waist_line'], 6., y_chest - 3)
        hem_rise = min(hem_rise, y_waist - 3)

        # Keep the side seam's slope gentle: suppression is limited by the
        # vertical room available, or the seam hairpins at the hem corner
        waist_w = max(waist_w,
                      hem_w - 0.4 * (y_waist - hem_rise),
                      chest_w - 0.4 * (y_chest - y_waist))

        # --- Edge loop (counterclockwise from center-bottom) ---
        # Shirttail hem: flat through the center, then a quarter-round
        # curve up to the side seam (vertical tangent at the corner, so the
        # junction with the side seam is a soft, near-tangent corner)
        # All curves are quadratic Beziers with analytically-placed control
        # points (tangent-line intersections): deterministic, no fitting
        corner = [-hem_w, hem_rise]
        waist_pt = [-waist_w, y_waist]
        # Direction of the (straight) side seam just above the hem corner
        seam_d = np.array([corner[0] - waist_pt[0], corner[1] - waist_pt[1]])

        if hem_rise > 0.5:
            curve_w = min(hem_w * 0.4, max(2 * hem_rise, 4.))
            hem_flat = pyg.Edge([ext, 0], [-(hem_w - curve_w), 0])
            # Control point where the side-seam line, extended down past
            # the corner, crosses y=0: the hem leaves horizontally and
            # lands tangent on the side seam. Overshoot past the corner is
            # capped: exact tangency matters less than a sane outline
            s = hem_rise / (y_waist - hem_rise)
            ctrl = [max(corner[0] + s * seam_d[0], corner[0] - 1.5), 0]
            hem_tail = pyg.CurveEdge(
                hem_flat.end, corner, [ctrl], relative=False)
            hem = pyg.EdgeSequence(hem_flat, hem_tail)
        else:
            hem = pyg.EdgeSequence(pyg.Edge([ext, 0], [-hem_w, 0]))

        # Side seam: straight from the hem corner to the waist (matches the
        # hem-tail tangent exactly), then a soft curve out to the chest
        # line, arriving vertical to meet the straight armhole edge
        side_lower = pyg.Edge(hem[-1].end, waist_pt)
        if chest_w - waist_w > 0.5:
            ctrl = [-chest_w, y_waist + 0.35 * (y_chest - y_waist)]
            side_mid = pyg.CurveEdge(
                waist_pt, [-chest_w, y_chest], [ctrl], relative=False)
        else:
            side_mid = pyg.Edge(waist_pt, [-chest_w, y_chest])
        # Straight armhole-region side
        side_upper = pyg.Edge(side_mid.end, [-chest_w, length])

        shoulder = pyg.Edge(side_upper.end, [ext, length + shoulder_incl])
        inside = pyg.Edge(shoulder.end, hem[0].start)

        self.edges = pyg.EdgeSequence(
            *hem, side_lower, side_mid, side_upper, shoulder, inside)

        # Interfaces
        self.interfaces = {
            'outside': pyg.Interface(
                self, pyg.EdgeSequence(side_lower, side_mid, side_upper)),
            'inside': pyg.Interface(self, inside),
            'shoulder': pyg.Interface(self, shoulder),
            'bottom': pyg.Interface(self, hem),
            'shoulder_corner': pyg.Interface(self, [side_upper, shoulder]),
            'collar_corner': pyg.Interface(self, [shoulder, inside]),
        }

        # default placement
        self.translate_by(
            [0, body['height'] - body['head_l'] - length - shoulder_incl, 0])

    def get_width(self, level):
        # The upper side edge is vertical: panel width is constant over
        # the whole armhole region
        return self.width


class CollarLeafPanel(pyg.Panel):
    """Fold-over collar half: a band with a pointed front end.

    Mimics StraightBandPanel's edge ordering so interface roles match:
    edges[0] shoulder end, edges[2] front (pointed) end.
    """

    def __init__(self, name, width, depth, point_ext=0) -> None:
        super().__init__(name)

        self.edges = pyg.EdgeSeqFactory.from_verts(
            [0, 0], [0, depth], [width + point_ext, depth], [width, 0],
            loop=True)

        self.interfaces = {
            'right': pyg.Interface(self, self.edges[0]),
            'top': pyg.Interface(self, self.edges[1]).reverse(True),
            'left': pyg.Interface(self, self.edges[2]),
            'bottom': pyg.Interface(self, self.edges[3]),
        }

        self.top_center_pivot()
        self.center_x()


class ShirtCollar(pyg.Component):
    """Dress shirt collar: a standing band (collar stand) around the neck
    with a fold-over pointed collar stitched on top. One instance per
    bodice half (front + back pieces each)."""

    def __init__(self, tag, body, design) -> None:
        super().__init__(f'ShirtCollar_{tag}')

        d = design['dress_shirt']
        stand_h = d['stand_height']['v']
        collar_d = d['collar_depth']['v']
        point = d['collar_point']['v']

        width = body['neck_w'] * d['neck_ease']['v']
        fc_depth = 0.45 * width
        bc_depth = 0.12 * width

        # --Projected neckline shapes--
        f_collar = collars.CircleNeckHalf(fc_depth, width)
        b_collar = collars.CircleNeckHalf(bc_depth, width)

        self.interfaces = {
            'front_proj': pyg.Interface(self, f_collar),
            'back_proj': pyg.Interface(self, b_collar)
        }

        # -- Panels --
        length_f, length_b = f_collar.length(), b_collar.length()
        height_p = body['height'] - body['head_l'] + stand_h
        # Exposed so DressShirt can build a matching continuous back fall
        self.length_b = length_b
        self.collar_d = collar_d
        self.stand_top_y = height_p

        # Collar stand (like a shallow turtle neck)
        self.stand_f = StraightBandPanel(
            f'{tag}_stand_front', length_f, stand_h).translate_by(
            [-length_f / 2, height_p, 12])
        self.stand_b = StraightBandPanel(
            f'{tag}_stand_back', length_b, stand_h).translate_by(
            [-length_b / 2, height_p, -12])

        # Front fold-over collar fall (per half; free at the center-front
        # collar opening). Placed above the stand, then pre-folded down over
        # it so the collar "falls" correctly in the drape instead of standing
        # straight up. The BACK fall is built once, continuously, at the
        # DressShirt level (see DressShirt._add_back_fall) -- a single piece
        # with no center-back seam, which is the only way a folded back fall
        # both welds and holds (a split, folded, center-back-seamed fall
        # collapses the initial mesh weld).
        self.leaf_f = CollarLeafPanel(
            f'{tag}_collar_front', length_f, collar_d, point_ext=point
            ).translate_by([-length_f / 2, height_p + collar_d + 1, 14])
        pre_fold(self.leaf_f, self.leaf_f.interfaces['bottom'].edges[0],
                 _COLLAR_FRONT_FOLD)

        self.stitching_rules = pyg.Stitches(
            # stands meet at the shoulder line (the band stays continuous
            # around the neck)
            (self.stand_f.interfaces['right'], self.stand_b.interfaces['right']),
            # front collar fall sewn along the top of the front stand
            (self.leaf_f.interfaces['bottom'], self.stand_f.interfaces['top']),
        )

        self.interfaces.update({
            # Center front: only the stand connects (top button); the
            # front fall's pointed edge stays free (collar opening)
            'front': self.stand_f.interfaces['left'],
            # Center back seam: just the (unfolded) back stand
            'back': self.stand_b.interfaces['left'],
            # Top of the back stand -- the continuous back fall welds here
            'back_stand_top': self.stand_b.interfaces['top'],
            'bottom': pyg.Interface.from_multiple(
                self.stand_f.interfaces['bottom'],
                self.stand_b.interfaces['bottom'])
        })

    def length(self):
        return self.interfaces['back'].edges.length()


class DressShirtHalf(pyg.Component):
    """Half of a dress shirt: torso panels, sleeve, collar."""

    def __init__(self, name, body, design) -> None:
        super().__init__(name)

        design = deepcopy(design)   # Recalculate freely!

        self.ftorso = DressShirtPanel(
            f'{name}_ftorso', body, design, front=True).translate_by([0, 0, 30])
        self.btorso = DressShirtPanel(
            f'{name}_btorso', body, design, front=False).translate_by([0, 0, -25])

        self.interfaces = {
            'f_bottom': self.ftorso.interfaces['bottom'],
            'b_bottom': self.btorso.interfaces['bottom'],
            'front_in': self.ftorso.interfaces['inside'],
            'back_in': self.btorso.interfaces['inside']
        }

        # Sleeve opening size (same mechanics as BodiceHalf)
        max_cwidth = self.ftorso.interfaces['shoulder_corner'].edges[0].length() - 1
        min_cwidth = body['_armscye_depth']
        v = design['sleeve']['connecting_width']['v']
        design['sleeve']['connecting_width']['v'] = min(
            min_cwidth + min_cwidth * v, max_cwidth)

        self.add_sleeves(name, body, design)
        self.add_collar(name, body, design)

        self.stitching_rules.append((
            self.ftorso.interfaces['shoulder'],
            self.btorso.interfaces['shoulder']
        ))
        self.stitching_rules.append((
            self.ftorso.interfaces['outside'],
            self.btorso.interfaces['outside']))

    def add_sleeves(self, name, body, design):
        self.sleeve = sleeves.Sleeve(
            name, body, design,
            front_w=self.ftorso.get_width,
            back_w=self.btorso.get_width
        )

        _, f_sleeve_int = pyg.ops.cut_corner(
            self.sleeve.interfaces['in_front_shape'].edges,
            self.ftorso.interfaces['shoulder_corner'],
            verbose=self.verbose
        )
        _, b_sleeve_int = pyg.ops.cut_corner(
            self.sleeve.interfaces['in_back_shape'].edges,
            self.btorso.interfaces['shoulder_corner'],
            verbose=self.verbose
        )

        if not design['sleeve']['sleeveless']['v']:
            bodice_sleeve_int = pyg.Interface.from_multiple(
                f_sleeve_int.reverse(with_edge_dir_reverse=True),
                b_sleeve_int.reverse(),
            )
            self.stitching_rules.append((
                self.sleeve.interfaces['in'],
                bodice_sleeve_int
            ))
            gap = -1 - body['arm_pose_angle'] / 10
            self.sleeve.place_by_interface(
                self.sleeve.interfaces['in'],
                bodice_sleeve_int,
                gap=gap,
                alignment='top',
            )

        f_sleeve_int.edges.propagate_label(f'{self.name}_armhole')
        b_sleeve_int.edges.propagate_label(f'{self.name}_armhole')

    def add_collar(self, name, body, design):
        self.collar_comp = ShirtCollar(name, body, design)

        _, fc_interface = pyg.ops.cut_corner(
            self.collar_comp.interfaces['front_proj'].edges,
            self.ftorso.interfaces['collar_corner'],
            verbose=self.verbose
        )
        _, bc_interface = pyg.ops.cut_corner(
            self.collar_comp.interfaces['back_proj'].edges,
            self.btorso.interfaces['collar_corner'],
            verbose=self.verbose
        )

        # Neckline to collar stand
        self.stitching_rules.append((
            pyg.Interface.from_multiple(fc_interface, bc_interface),
            self.collar_comp.interfaces['bottom']
        ))

        self.interfaces['front_collar'] = self.collar_comp.interfaces['front']
        self.interfaces['front_in'] = pyg.Interface.from_multiple(
            self.ftorso.interfaces['inside'], self.interfaces['front_collar']
        )
        self.interfaces['back_collar'] = self.collar_comp.interfaces['back']
        # Center-back seam = the torso only. The two back stands are NOT
        # seamed to each other here: with a continuous back fall welded across
        # both their tops, adding a stand-to-stand center-back seam makes three
        # seams meet at the center-back-top point and collapses the initial
        # mesh weld. The stands are held closed by the neckline below and the
        # continuous fall above.
        self.interfaces['back_in'] = self.btorso.interfaces['inside']
        # Exposed so DressShirt can weld one continuous back fall across both
        # halves' back stand tops
        self.interfaces['back_stand_top'] = \
            self.collar_comp.interfaces['back_stand_top']

        fc_interface.edges.propagate_label(f'{self.name}_collar')
        bc_interface.edges.propagate_label(f'{self.name}_collar')

    def length(self):
        return self.btorso.length()


class DressShirt(pyg.Component):
    """A classic dress shirt, symmetric, buttoned closed for draping."""

    def __init__(self, body, design) -> None:
        super().__init__(self.__class__.__name__)
        self.design = design

        self.right = DressShirtHalf('right', body, design)
        self.left = DressShirtHalf('left', body, design).mirror()

        # Button line: the placket extensions are stitched shut
        self.stitching_rules.append((self.right.interfaces['front_in'],
                                     self.left.interfaces['front_in']))
        self.stitching_rules.append((self.right.interfaces['back_in'],
                                     self.left.interfaces['back_in']))

        # One continuous back fall spanning both halves (see _add_back_fall)
        self._add_back_fall()

        # Tag the right front's center-front edge as the button placket so the
        # pattern renderer and the drape can place buttons along it
        self.right.ftorso.interfaces['inside'].edges.propagate_label(
            _BUTTON_PLACKET_LABEL)

        self.interfaces = {
            'bottom': pyg.Interface.from_multiple(
                self.right.interfaces['f_bottom'].reverse(),
                self.left.interfaces['f_bottom'],
                self.left.interfaces['b_bottom'].reverse(),
                self.right.interfaces['b_bottom'],)
        }

    def assembly(self):
        """Standard assembly plus the button hardware config, so the 2D
        pattern and the 3D drape can both place buttons along the placket."""
        spat = super().assembly()
        b = self.design.get('buttons', {})
        count = int(b.get('count', {}).get('v', 0)) if b else 0
        if count > 0:
            spat.pattern['buttons'] = {
                'count': count,
                'diameter': float(b['diameter']['v']),
                'placket_label': _BUTTON_PLACKET_LABEL,
            }
        # A dress-shirt collar and cuffs are interfaced (crisp): stiffen those
        # panels by default. The stand is firm (holds the neck band), the fall
        # only lightly (so it rolls onto the chest instead of propping out),
        # and the cuff is firm (clean barrel). Panel names carry the role:
        # '*_stand_*', '*_collar_*' (the fall), '*_cuff_*'. The user can
        # override any panel's stiffness in the GUI.
        stiff = {}
        for p in spat.pattern['panels']:
            if 'stand' in p:
                stiff[p] = _COLLAR_STAND_STIFFNESS
            elif 'collar' in p:
                stiff[p] = _COLLAR_FALL_STIFFNESS
            elif 'cuff' in p:
                stiff[p] = _CUFF_STIFFNESS
        if stiff:
            spat.pattern.setdefault('panel_stiffness', {}).update(stiff)
        return spat

    def _add_back_fall(self):
        """Build the collar's back fall as ONE continuous panel welded across
        both halves' back stand tops, then pre-fold it down.

        A split back fall (one per half, seamed at center back) collapses the
        initial mesh weld once folded. A single piece has no center-back seam,
        welds cleanly to the two stand tops, and -- being connected to the
        stand through that weld -- holds its fold via cloth bending, the same
        way the front fall does.
        """
        collar = self.right.collar_comp
        width = 2 * collar.length_b
        depth = collar.collar_d

        # Placed above the back stands (behind the neck), mirroring the front
        # fall's placement, then pre-folded down+back over the stand.
        self.back_fall = StraightBandPanel('collar_back', width, depth)
        self.back_fall.translate_by([0, collar.stand_top_y + depth + 1, -14])
        pre_fold(self.back_fall, self.back_fall.interfaces['bottom'].edges[0],
                 _COLLAR_BACK_FOLD)

        stand_top = pyg.Interface.from_multiple(
            self.right.interfaces['back_stand_top'],
            self.left.interfaces['back_stand_top'])
        self.stitching_rules.append(
            (self.back_fall.interfaces['bottom'], stand_top))

    def length(self):
        return self.right.length()
