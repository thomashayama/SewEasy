"""Apply a saved fabric's measured properties to the browser garment solver.

The garment solver is isotropic and uses scalar XPBD compliances, so only some
measured properties can change a drape. The rest are carried for provenance and
stay visible as stored-only. The orthotropic membrane model belongs to the
fabric swatch (docs/FabricSwatch.md); this does not add it to garments.
"""

# A fabric at this rigidity drapes exactly like an unassigned panel. It is the
# same assumed default the swatch uses for a material with no bending data.
REFERENCE_BEND_RIGIDITY = 1e-5          # N*m
DEFAULT_GSM = 300.                      # what unassigned garments have always used
MIN_CLEARANCE_M = .004                  # numerical contact margin, not a measurement
STIFFNESS_RANGE = (.5, 30.)
DEFAULT_DAMPING = 2.                    # gui/webgpu/physics.js garment defaults
DEFAULT_FRICTION = .4

# property -> (scope, what the solver actually does with it)
SUPPORT = {
    'weight': ('piece', 'Vertex mass is rest triangle area × g/m².'),
    'bend_warp': ('piece', 'Averaged with the weft rigidity into one isotropic bending multiplier.'),
    'bend_weft': ('piece', 'Averaged with the warp rigidity into one isotropic bending multiplier.'),
    'damping': ('garment', 'Mean over the garment by rest area; pieces without a value count at the '
                           'solver default. The solver damps velocity for the whole garment.'),
    'friction': ('garment', 'Mean over the garment by rest area; pieces without a value count at the '
                            'solver default. Used as the positional body-friction factor, which is '
                            'not a Coulomb coefficient, and scales the body grip.'),
    'thickness': ('garment', 'Raises the 4 mm numerical contact margin when a material is thicker. '
                             'It never lowers the margin and never replaces the measurement.'),
    'stretch_warp': ('stored', 'Garment panels use scalar distance constraints and a strain limiter, '
                               'not N/m membrane stiffness.'),
    'stretch_weft': ('stored', 'Garment panels use scalar distance constraints and a strain limiter, '
                               'not N/m membrane stiffness.'),
    'shear': ('stored', 'No shear model outside the fabric swatch.'),
}


def _value(properties, key):
    item = (properties or {}).get(key) or {}
    value = item.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def rigidity(properties):
    """One isotropic bending rigidity; a garment drape has no warp/weft axis."""
    values = [v for v in (_value(properties, 'bend_warp'), _value(properties, 'bend_weft')) if v]
    return sum(values) / len(values) if values else None


def stiffness_for(material):
    """The existing per-panel bending multiplier, or None to leave a panel alone."""
    measured = rigidity((material or {}).get('properties'))
    if measured is None:
        tuning = (material or {}).get('solver_tuning') or {}
        multiplier = tuning.get('bend_multiplier')
        if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
            return None
        measured = float(multiplier) * REFERENCE_BEND_RIGIDITY
    low, high = STIFFNESS_RANGE
    return min(high, max(low, measured / REFERENCE_BEND_RIGIDITY))


def applied(material):
    """What a saved material does to a drape, and what it only carries."""
    properties = (material or {}).get('properties') or {}
    return dict(weight_gsm=_value(properties, 'weight'), stiffness=stiffness_for(material),
                damping=_value(properties, 'damping'), friction=_value(properties, 'friction'),
                thickness_mm=_value(properties, 'thickness'),
                stored_only=sorted(key for key, (scope, _) in SUPPORT.items()
                                   if scope == 'stored' and _value(properties, key) is not None))


def panel_weights(materials):
    """Areal density per panel, for the scene builder's vertex masses."""
    return {panel: applied(material)['weight_gsm'] for panel, material in (materials or {}).items()
            if applied(material)['weight_gsm']}


def garment_settings(materials, areas):
    """Solver-wide values for controls the garment solver cannot vary per piece.

    Areas are rest areas in m², so a lining panel cannot outvote a whole skirt.
    """
    if not materials:
        return {}
    values = {panel: applied(material) for panel, material in materials.items()}
    result = {}
    total = sum(float(area) for area in areas.values())
    for key, default in (('damping', DEFAULT_DAMPING), ('friction', DEFAULT_FRICTION)):
        # Every piece votes by area. One without a value votes for the solver
        # default, so a single cuff cannot set the whole garment's friction.
        weighted = sum(float(area) * (values[panel][key] if panel in values and values[panel][key] is not None
                                      else default) for panel, area in areas.items())
        result[key] = weighted / total if total else default
    thickness = [item['thickness_mm'] / 1000 for item in values.values() if item['thickness_mm']]
    result['thickness'] = max([MIN_CLEARANCE_M, *thickness])
    return result
