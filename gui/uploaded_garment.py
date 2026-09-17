"""Adapter for a validated, self-contained uploaded sewing-pattern definition."""
from copy import deepcopy
from seweasy.pattern.wrappers import VisPattern


class UploadedGarment:
    def __init__(self, params):
        self.params = params

    def assembly(self):
        pattern = VisPattern()
        pattern.name = 'Uploaded_garment'
        pattern.spec = deepcopy(self.params['_custom_pattern'])
        pattern.pattern = pattern.spec['pattern']
        pattern.properties = pattern.spec['properties']
        fit = self.params.get('pattern_fit', {})
        width, height = (fit.get(k, {}).get('v', 1.) for k in ('width', 'height'))
        if width <= 0 or height <= 0:
            raise ValueError('Pattern width and height must be positive.')
        for panel in pattern.pattern['panels'].values():
            panel['vertices'] = [[x * width, y * height] for x, y in panel['vertices']]
            panel['translation'][0] *= width
            panel['translation'][1] *= height
        return pattern

    def is_self_intersecting(self):
        return self.assembly().is_self_intersecting()
