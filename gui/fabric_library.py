"""Approximate fabric presets for the browser solver's bending multiplier.

These are artistic starting points, not measured material constants. Keep the
catalog limited to properties that the simulator actually uses; stretch, mass
and friction need separate per-material solver support before exposing them.
"""

FABRIC_PRESETS = (
    dict(id='chiffon', label='Chiffon', stiffness=0.5, description='Very soft, flowing folds.'),
    dict(id='silk_satin', label='Silk satin', stiffness=1.0, description='Soft folds with a fluid drape.'),
    dict(id='cotton_poplin', label='Cotton poplin', stiffness=2.0, description='Light structure for shirts and dresses.'),
    dict(id='linen', label='Linen', stiffness=2.5, description='A relaxed drape with some body.'),
    dict(id='cotton_twill', label='Cotton twill', stiffness=3.0, description='More structure for trousers and workwear.'),
    dict(id='wool_suiting', label='Wool suiting', stiffness=4.0, description='Structured, rounded folds for tailoring.'),
    dict(id='denim', label='Denim', stiffness=6.0, description='Firm folds that hold their shape.'),
    dict(id='canvas', label='Canvas', stiffness=9.0, description='Stiff, pronounced structure.'),
)

FABRICS_BY_ID = {preset['id']: preset for preset in FABRIC_PRESETS}
