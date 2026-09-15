"""Bundle only the six standard renders from a local browser's saved cache.

Visit Home and allow its browser thumbnail queue to finish, then run:
python benchmarks/export_garment_thumbnails.py .nicegui/storage-user-<id>.json
Personal garments, outfits and measurements are never exported.
"""
import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webapp.garment_catalog import standard_garments
from webapp.thumbnail_cache import normalize_image, thumbnail_key


def export(path):
    cache = json.loads(path.read_text(encoding='utf-8'))['wardrobe'].get('thumbnails', {})
    standards = [(g['name'], thumbnail_key([g])) for g in standard_garments()]
    missing = [name for name, key in standards if key not in cache]
    if missing:
        raise ValueError('Wait for these renders to finish in Home: ' + ', '.join(missing))
    output = ROOT / 'assets/garment_thumbnails'
    output.mkdir(exist_ok=True)
    for name, key in standards:
        image = normalize_image(cache[key])
        (output / f'{key}.webp').write_bytes(base64.b64decode(image.split(',', 1)[1]))
        print(f'{name}: {key}.webp')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storage', type=Path)
    export(parser.parse_args().storage)
