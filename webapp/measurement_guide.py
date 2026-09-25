"""In-app guide for taking body measurements.

Definitions follow `docs/Body Measurements GarmentCode.pdf` (the
authoritative spec for how the pattern framework interprets each value),
rephrased as practical tape-measure instructions. Every entry has a
matching diagram at `assets/img/measurements/<key>.svg`, drawn on the
default mannequin by `assets/img/measurements/generate.py`, and many have a
photo of the measurement being taken (`photos/credits.json` lists each
photo with its author and license).

`essential` marks the measurements shown in the editor's Essential mode:
the ones with the largest effect on fit that a home sewist can take with
a tape measure. The rest keep their profile values (scaled defaults are
usually fine) until edited in All mode.

All lengths are centimeters; angles are degrees.
"""
import json
from functools import lru_cache
from pathlib import Path

DIAGRAM_URL = '/img/measurements'
OVERVIEW_DIAGRAM = f'{DIAGRAM_URL}/overview.svg'
PHOTO_DIR = Path(__file__).resolve().parents[1] / 'assets/img/measurements/photos'
PHOTO_URL = f'{DIAGRAM_URL}/photos'


@lru_cache(maxsize=1)
def _photo_credits():
    try:
        return json.loads((PHOTO_DIR / 'credits.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def photo_for(key: str):
    """{url, credit, link} for a measurement's photo, or None. The credit names author, source and license."""
    entry = _photo_credits().get(key)
    if not entry or not (PHOTO_DIR / entry['file']).is_file():
        return None
    credit = f'Photo: {entry["author"]} · {entry["source"]}'
    if entry.get('license') and entry['source'] == 'Wikimedia Commons':
        credit += f' · {entry["license"]}'
    return dict(url=f'{PHOTO_URL}/{entry["file"]}', credit=credit, link=entry.get('page'))


GENERAL_TIPS = (
    'Measure over underwear or thin, close-fitting clothes. Keep the tape '
    'snug but not tight — it should lie flat on the body without pressing '
    'in. Stand naturally, look straight ahead, and breathe normally. For '
    'circumferences, keep the tape parallel to the floor; a mirror or a '
    'helper makes this much easier.'
)

# --- Skin tones ---
# The Monk Skin Tone (MST) scale: a 10-tone scale of human skin colors by
# Dr. Ellis Monk and Google LLC, CC BY 4.0 — https://skintone.google
# (see the Attribution section in ReadMe.md). The mannequin slider
# interpolates linearly between adjacent tones.
SKIN_TONES = ['#f6ede4', '#f3e7db', '#f7ead0', '#eadaba', '#d7bd96',
              '#a07e56', '#825c43', '#604134', '#3a312a', '#292420']


def _hex_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]


def skin_tone_hex(t) -> str:
    """Interpolate the skin-tone ramp at position t in [0, 1]"""
    t = min(max(float(t), 0.), 1.)
    pos = t * (len(SKIN_TONES) - 1)
    i = min(int(pos), len(SKIN_TONES) - 2)
    frac = pos - i
    c0, c1 = _hex_rgb(SKIN_TONES[i]), _hex_rgb(SKIN_TONES[i + 1])
    rgb = [round(a + (b - a) * frac) for a, b in zip(c0, c1)]
    return '#{:02x}{:02x}{:02x}'.format(*rgb)


def skin_tone_t(hex_color) -> float:
    """Closest slider position on the skin-tone ramp for a stored color"""
    target = _hex_rgb(hex_color)
    return min(
        (i / 100 for i in range(101)),
        key=lambda t: sum((a - b) ** 2
                          for a, b in zip(_hex_rgb(skin_tone_hex(t)), target))
    )


# --- Display units (storage is always centimeters) ---
CM_PER_IN = 2.54
ANGLE_KEYS = {'hip_inclination', 'shoulder_incl', 'arm_pose_angle'}


def display_value(key: str, cm_value, units: str) -> float:
    """Stored cm -> the value shown in the editor (angles pass through)"""
    if units == 'in' and key not in ANGLE_KEYS:
        return round(float(cm_value) / CM_PER_IN, 2)
    return round(float(cm_value), 2)


def stored_value(key: str, shown, units: str, previous_cm=None) -> float:
    """Editor value -> cm for storage.

    When the field is an unchanged round-trip of `previous_cm`, the exact
    previous value is kept so displaying in inches never drifts the
    stored centimeters."""
    value = float(shown)
    if units == 'in' and key not in ANGLE_KEYS:
        value *= CM_PER_IN
    if previous_cm is not None and abs(value - float(previous_cm)) < 0.02:
        return float(previous_cm)
    return round(value, 2)


def unit_suffix(key: str, units: str) -> str:
    """Label suffix for the editor field; angles carry their own (°)"""
    if key in ANGLE_KEYS:
        return ''
    return ' (in)' if units == 'in' else ' (cm)'

# In the order you take them: height, then around the body, then lengths.
# The editors list fields in this order.
GUIDE = {
    'height': dict(
        label='Height', essential=True, view='side',
        how='Your full height without shoes. Stand with heels, seat and '
            'shoulder blades against a wall, rest a hardcover book flat on '
            'your head against the wall, mark its underside and measure from '
            'the floor to the mark.'),

    # --- Around the body ---
    'bust': dict(
        label='Bust', essential=True, view='front',
        how='Around the fullest part of your bust, passing over the bust '
            'points. Keep the tape parallel to the floor all the way around '
            'and don\'t compress the bust.'),
    'underbust': dict(
        label='Underbust', essential=True, view='front',
        how='Around your ribcage directly below the bust, where a bra band '
            'sits. Tape parallel to the floor, snug against the ribs.'),
    'waist': dict(
        label='Waist', essential=True, view='front',
        how='Around your natural waist — roughly midway between your lowest '
            'rib and your hip bones, usually the narrowest part of the '
            'torso. Tie a string there first if you\'re unsure; it settles '
            'into the natural waist when you bend sideways.'),
    'hips': dict(
        label='Hips', essential=True, view='front',
        how='Around the fullest part of your seat, keeping the tape '
            'parallel to the floor. Check in a mirror that the tape sits on '
            'the widest point front and back.'),
    'leg_circ': dict(
        label='Thigh', essential=True, view='front',
        how='Around the thickest part of one thigh, near the top of the '
            'leg. Stand with weight even on both feet.'),
    'wrist': dict(
        label='Wrist', essential=True, view='front',
        how='Around the narrowest part of your wrist, just above the wrist '
            'bone at the root of the hand.'),

    # --- Lengths ---
    'shoulder_w': dict(
        label='Shoulder width', essential=True, view='back',
        how='Across the back, from one shoulder point to the other — the '
            'bony tips where the shoulders begin to curve into the arms. '
            'A helper makes this much easier.'),
    'arm_length': dict(
        label='Arm length', essential=True, view='side',
        how='From the shoulder point down the outside of the arm to the '
            'wrist bone, with the arm relaxed at your side.'),
    'waist_line': dict(
        label='Back length (nape to waist)', essential=True, view='back',
        how='From the nape of your neck (the prominent bone at the base of '
            'the back of the neck) down the center back to waist level. Let '
            'the tape follow the curve of your back.'),
    'hips_line': dict(
        label='Waist to hip', essential=True, view='side',
        how='On your side: the vertical distance from waist level down to '
            'hip level (where you measured the hip circumference).'),
    'inseam': dict(
        label='Inseam (crotch to floor)', essential=True, view='front',
        how='Along the inside of the leg, from the crotch straight down to '
            'the floor, without shoes. Easiest: stand against a wall with a '
            'hardcover book held up between your legs like a saddle, keep it '
            'level, and measure from its top edge to the floor. It sets how '
            'deep the crotch sits below your hips.'),

    # --- Details (the defaults scale with the essentials) ---
    'back_width': dict(
        label='Back width', essential=False, view='back',
        how='Across your back at bust level, from one side line of the '
            'body to the other. This is the back portion of the bust '
            'circumference.'),
    'waist_back_width': dict(
        label='Waist back width', essential=False, view='back',
        how='The back portion of your waist circumference: across your '
            'back at waist level, from the side line of the body on one '
            'side to the other (the "balance line" — the vertical line '
            'running down the middle of your side).'),
    'hip_back_width': dict(
        label='Hip back width', essential=False, view='back',
        how='Across your back at hip level, from one side line of the body '
            'to the other — the back portion of the hip circumference.'),
    'waist_over_bust_line': dict(
        label='Front length over bust', essential=False, view='side',
        how='From the neck base down the front to waist level, passing '
            'over the bust point. Let the tape lie on the body over the '
            'bust like a tailor\'s tape — don\'t bridge it straight down.'),
    'bust_line': dict(
        label='Shoulder to bust point', essential=False, view='side',
        how='From shoulder level down to the bust point, measured along '
            'the same line as the front length. On the body surface, not '
            'straight through the air.'),
    'vert_bust_line': dict(
        label='Nape to bust level', essential=False, view='side',
        how='The vertical drop from the nape of the neck to the height of '
            'the bust circumference. Best taken from a side photo: it\'s a '
            'straight vertical distance, not along the body.'),
    'armscye_depth': dict(
        label='Armscye depth', essential=False, view='back',
        how='On your back: the vertical distance from shoulder level down '
            'to the bottom of the armpit. Hold a ruler horizontally under '
            'the armpit to make the lower point easier to find.'),
    'head_l': dict(
        label='Head length', essential=False, view='side',
        how='From the nape of the neck straight up to the top of your '
            'head (a vertical, straight-line distance).'),
    'neck_w': dict(
        label='Neck width', essential=False, view='back',
        how='The width of the neck base, measured across the back of the '
            'neck from one side to the other.'),
    'bust_points': dict(
        label='Bust point distance', essential=False, view='front',
        how='The horizontal distance between the two bust points, measured '
            'straight across the front.'),
    'bum_points': dict(
        label='Seat point distance', essential=False, view='back',
        how='The horizontal distance between the fullest points of the '
            'seat, measured straight across the back.'),
    'crotch_hip_diff': dict(
        label='Hip to crotch', essential=False, view='side', derived=True,
        how='The vertical distance from hip level down to the crotch. '
            'Worked out from your inseam: height, less head length, back '
            'length, waist to hip and inseam.'),

    # --- Angles ---
    'hip_inclination': dict(
        label='Hip inclination (°)', essential=False, view='front',
        how='The angle your side makes between waist and hip: 0° is a '
            'perfectly vertical side; bigger values mean more hip flare. '
            'Estimate it from a straight-on front photo with a protractor '
            'app, or leave the default.'),
    'shoulder_incl': dict(
        label='Shoulder slope (°)', essential=False, view='front',
        how='The slope of your shoulder line, from the neck base to the '
            'shoulder tip, against horizontal. Around 20° is average; '
            'square shoulders are lower, sloped shoulders higher. A front '
            'photo makes this easy to estimate.'),
}

# Stored with a body but not measured: the 3D preview's arm pose.
NOT_MEASUREMENTS = {'arm_pose_angle'}
# Shown and edited, never stored: inseam sets hip-to-crotch (see apply_inseam).
VIRTUAL = {'inseam'}


def label_for(key: str) -> str:
    entry = GUIDE.get(key)
    return entry['label'] if entry else key.replace('_', ' ').capitalize()


def is_essential(key: str) -> bool:
    entry = GUIDE.get(key)
    return bool(entry and entry['essential'])


def inseam_cm(m: dict) -> float:
    """Crotch height above the floor: what the pattern and the mannequin already imply."""
    return float(m['height']) - sum(float(m[k]) for k in ('head_l', 'waist_line', 'hips_line', 'crotch_hip_diff'))


def apply_inseam(m: dict, inseam: float) -> dict:
    """The measurements with hip-to-crotch set so the crotch sits `inseam` cm above the floor.

    Height, head, back length and waist-to-hip are measured; the crotch depth
    below the hips is the hardest to take yourself, so the inseam decides it.
    """
    result = dict(m)
    result['crotch_hip_diff'] = round(float(m['height']) - float(inseam) - sum(
        float(m[k]) for k in ('head_l', 'waist_line', 'hips_line')), 2)
    return result


def editor_keys(measurements: dict, essential_only: bool) -> list:
    """Editable fields in measuring order: inseam in, derived and non-measurements out."""
    keys = [k for k, entry in GUIDE.items()
            if not entry.get('derived') and (k in measurements or k in VIRTUAL)
            and (entry['essential'] or not essential_only)]
    if not essential_only:
        keys += sorted(k for k in measurements if k not in GUIDE and k not in NOT_MEASUREMENTS
                       and not k.startswith('_'))
    return keys


def editor_values(measurements: dict) -> dict:
    """Stored values plus the virtual inseam, in centimetres."""
    values = dict(measurements)
    try:
        values['inseam'] = round(inseam_cm(measurements), 2)
    except (KeyError, TypeError, ValueError):
        pass
    return values


# --- Keeping hidden measurements consistent with essential edits ---

# Non-essential measurement -> the essential it scales with. When only the
# essentials are edited (Essential mode), each dependent is scaled by its
# parent's ratio so the hidden values stay anatomically plausible instead
# of keeping the mean body's absolute numbers. Angles are left alone.
COUPLED = {
    'waist_back_width': 'waist',
    'back_width': 'bust',
    'bust_points': 'bust',
    'hip_back_width': 'hips',
    'bum_points': 'hips',
    'neck_w': 'shoulder_w',
    'head_l': 'height',
    'vert_bust_line': 'waist_line',
    'bust_line': 'waist_line',
    'waist_over_bust_line': 'waist_line',
    'armscye_depth': 'waist_line',
    # crotch_hip_diff is set from the inseam instead (apply_inseam).
}


def scale_coupled(old: dict, new: dict) -> dict:
    """Values for coupled non-essentials, scaled by their parent's change.

    `old` is the stored profile, `new` the profile with essential edits
    applied. Returns only the entries that actually change.
    """
    updated = {}
    for key, parent in COUPLED.items():
        try:
            old_parent = float(old[parent])
            new_parent = float(new[parent])
            old_value = float(old[key])
        except (KeyError, TypeError, ValueError):
            continue
        if old_parent <= 0 or abs(new_parent - old_parent) < 1e-9:
            continue
        updated[key] = round(old_value * new_parent / old_parent, 2)
    return updated


# --- Validation guardrails ---

def validate_measurements(m: dict):
    """Sanity-check a full measurement set.

    Returns (errors, warnings): errors are mathematically impossible
    combinations that break pattern drafting (negative panel widths,
    negative leg length); warnings are anatomically suspicious values
    that will draft but fit badly.
    """
    def val(key):
        try:
            return float(m[key])
        except (KeyError, TypeError, ValueError):
            return None

    errors, warnings = [], []

    def check(a_key, b_key, message, level=errors, factor=1.0):
        a, b = val(a_key), val(b_key)
        if a is not None and b is not None and a >= b * factor:
            level.append(message)

    # Impossible: front panel widths become zero or negative
    check('waist_back_width', 'waist',
          'Waist back width must be smaller than the waist circumference')
    check('back_width', 'bust',
          'Back width must be smaller than the bust circumference')
    check('hip_back_width', 'hips',
          'Hip back width must be smaller than the hip circumference')
    check('underbust', 'bust',
          'Underbust must be smaller than the bust circumference')
    check('neck_w', 'shoulder_w',
          'Neck width must be smaller than the shoulder width')
    check('vert_bust_line', 'waist_line',
          'Nape-to-bust must be smaller than the back length '
          '(the bust sits above the waist)')
    check('bust_line', 'waist_over_bust_line',
          'Shoulder-to-bust must be smaller than the front length over '
          'the bust (it is part of that line)')

    height = val('height')
    vertical = [val(k) for k in ('head_l', 'waist_line', 'hips_line',
                                 'crotch_hip_diff')]
    if height is not None and all(v is not None for v in vertical) \
            and height <= sum(vertical):
        errors.append(
            'Height is smaller than head length + back length + '
            'waist-to-hip + hip-to-crotch combined — the legs would have '
            'negative length')
    # Hip-to-crotch follows from the inseam: a sum that does not add up shows here.
    crotch = val('crotch_hip_diff')
    if crotch is not None and crotch < 1:
        errors.append(
            'The inseam is too long for your height, back length and '
            'waist-to-hip: it would put the crotch at or above hip level. '
            'Check those four measurements.')
    elif crotch is not None and not 4 <= crotch <= 16:
        warnings.append(
            f'Your inseam puts the crotch {crotch:.1f} cm below hip level '
            '(usually 5–13 cm). Check height, back length, waist-to-hip and '
            'inseam.')

    # Suspicious: drafts, but the front/back split will be badly skewed
    check('waist_back_width', 'waist',
          'Waist back width is over 60% of the waist — garment fronts '
          'will be much narrower than the backs', warnings, factor=0.6)
    check('back_width', 'bust',
          'Back width is over 60% of the bust — garment fronts will be '
          'much narrower than the backs', warnings, factor=0.6)
    check('hip_back_width', 'hips',
          'Hip back width is over 60% of the hips — garment fronts will '
          'be much narrower than the backs', warnings, factor=0.6)
    check('armscye_depth', 'vert_bust_line',
          'Armscye depth reaches below the bust level — check both values',
          warnings)

    return errors, warnings
