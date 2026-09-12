"""Archive text-only browser measurements; generated body/cloth assets stay local."""
import hashlib
import argparse
import json
import platform
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--refinement', action='store_true', help='Archive the refinement trials separately from the original baseline')
args = parser.parse_args()
reports = {p.name: json.loads(p.read_text()) for p in
           sorted((ROOT / 'output/webgpu/results').glob('*.analysis.json'))}
baseline_checks = {}
if args.refinement:
    baseline_checks = {name: report for name, report in reports.items()
                       if not report.get('implementation') and 'body_surface_samples' in report.get('offline_quality', {})}
    reports = {name: report for name, report in reports.items() if report.get('implementation') == 'principal-strain-v1'}
selected = {}
for name, report in reports.items():
    if (report.get('surface_contact_samples_per_triangle') == 4 and report.get('start_frame') == 0
            and report['settings']['width'] == 1 and report.get('fitting_support') is not None):
        selected[report['scene']] = name
source = ROOT / 'benchmarks/webgpu'
result = dict(date=date.today().isoformat(), os=platform.platform(),
              hardware=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
                                                '--format=csv,noheader'], text=True).strip(),
              source_base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              final_source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.js')},
              note='Evaluation includes earlier tuning trials. Final source hashes include later validation/UI fixes. '
                   'Each report keeps its own solver settings. No body geometry or cloth positions are archived here.',
              selected_final_baselines=selected, baseline_surface_cross_checks=baseline_checks, reports=reports)
suffix = '-refined' if args.refinement else ''
dest = source / 'results' / f'{result["date"]}{suffix}.json'
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(result, indent=2))
print(f'Saved {len(reports)} browser trials to {dest}')
