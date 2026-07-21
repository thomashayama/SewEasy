"""Pre-fold paradigm for folded and buttoned garments.

Cloth simulation starts from the flat pattern placed in 3D and then relaxes
under gravity + body collision. A fold only survives the sim if two things
hold:

  1. It sits on a SEAM between two panels. A stitch is a distance spring with
     no target angle, so panels can meet at any dihedral. A crease *inside*
     one panel, by contrast, has a flat bending rest-angle and springs back
     flat — so folded features must be built as separate panels joined on the
     fold line, never as a crease within a single panel.
  2. It *starts* folded. A seam placed flat relaxes to whatever gravity gives;
     only a fold that is already folded in the initial 3D placement stays put.

`pre_fold` implements (2): it rotates an already-placed panel about one of its
edges (the hinge / seam line), keeping that edge fixed in 3D. Reuse it for any
garment feature that should hang folded before the sim runs — shirt-collar
fall folding over the stand, a button-placket facing folded back against the
front, lapels, folded cuffs, hems.

`ButtonPlacket` is the buttoned-front paradigm built on top of `pre_fold`: a
folded-back facing band along the center-front edge, a separate panel so the
fold holds, that reads as a real placket in 3D.
"""
import numpy as np
from scipy.spatial.transform import Rotation as R

import seweasy as pyg
from assets.garment_programs.bands import StraightBandPanel


def pre_fold(panel, hinge_edge, angle_deg):
    """Fold a placed panel about one of its edges, before simulation.

    * panel      -- a pyg.Panel that has ALREADY been positioned (translate/
                    rotate); the hinge axis is read from its current placement
    * hinge_edge -- an Edge of the panel (local 2D coords) that stays fixed;
                    the rest of the panel swings about it
    * angle_deg  -- fold angle. Sign picks the fold direction (toward or away
                    from the panel's current normal side)

    The seam on the hinge edge is preserved (that edge does not move), so a
    stitch defined on it stays valid. autonorm() is intentionally NOT called:
    a ~180 deg fold would otherwise flip the panel's right/wrong side and
    reverse its edge loop, breaking stitch orientation. The 3D viewer renders
    fabric double-sided, so the un-flipped normal is cosmetically fine.
    """
    h0 = np.asarray(panel.point_to_3D(hinge_edge.start))
    h1 = np.asarray(panel.point_to_3D(hinge_edge.end))
    axis = h1 - h0
    n = np.linalg.norm(axis)
    if n < 1e-6:
        return panel
    axis = axis / n

    delta = R.from_rotvec(axis * np.deg2rad(angle_deg))
    # Apply the world-space rotation about the hinge point h0:
    #   world' = delta.apply(world - h0) + h0
    # which, with world = rotation.apply(local) + translation, gives:
    panel.rotation = delta * panel.rotation
    panel.translation = delta.apply(panel.translation - h0) + h0
    return panel


class ButtonPlacket(pyg.Component):
    """A folded-back front facing for buttoned garments (shirts, jackets).

    Built as a separate band panel stitched to the garment's center-front
    edge and pre-folded ~180 deg so it lies against the inside of the front —
    the construction of a real placket, and one the sim will keep folded
    because the fold is a seam, not an in-panel crease.

    The facing runs the full length of the front opening. Its `to_front`
    interface stitches to the bodice center-front edge.
    """
    def __init__(self, tag, length, width, front_edge_3d, depth_dir):
        """
        * length       -- vertical length of the front opening (cm)
        * width        -- placket/facing width (cm)
        * front_edge_3d-- (top_xyz, bottom_xyz) of the center-front edge the
                          facing attaches to, in world coords
        * depth_dir    -- unit 3D vector pointing away from the body at the
                          front (the facing folds back opposite to this)
        """
        super().__init__(f'ButtonPlacket_{tag}')

        top, bottom = np.asarray(front_edge_3d[0]), np.asarray(front_edge_3d[1])

        self.facing = StraightBandPanel(f'{tag}_placket', length, width)
        # Place the facing so its inner (seam) edge lies on the front edge,
        # extending outward (+depth) before folding back
        mid = (top + bottom) / 2
        self.facing.translate_to(mid + np.asarray(depth_dir) * (width / 2 + 2))
        # Fold the facing back against the front (~180 deg about its seam edge)
        pre_fold(self.facing, self.facing.interfaces['left'].edges[0], 175)

        self.interfaces = {
            'to_front': self.facing.interfaces['left'],
            'right': self.facing.interfaces['right'],
            'bottom': self.facing.interfaces['bottom'],
        }
