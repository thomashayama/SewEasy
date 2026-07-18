"""In-app guide for taking body measurements.

Definitions follow `docs/Body Measurements GarmentCode.pdf` (the
authoritative spec for how the pattern framework interprets each value),
rephrased as practical tape-measure instructions. Every entry has a
matching diagram at `assets/img/measurements/<key>.svg`, generated from
the mean-body outline by `assets/img/measurements/generate.py`.

`essential` marks the measurements shown in the editor's Essential mode:
the ones with the largest effect on fit that a home sewist can take with
a tape measure. The rest keep their profile values (scaled defaults are
usually fine) until edited in All mode.

All lengths are centimeters; angles are degrees.
"""

DIAGRAM_URL = '/img/measurements'
OVERVIEW_DIAGRAM = f'{DIAGRAM_URL}/overview_body_measures.svg'
# CC BY-SA 3.0 attribution for the overview illustration (see ReadMe.md)
OVERVIEW_CREDIT = ('Overview illustration: "Body measures SVG" by '
                   'MagentaGreen, CC BY-SA 3.0, via Wikimedia Commons')

GENERAL_TIPS = (
    'Measure over underwear or thin, close-fitting clothes. Keep the tape '
    'snug but not tight — it should lie flat on the body without pressing '
    'in. Stand naturally, look straight ahead, and breathe normally. For '
    'circumferences, keep the tape parallel to the floor; a mirror or a '
    'helper makes this much easier. All lengths are in centimeters.'
)

GUIDE = {
    # --- Circumferences ---
    'height': dict(
        label='Height', essential=True,
        how='Your full height without shoes. Stand straight with your back '
            'against a wall and measure from the floor to the top of your '
            'head.'),
    'bust': dict(
        label='Bust', essential=True,
        how='Around the fullest part of your bust, passing over the bust '
            'points. Keep the tape parallel to the floor all the way around '
            'and don\'t compress the bust.'),
    'underbust': dict(
        label='Underbust', essential=True,
        how='Around your ribcage directly below the bust, where a bra band '
            'sits. Tape parallel to the floor, snug against the ribs.'),
    'waist': dict(
        label='Waist', essential=True,
        how='Around your natural waist — roughly midway between your lowest '
            'rib and your hip bones, usually the narrowest part of the '
            'torso. Tie a string there first if you\'re unsure; it settles '
            'into the natural waist when you bend sideways.'),
    'hips': dict(
        label='Hips', essential=True,
        how='Around the fullest part of your seat, keeping the tape '
            'parallel to the floor. Check in a mirror that the tape sits on '
            'the widest point front and back.'),
    'leg_circ': dict(
        label='Thigh', essential=True,
        how='Around the thickest part of one thigh, near the top of the '
            'leg. Stand with weight even on both feet.'),
    'wrist': dict(
        label='Wrist', essential=True,
        how='Around the narrowest part of your wrist, just above the wrist '
            'bone at the root of the hand.'),

    # --- Back widths ---
    'waist_back_width': dict(
        label='Waist back width', essential=False,
        how='The back portion of your waist circumference: across your '
            'back at waist level, from the side line of the body on one '
            'side to the other (the "balance line" — the vertical line '
            'running down the middle of your side).'),
    'back_width': dict(
        label='Back width', essential=False,
        how='Across your back at bust level, from one side line of the '
            'body to the other. This is the back portion of the bust '
            'circumference.'),
    'hip_back_width': dict(
        label='Hip back width', essential=False,
        how='Across your back at hip level, from one side line of the body '
            'to the other — the back portion of the hip circumference.'),

    # --- Lengths & distances ---
    'waist_line': dict(
        label='Back length (nape to waist)', essential=True,
        how='From the nape of your neck (the prominent bone at the base of '
            'the back of the neck) down the center back to waist level. Let '
            'the tape follow the curve of your back.'),
    'waist_over_bust_line': dict(
        label='Front length over bust', essential=False,
        how='From the neck base down the front to waist level, passing '
            'over the bust point. Let the tape lie on the body over the '
            'bust like a tailor\'s tape — don\'t bridge it straight down.'),
    'bust_line': dict(
        label='Shoulder to bust point', essential=False,
        how='From shoulder level down to the bust point, measured along '
            'the same line as the front length. On the body surface, not '
            'straight through the air.'),
    'vert_bust_line': dict(
        label='Nape to bust level', essential=False,
        how='The vertical drop from the nape of the neck to the height of '
            'the bust circumference. Best taken from a side photo: it\'s a '
            'straight vertical distance, not along the body.'),
    'arm_length': dict(
        label='Arm length', essential=True,
        how='From the tip of your shoulder (the bony point where the '
            'shoulder meets the arm) down to your wrist, with the arm '
            'relaxed at your side or slightly bent.'),
    'armscye_depth': dict(
        label='Armscye depth', essential=False,
        how='On your back: the vertical distance from shoulder level down '
            'to the bottom of the armpit. Hold a ruler horizontally under '
            'the armpit to make the lower point easier to find.'),
    'head_l': dict(
        label='Head length', essential=False,
        how='From the nape of the neck straight up to the top of your '
            'head (a vertical, straight-line distance).'),
    'shoulder_w': dict(
        label='Shoulder width', essential=True,
        how='Across the front, from the outer end of one collarbone to the '
            'outer end of the other — the bony points where the shoulders '
            'begin to curve into the arms.'),
    'neck_w': dict(
        label='Neck width', essential=False,
        how='The width of the neck base, measured across the back of the '
            'neck from one side to the other.'),
    'bust_points': dict(
        label='Bust point distance', essential=False,
        how='The horizontal distance between the two bust points, measured '
            'straight across the front.'),
    'bum_points': dict(
        label='Seat point distance', essential=False,
        how='The horizontal distance between the fullest points of the '
            'seat, measured straight across the back.'),
    'hips_line': dict(
        label='Waist to hip', essential=True,
        how='On your side: the vertical distance from waist level down to '
            'hip level (where you measured the hip circumference).'),
    'crotch_hip_diff': dict(
        label='Hip to crotch', essential=False,
        how='The vertical distance from hip level down to the deepest '
            'point of the crotch. Easiest sitting on a hard chair: measure '
            'at the side from your hip line down to the seat, then '
            'subtract the waist-to-hip value if you started at the waist.'),

    # --- Angles ---
    'hip_inclination': dict(
        label='Hip inclination (°)', essential=False,
        how='The angle your side makes between waist and hip: 0° is a '
            'perfectly vertical side; bigger values mean more hip flare. '
            'Estimate it from a straight-on front photo with a protractor '
            'app, or leave the default.'),
    'shoulder_incl': dict(
        label='Shoulder slope (°)', essential=False,
        how='The slope of your shoulder line, from the neck base to the '
            'shoulder tip, against horizontal. Around 20° is average; '
            'square shoulders are lower, sloped shoulders higher. A front '
            'photo makes this easy to estimate.'),
    'arm_pose_angle': dict(
        label='Arm pose angle (°)', essential=False,
        how='Not a body measurement: the arm pose (from vertical) used '
            'when draping garments in 3D. Leave at the default unless you '
            'specifically need a different pose.'),
}


def label_for(key: str) -> str:
    entry = GUIDE.get(key)
    return entry['label'] if entry else key.replace('_', ' ').capitalize()


def is_essential(key: str) -> bool:
    entry = GUIDE.get(key)
    return bool(entry and entry['essential'])


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
    'crotch_hip_diff': 'hips_line',
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
