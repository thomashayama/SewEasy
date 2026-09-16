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
from webapp.wardrobe import normalize_library


def export(path):
    library = normalize_library(json.loads(path.read_text(encoding='utf-8'))['wardrobe'])
    cache = library.get('thumbnails', {})
    standards = [(g['name'], g['standard'], cache.get(thumbnail_key('garment', g['id']))) for g in standard_garments()]
    missing = [name for name, key, image in standards if not image]
    if missing:
        raise ValueError('Wait for these renders to finish in Home: ' + ', '.join(missing))
    output = ROOT / 'assets/garment_thumbnails'
    output.mkdir(exist_ok=True)
    for name, key, image in standards:
        image = normalize_image(image)
        (output / f'{key}.webp').write_bytes(base64.b64decode(image.split(',', 1)[1]))
        print(f'{name}: {key}.webp')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storage', type=Path)
    export(parser.parse_args().storage)
