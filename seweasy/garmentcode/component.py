import numpy as np
from scipy.spatial.transform import Rotation as R

from seweasy.garmentcode.base import BaseComponent
from seweasy.pattern.wrappers import VisPattern


class Component(BaseComponent):
    """Garment element (or whole piece) composed of simpler connected garment
    elements"""

    # TODOLOW Overload copy -- respecting edge sequences -- never had any problems though

    def __init__(self, name) -> None:
        super().__init__(name)

        self.subs = []  # list of generative subcomponents

    def set_panel_label(self, label: str, overwrite=True):
        """Propagate given label to all sub-panels (in subcomponents)"""
        subs = self._get_subcomponents()
        for sub in subs: 
            sub.set_panel_label(label, overwrite)

    def pivot_3D(self):
        """Pivot of a component as a block

            NOTE: The relation of pivots of sub-blocks needs to be
            preserved in any placement operations on components
        """
        mins, maxes = self.bbox3D()
        return np.array(((mins[0] + maxes[0]) / 2, maxes[1],
                         (mins[-1] + maxes[-1]) / 2))

    def length(self):
        """Length of a component in cm
        
            Defaults the to the vertical length of a 3D bounding box
            * longest_dim -- if set, returns the longest dimention out of the bounding box dimentions
        """
        subs = self._get_subcomponents()
        return sum([s.length() for s in subs]) if subs else 0

    def translate_by(self, delta_vector):
        """Translate component by a vector"""
        for subs in self._get_subcomponents():
            subs.translate_by(delta_vector)
        return self
    
    def translate_to(self, new_translation):
        """Set panel translation to be exactly that vector"""
        pivot = self.pivot_3D()
        for subs in self._get_subcomponents():
            sub_pivot = subs.pivot_3D()
            subs.translate_to(np.asarray(new_translation) + (sub_pivot - pivot))
        return self

    def rotate_by(self, delta_rotation: R):
        """Rotate component by a given rotation"""
        pivot = self.pivot_3D()
        for subs in self._get_subcomponents():
            # With preserving relationships between components
            rel = subs.pivot_3D() - pivot
            rel_rotated = delta_rotation.apply(rel) 
            subs.rotate_by(delta_rotation)
            subs.translate_by(rel_rotated - rel)
        return self
    
    def rotate_to(self, new_rot):
        # TODOLOW Implement with correct preservation of relative placement
        # of subcomponents
        raise NotImplementedError(
            f'Component::ERROR::rotate_to is not supported on component level.'
            'Use relative <rotate_by()> method instead')

    def mirror(self, axis=[0, 1]):
        """Swap this component with its mirror image by recursively mirroring
        subcomponents
        
            Axis specifies 2D axis to swap around: Y axis by default
        """
        for subs in self._get_subcomponents():
            subs.mirror(axis)
        return self

    def assembly(self):
        """Construction process of the garment component

        get serializable representation
        Returns: simulator friendly description of component sewing pattern
        """
        spattern = VisPattern()
        spattern.name = self.name

        subs = self._get_subcomponents()
        if not subs:
            return spattern

        # Simple merge of subcomponent representations
        for sub in subs:
            sub_raw = sub.assembly().pattern

            # simple merge of panels
            # (in-place update: rebuilding the dict per sub is quadratic
            # in the total panel count)
            spattern.pattern['panels'].update(sub_raw['panels'])

            # of stitches
            spattern.pattern['stitches'] += sub_raw['stitches']

            # of optional button config (a single dict; last non-empty wins)
            if sub_raw.get('buttons'):
                spattern.pattern['buttons'] = sub_raw['buttons']

            # of optional per-panel stiffness (merge; later subs win per key)
            if sub_raw.get('panel_stiffness'):
                spattern.pattern.setdefault('panel_stiffness', {}).update(
                    sub_raw['panel_stiffness'])

        spattern.pattern['stitches'] += self.stitching_rules.assembly()
        return spattern

    def bbox3D(self):
        """Evaluate 3D bounding box of the current component"""
        
        subs = self._get_subcomponents()
        bboxes = [s.bbox3D() for s in subs]

        if not len(subs):
            # Special components without panel geometry -- no bbox defined
            return np.array([[np.inf, np.inf, np.inf], [-np.inf, -np.inf, -np.inf]])

        mins = np.vstack([b[0] for b in bboxes])
        maxes = np.vstack([b[1] for b in bboxes])

        return mins.min(axis=0), maxes.max(axis=0)

    def is_self_intersecting(self):
        """Check whether the component have self-intersections on panel level"""

        for s in self._get_subcomponents():
            if s.is_self_intersecting():
                return True
        return False

    # Subcomponents
    def _get_subcomponents(self):
        """Unique set of subcomponents defined in the `self.subs` list or as
        attributes of the object

        NOTE: scans instance attributes (vars) rather than dir(): dir()
        sorts every attribute name and getattr()s methods and properties
        too, which is pure overhead on this very hot call (every
        translate/rotate/assembly of every component re-walks the tree).
        Deduplicated by identity, preserving a stable discovery order.
        """
        subs = {}
        for att in vars(self).values():
            if isinstance(att, BaseComponent):
                subs[id(att)] = att
        for att in self.subs:
            subs[id(att)] = att
        return list(subs.values())

