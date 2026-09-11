"""Save text-only evidence to git; body geometry and garment recordings stay local."""
import json
import platform
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/simulator-benchmark'
reports = {}
for path in sorted(OUTPUT.glob('*/*/result.json')):
    report = json.loads(path.read_text())
    # This early location heuristic was not a reliable garment-fit test.
    report.get('quality', {}).pop('retained_on_body', None)
    report.pop('traceback', None)
    reports[path.parent.relative_to(OUTPUT).as_posix()] = report
stamp = date.today().isoformat()
snapshot = dict(date=stamp,
                source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                hardware=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
                                                  '--format=csv,noheader'], text=True).strip(),
                os=platform.platform(),
                method='One run per configuration; no simultaneous GPU benchmark processes. '
                       'Frame percentiles are within-run distributions, not confidence intervals.',
                reports=reports,
                verification=json.loads((OUTPUT / 'verification.json').read_text()))
dest = ROOT / f'benchmarks/results/{stamp}.json'
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(snapshot, indent=2))
print(f'Saved {len(reports)} trials to {dest}')
