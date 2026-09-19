"""Small, offline fabric collection with property-level evidence and attribution.

Catalog records are templates, never database seeds. Copies and garment snapshots
are detached so a catalog update cannot silently change someone's saved material.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit

from webapp import fabric_formats as formats


def metadata(value):
    """Validate the portable catalog metadata, including untrusted U3M imports."""
    if value is None:
        return None
    fields = ('id', 'composition', 'construction', 'sample', 'notes')
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('Invalid fabric catalog metadata.')
    result = dict(schema=1)
    for key in fields:
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError('Invalid fabric catalog text.')
        result[key] = text
    revision = value.get('revision', 1)
    if type(revision) is not int or not 1 <= revision <= 100000:
        raise ValueError('Invalid fabric catalog revision.')
    result['revision'] = revision
    refs = value.get('references', [])
    if not isinstance(refs, list) or len(refs) > 8:
        raise ValueError('Invalid fabric references.')
    result['references'] = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('Invalid fabric reference.')
        clean = {}
        for key in ('title', 'authors', 'url', 'license', 'license_url'):
            text = ref.get(key, '')
            if not isinstance(text, str) or len(text) > 2000:
                raise ValueError('Invalid fabric reference text.')
            if key in ('url', 'license_url') and text:
                try:
                    parsed = urlsplit(text)
                    safe = parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
                except ValueError:
                    safe = False
                if not safe or any(ord(c) < 33 for c in text):
                    raise ValueError('Fabric source links must use HTTPS.')
            clean[key] = text
        result['references'].append(clean)
    return result


@lru_cache(maxsize=1)
def _records():
    catalog = json.loads(Path(__file__).with_name('fabric_catalog.json').read_text(encoding='utf-8'))
    records = []
    for item in catalog['fabrics']:
        values = formats.properties()
        for key, value in item['estimates'].items():
            values[key].update(value=value, origin='estimated',
                               source='SewEasy starter estimate; not a measurement of this sample.')
        for key, measurement in item.get('measurements', {}).items():
            values[key].update(measurement)
        formats.validate_properties(values)
        info = metadata(dict(schema=1, revision=catalog['revision'], id=item['id'],
            composition=item['composition'], construction=item['construction'],
            sample=item.get('sample', ''), notes=item['notes'],
            references=[catalog['references'][r] for r in item.get('references', [])]))
        content = dict(schema=1, description=item['description'], properties=values,
            appearance={}, curves=[], solver_tuning={}, catalog=info,
            source=dict(format='SewEasy fabric collection', catalog_id=item['id']))
        records.append(dict(id='standard:catalog:' + item['id'], name=item['name'],
                            content=content, standard=True, has_source=False, edit_token=None))
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Duplicate fabric catalog IDs.')
    return records


def standard_fabrics():
    return deepcopy(_records())


def evidence_label(content):
    origins = {p['origin'] for p in content['properties'].values() if p['value'] is not None}
    published = bool(origins & {'measured', 'reported'})
    if published and 'estimated' in origins:
        return 'Measurements + estimates'
    if published:
        return 'Published measurements'
    if 'user' in origins:
        return 'Your values'
    return 'Estimated preset' if 'estimated' in origins else 'No measurements'
