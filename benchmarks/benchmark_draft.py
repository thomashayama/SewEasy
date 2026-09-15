"""Compare full SVG drafting with scalar fitting, vector fitting, and caching.

Run in the GUI environment from the repository root. Timings exclude imports
and HTTP delivery; the canvas data-paint-ms attribute measures page delivery.
"""
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assets.garment_programs import sleeves
from gui.gui_pattern import GUIPattern
from seweasy.garmentcode import operators


def scalar_curvature(curve, points_estimates=100):
    return max(curve.curvature(t) for t in np.linspace(0, 1, points_estimates))


def benchmark():
    result = {}
    pattern = GUIPattern(draft=False)
    try:
        for mode in ('scalar_uncached', 'vector_uncached', 'optimized_cold', 'optimized_warm'):
            samples = []
            curvature = patch.object(operators, '_max_curvature', scalar_curvature) if mode == 'scalar_uncached' else nullcontext()
            cache = patch.object(sleeves, '_cached_armhole_curve', sleeves._fit_armhole_curve) if 'uncached' in mode else nullcontext()
            with curvature, cache:
                for _ in range(3):
                    if mode == 'optimized_cold':
                        sleeves._cached_armhole_curve.cache_clear()
                    started = time.perf_counter()
                    pattern.reload_garment()
                    samples.append(round((time.perf_counter() - started) * 1000))
            result[mode] = dict(samples_ms=samples, median_ms=float(np.median(samples)))
    finally:
        pattern.release()
    return result


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2))
