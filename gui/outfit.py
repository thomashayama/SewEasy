"""Draft independent garments together, without sewing one garment to another."""
from copy import deepcopy

from assets.garment_programs.meta_garment import MetaGarment
from seweasy.pattern.wrappers import VisPattern


class OutfitProgram:
    name = 'Configured_outfit'

    def __init__(self, body, items):
        self.items = items
        self.garments = [MetaGarment(f'garment_{i}', body, item['params'])
                         for i, item in enumerate(items)]

    def is_self_intersecting(self):
        return any(g.is_self_intersecting() for g in self.garments)

    def assembly(self):
        result = VisPattern()
        result.name = self.name
        result.pattern['panel_fabrics'] = {}
        result.pattern['button_groups'] = []
        for i, (garment, item) in enumerate(zip(self.garments, self.items)):
            raw = deepcopy(garment.assembly().pattern)
            names = {name: f'g{i}__{name}' for name in raw['panels']}
            result.pattern['panels'].update({names[k]: v for k, v in raw['panels'].items()})
            for seam in raw['stitches']:
                for end in seam[:2]:
                    end['panel'] = names[end['panel']]
            result.pattern['stitches'].extend(raw['stitches'])
            stiff = {**raw.get('panel_stiffness', {}), **item.get('appearance', {}).get('panel_stiffness', {})}
            result.pattern.setdefault('panel_stiffness', {}).update({names[k]: v for k, v in stiff.items() if k in names})
            if raw.get('fabric'):
                overrides = item.get('appearance', {}).get('panel_colors', {})
                result.pattern['panel_fabrics'].update({names[name]: raw['fabric'] for name in names if name not in overrides})
            if raw.get('buttons'):
                result.pattern['button_groups'].append({**raw['buttons'], 'panels': list(names.values())})
        return result
