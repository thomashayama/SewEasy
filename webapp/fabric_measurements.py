"""FAB units and an explicitly estimated short-loop bending fit.

Reported Browzwear stretch is N/m. Vendor bend coefficients are NOT N*m.
For bending we fit raw short-loop compression instead, with per-cycle tare.
This ideal, inextensible, clamped elastica ignores gravity, hysteresis and
clamp compliance; the spread between cycles is retained, not hidden.
"""
import json
import math
from statistics import median

VERSION = 1
GRAM_FORCE_N = .00980665
PHYSICS_REFERENCE = 'https://help.browzwear.com/en/articles/13065506-physics-reference'


def loop_factor(ratio):
    """P / (D * width) for a clamped, first-mode elastica of unit length."""
    from scipy.optimize import brentq
    from scipy.special import ellipk, ellipe
    m = brentq(lambda m: 2 * ellipe(m) / ellipk(m) - 1 - ratio, 0, .999)
    return 16 * float(ellipk(m)) ** 2


def fit_loop(points, length, width):
    """Fit force_N = D * width * factor / L² + a constant tare offset."""
    import numpy as np
    if length <= 0 or width <= 0:
        return None
    selected = [(x, y) for x, y in points if .55 < x / length < .94]
    if len(selected) < 6 or width <= 0 or length <= 0:
        return None
    x = np.array([loop_factor(span / length) / length**2 for span, _ in selected])
    y = np.array([-force / width for _, force in selected])
    if np.ptp(x) < .05 * x.mean() or np.ptp(y) <= 1e-8:
        return None
    centered = x - x.mean()
    rigidity = float(centered @ (y-y.mean()) / (centered @ centered))
    offset = float(y.mean() - rigidity*x.mean())
    error = float(np.sqrt(np.mean((rigidity*x+offset-y)**2)) / np.ptp(y))
    if not math.isfinite(rigidity) or rigidity <= 0 or error > .2:
        return None
    return dict(value=rigidity, normalized_rmse=error, points=len(selected),
                force_offset_n=offset*width)


def normalize(fab):
    """No fetching; skip unsupported/malformed optional measurements."""
    raw = (fab or {}).get('raw_data') or {}
    vendor = ((fab or {}).get('custom') or {}).get('browzwear') or {}
    values, curves, fits = {}, [], {}
    stretch = vendor.get('stretch') if isinstance(vendor, dict) else None
    if isinstance(stretch, dict):
        for axis, field in (('warp', 'length'), ('weft', 'width')):
            try:
                value = float(stretch[field])
                if math.isfinite(value) and value >= 0:
                    values['stretch_'+axis] = dict(value=value, unit='N/m', origin='reported',
                        source=f'FAB custom.browzwear.stretch.{field}; Browzwear Physics Reference (N/m)')
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
    for direction, axis in (('L', 'warp'), ('W', 'weft'), ('B', 'bias')):
        tests = raw.get(direction)
        if not isinstance(tests, dict):
            continue
        axis_fits = []
        for name in ('U1', 'D1', 'D2', 'S1', 'S2'):
            test = tests.get(name)
            if not isinstance(test, dict):
                continue
            try:
                length, width = float(test['length'])*.01, float(test['width'])*.01
                branches = test['samplesTree']
                branches = json.loads(branches) if isinstance(branches, str) else branches
                if not (math.isfinite(length) and math.isfinite(width) and length > 0 and width > 0):
                    continue
                if not isinstance(branches, list):
                    continue
                for branch, pairs in enumerate(branches):
                    if not isinstance(pairs, list) or len(pairs) % 2:
                        continue
                    points = [[float(pairs[i])*.01, float(pairs[i+1])*GRAM_FORCE_N]
                              for i in range(0, len(pairs), 2)]
                    if not all(math.isfinite(v) for p in points for v in p):
                        continue
                    source = f'FAB raw_data.{direction}.{name}.samplesTree[{branch}]'
                    curves.append(dict(direction=axis, test=name, cycle=branch//2,
                        branch='loading' if branch % 2 == 0 else 'unloading',
                        length_m=length, width_m=width, x_unit='m', y_unit='N',
                        points=points, source=source))
                    # Skip conditioning and long loops where self-weight matters more.
                    if axis != 'bias' and name in ('U1', 'D1') and branch > 0 and branch % 2 == 0:
                        fit = fit_loop(points, length, width)
                        if fit:
                            axis_fits.append(dict(fit, source=source))
            except (KeyError, ValueError, TypeError, OverflowError):
                continue
        if len(axis_fits) >= 2:
            estimates = [f['value'] for f in axis_fits]
            key = 'bend_'+axis
            fits[key] = dict(method='clamped-elastica-short-loop-v1', unit='N*m',
                value=median(estimates), range=[min(estimates), max(estimates)], cycles=axis_fits)
            values[key] = dict(value=median(estimates), unit='N*m', origin='estimated',
                source=f'FAB raw_data.{direction} U1/D1 loading cycles; short-loop elastica fit v1')
    return values, curves, dict(version=VERSION, bending_fits=fits, stretch_reference=PHYSICS_REFERENCE)
