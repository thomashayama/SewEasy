"""Archive text-only browser measurements; generated body/cloth assets stay local."""
import hashlib
import json
import platform
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
reports = {p.name: json.loads(p.read_text()) for p in
           sorted((ROOT / 'output/webgpu/results').glob('*.analysis.json'))}
source = ROOT / 'benchmarks/webgpu'
result = dict(date=date.today().isoformat(), os=platform.platform(),
              hardware=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
                                                '--format=csv,noheader'], text=True).strip(),
              source_base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              final_source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.js')},
              note='Evaluation includes earlier tuning trials. Final source hashes include later validation/UI fixes. '
                   'Each report keeps its own solver settings. No body geometry or cloth positions are archived here.',
              reports=reports)
dest = source / 'results' / f'{result["date"]}.json'
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(result, indent=2))
print(f'Saved {len(reports)} browser trials to {dest}')
