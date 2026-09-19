"""Opt-in validation of locally downloaded vendor packages; never fetch assets.

Run from the repository root: python -m benchmarks.validate_fabric_packages paths...
Supplier assets stay outside the repository; the JSON report records their hashes.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from webapp import fabric_formats as fmt


def validate(path):
    raw = path.read_bytes()
    files, manifest, doc, _ = fmt.read_package(raw, path.name)
    content = fmt.import_fabric(raw, path.name)
    record = dict(id=str(uuid4()), name=content['name'], content=content)
    result = fmt.export_fabric(record, raw, path.name)
    saved_files, _, saved_doc, _ = fmt.read_package(result, 'roundtrip.u3ma')
    reimported = fmt.import_fabric(result, 'roundtrip.u3ma')
    assert set(files) == set(saved_files), 'File inventory changed'
    assert all(saved_files[p] == b for p, b in files.items() if p != manifest), 'Companion bytes changed'
    assert reimported['properties'] == content['properties'], 'Property/provenance drift'
    assert reimported['curves'] == content['curves'], 'Normalized curve drift'
    assert reimported['physics_normalization'] == content['physics_normalization'], 'Normalization drift'
    assert reimported['appearance'] == content['appearance'], 'Appearance drift'
    for key, value in (doc.get('custom') or {}).items():
        if key != 'seweasy':
            assert saved_doc['custom'][key] == value, 'Vendor extension changed'
    return dict(file=path.name, sha256=sha256(raw).hexdigest(), bytes=len(raw),
                name=content['name'], preserved_companions=len(files)-1,
                properties=content['properties'], curves=len(content['curves']),
                warnings=content['physics_normalization']['raw_warnings'], result='pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps([validate(path) for path in args.packages], indent=2, allow_nan=False))
