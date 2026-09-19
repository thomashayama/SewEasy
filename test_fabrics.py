"""Real U3M measurements, lossless assets, private storage, and safe round trips."""
from contextlib import ExitStack
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User
from webapp import fabrics
from webapp import fabric_formats as fmt


class FormatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = fmt.sample_package()

    def test_published_sample_normalizes_only_known_units(self):
        content = fmt.import_fabric(self.sample, 'cupro.u3ma')
        self.assertEqual(content['name'], 'SU-1098 Cupro')
        self.assertAlmostEqual(content['properties']['weight']['value'], 105.6, places=4)
        self.assertAlmostEqual(content['properties']['thickness']['value'], .10464175)
        self.assertEqual(content['properties']['weight']['origin'], 'measured')
        self.assertEqual(content['properties']['friction']['value'], .2)
        # Vendor coefficients must never be relabeled as normalized SI measurements.
        for key in ('shear', 'damping'):
            self.assertIsNone(content['properties'][key]['value'])
        self.assertAlmostEqual(content['properties']['stretch_warp']['value'], 587.5115966796875)
        self.assertEqual(content['properties']['stretch_warp']['origin'], 'reported')
        self.assertEqual(content['properties']['bend_warp']['origin'], 'estimated')
        self.assertAlmostEqual(content['properties']['bend_warp']['value'], 1.0022226205644924e-5)
        self.assertEqual(len(content['curves']), 102)
        self.assertEqual({c['branch'] for c in content['curves']}, {'loading', 'unloading'})
        self.assertTrue(all(c['x_unit']=='m' and c['y_unit']=='N' for c in content['curves']))
        self.assertEqual(content['solver_tuning'], {})

    def test_export_preserves_original_curves_unknown_vendor_fields_and_assets(self):
        files, manifest, doc, _ = fmt.read_package(self.sample, 'cupro.u3ma')
        doc['custom'] = {'vendor-extension': {'future_field': [1, 2, 'unknown']}}
        files[manifest] = json.dumps(doc).encode()
        files['textures/future.png'] = b'opaque source bytes'
        raw = fmt.pack(files)
        content = fmt.import_fabric(raw, 'cupro.u3ma')
        record = dict(id=str(uuid4()), name='My cupro', content=content)
        result = fmt.export_fabric(record, raw, 'cupro.u3ma')
        saved_files, _, saved_doc, _ = fmt.read_package(result, 'saved.u3ma')
        for path in files:
            if path != manifest:
                self.assertEqual(saved_files[path], files[path])
        self.assertEqual(saved_doc['custom']['vendor-extension'], doc['custom']['vendor-extension'])
        self.assertEqual(saved_doc['material']['id'], record['id'])
        self.assertEqual(fmt.import_fabric(result, 'saved.u3ma')['properties'], content['properties'])

    def test_u3ma_headers_follow_restricted_zip_spec(self):
        raw = self.sample
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.comment, b'')
            self.assertEqual(archive.infolist()[0].header_offset, 0)
            for entry in archive.infolist():
                self.assertEqual((entry.create_system, entry.create_version, entry.extract_version), (0, 63, 20))
                self.assertEqual(entry.flag_bits, 0x800)
                self.assertEqual((entry.extra, entry.comment), (b'', b''))
                self.assertEqual((entry.internal_attr, entry.external_attr), (0, 0))
                local = struct.unpack_from('<4s5H3I2H', raw, entry.header_offset)
                self.assertEqual(local[0], b'PK\x03\x04')
                self.assertEqual(local[1:4], (20, 0x800, 8))
                self.assertEqual(local[6:9], (entry.CRC, entry.compress_size, entry.file_size))
                self.assertEqual(local[10], 0)
        self.assertEqual(raw[-22:-18], b'PK\x05\x06')

    def test_standalone_and_nested_manifest(self):
        doc = fmt.empty_document('Unmeasured cotton')
        standalone = json.dumps(doc).encode()
        self.assertIsNone(fmt.import_fabric(standalone, 'cotton.u3m')['properties']['weight']['value'])
        files, _, _, _ = fmt.read_package(self.sample, 'sample.u3ma')
        nested = fmt.pack({'nested/' + path: raw for path, raw in files.items()})
        self.assertAlmostEqual(fmt.import_fabric(nested, 'nested.zip')['properties']['weight']['value'], 105.6, places=4)

    def test_missing_companion_file_does_not_fetch_or_guess(self):
        files, manifest, _, _ = fmt.read_package(self.sample, 'sample.u3ma')
        with self.assertRaisesRegex(ValueError, 'Missing companion'):
            fmt.import_fabric(files[manifest], 'sample.u3m')

    def test_rejects_wrong_schema_missing_fields_and_nonfinite_json(self):
        doc = fmt.empty_document('test')
        variants = [dict(doc, schema='1.0'), dict(schema='1.1'), dict(doc, custom={'x': float('nan')})]
        for variant in variants:
            with self.subTest(variant=str(variant)[:30]), self.assertRaises(ValueError):
                fmt.import_fabric(json.dumps(variant).encode(), 'test.u3m')
        with self.assertRaises(ValueError):
            fmt.import_fabric(b'{"schema":"1.1","schema":"1.1"}', 'test.u3m')
        with self.assertRaises(ValueError):
            fmt.import_fabric(b'{"a":1e999}', 'test.u3m')

    def test_rejects_traversal_duplicates_links_and_bombs(self):
        for name in ('../escape.u3m', '/absolute.u3m', 'C:/absolute.u3m', 'a\\b.u3m', 'a/./b.u3m'):
            output = BytesIO()
            with ZipFile(output, 'w') as archive:
                archive.writestr(name, b'{}')
            with self.subTest(name=name), self.assertRaises(ValueError):
                fmt.import_fabric(output.getvalue(), 'bad.u3ma')
        output = BytesIO()
        with ZipFile(output, 'w') as archive:
            archive.writestr('A.u3m', b'{}')
            archive.writestr('a.u3m', b'{}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            fmt.import_fabric(output.getvalue(), 'bad.zip')
        info = ZipInfo('link.u3m')
        info.create_system, info.external_attr = 3, 0o120777 << 16
        output = BytesIO()
        with ZipFile(output, 'w') as archive:
            archive.writestr(info, b'outside')
        with self.assertRaisesRegex(ValueError, 'links'):
            fmt.import_fabric(output.getvalue(), 'link.zip')
        with patch.object(fmt, 'MAX_EXPANDED', 100), self.assertRaisesRegex(ValueError, 'uncompressed'):
            fmt.import_fabric(self.sample, 'bomb.zip')
        with self.assertRaises(ValueError):
            fmt.import_fabric(b'not a zip', 'broken.u3ma')

    def test_unknown_vendor_shape_and_missing_measurements(self):
        files, manifest, doc, fab = fmt.read_package(self.sample, 'sample.u3ma')
        fab['custom']['browzwear'] = 'future vendor format'
        fab['raw_data'] = None
        files['physics.json'] = json.dumps(fab).encode()
        content = fmt.import_fabric(fmt.pack(files), 'empty.u3ma')
        self.assertTrue(all(p['value'] is None for p in content['properties'].values()))


class FabricStorageTest(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        temp = stack.enter_context(TemporaryDirectory())
        self.engine = create_engine('sqlite:///' + str(Path(temp) / 'fabrics.db'))
        stack.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        sessions = sessionmaker(bind=self.engine)
        stack.enter_context(patch.object(fabrics, 'SessionLocal', sessions))
        with sessions() as db:
            db.add_all([User(email='alice@example.test'), User(email='bob@example.test')])
            db.commit()
        self.alice, self.bob = 'alice@example.test', 'bob@example.test'
        self.raw = fmt.sample_package()
        self.record = fabrics.import_fabric(self.alice, self.raw, 'sample.u3ma')

    def save(self, record=None, **kwargs):
        r = record or self.record
        return fabrics.update_fabric(self.alice, r['id'], r['edit_token'],
            name=kwargs.get('name', r['name']), description=kwargs.get('description', r['content']['description']),
            values=kwargs.get('values', {}))

    def test_persistence_copy_identity_and_private_source(self):
        record = fabrics.get_fabric(self.alice, self.record['id'])
        self.assertEqual(record['content'], self.record['content'])
        self.assertEqual(fabrics.original_file(self.alice, record['id']), ('sample.u3ma', self.raw))
        copied = fabrics.copy_fabric(self.alice, record['id'])
        self.assertNotEqual(copied['id'], record['id'])
        self.assertEqual(copied['name'], record['name'] + ' (copy)')
        self.assertEqual(copied['content'], record['content'])
        self.assertEqual(fabrics.original_file(self.alice, copied['id'])[1], self.raw)
        saved = self.save(copied, name='Lightweight lining', values={'weight': 80})
        self.assertEqual(saved['id'], copied['id'])
        self.assertAlmostEqual(fabrics.get_fabric(self.alice, record['id'])['content']['properties']['weight']['value'], 105.6, places=4)

    def test_other_account_cannot_read_update_copy_export_or_download(self):
        identity = self.record['id']
        self.assertEqual(fabrics.list_fabrics(self.bob), [])
        for operation in (fabrics.get_fabric, fabrics.copy_fabric, fabrics.export_fabric, fabrics.original_file, fabrics.snapshot):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(ValueError, 'unavailable'):
                operation(self.bob, identity)
        with self.assertRaises(ValueError):
            fabrics.update_fabric(self.bob, identity, self.record['edit_token'], name='Stolen', description='', values={})
        with self.assertRaises(ValueError):
            fabrics.list_fabrics(None)

    def test_edits_roundtrip_without_modifying_original_and_no_lost_updates(self):
        snapshot = fabrics.snapshot(self.alice, self.record['id'])
        changed = self.save(values={'weight': '700', 'friction': ''})
        self.assertEqual(changed['content']['properties']['weight']['origin'], 'user')
        self.assertIsNone(changed['content']['properties']['friction']['value'])
        with self.assertRaisesRegex(ValueError, 'another tab'):
            self.save(name='Stale tab overwrite')
        exported = fabrics.export_fabric(self.alice, self.record['id'])
        imported = fabrics.import_fabric(self.alice, exported, 'edited.u3ma')
        self.assertEqual(imported['content']['properties'], changed['content']['properties'])
        self.assertEqual(fabrics.original_file(self.alice, self.record['id'])[1], self.raw)
        self.assertAlmostEqual(snapshot['properties']['weight']['value'], 105.6, places=4)
        self.assertEqual(snapshot['source_fabric_id'], self.record['id'])
        self.assertNotIn('edit_token', snapshot)

    def test_unchanged_values_preserve_measurement_provenance(self):
        value = self.record['content']['properties']['weight']['value']
        saved = self.save(values={'weight': str(value)})
        self.assertEqual(saved['content']['properties']['weight']['origin'], 'measured')

    def test_standard_presets_are_unknown_measurements_with_separate_tuning(self):
        standard = fabrics.standard_fabrics()[0]
        self.assertTrue(all(p['value'] is None for p in standard['content']['properties'].values()))
        self.assertIn('bend_multiplier', standard['content']['solver_tuning'])
        with self.assertRaisesRegex(ValueError, 'Save a copy'):
            self.save(standard)
        copied = fabrics.copy_fabric(self.alice, standard['id'])
        self.assertFalse(copied['standard'])
        self.assertEqual(copied['content'], standard['content'])
        fmt.import_fabric(fabrics.export_fabric(self.alice, standard['id']), 'standard.u3ma')

    def test_invalid_values_and_names_are_atomic(self):
        for value in ('NaN', 'inf', '-3', '0', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(values={'weight': value})
        with self.assertRaises(ValueError):
            self.save(name='')
        duplicate = fabrics.create_fabric(self.alice, 'Other')
        with self.assertRaises(ValueError):
            self.save(name=duplicate['name'])
        self.assertEqual(fabrics.get_fabric(self.alice, self.record['id'])['edit_token'], self.record['edit_token'])
        high = self.save(values={'weight': '3500'})
        self.assertEqual(high['content']['properties']['weight']['value'], 3500)

    def test_library_listing_does_not_load_original_blobs(self):
        queries = []
        def observe(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)
        event.listen(self.engine, 'before_cursor_execute', observe)
        try:
            records = fabrics.list_fabrics(self.alice)
        finally:
            event.remove(self.engine, 'before_cursor_execute', observe)
        self.assertNotIn('source_bytes', ' '.join(queries))
        self.assertNotIn('source_bytes', records[0])

    def test_weight_preview_is_private_and_scales_mass_not_gravity(self):
        from webapp import fabric_preview as preview
        scene = preview.default_scene()
        app = FastAPI()
        preview.register(app)
        with patch.object(preview, 'default_scene', return_value=scene), \
                patch.object(preview.auth, 'current_user', return_value={'email': self.alice}) as identity, TestClient(app) as client:
            url = '/fabric-preview/' + self.record['id']
            reference = client.get(url + '?direction=weft')
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'private, no-store')
            measured = response.json()
            ratio = self.record['content']['properties']['weight']['value'] / 300
            self.assertAlmostEqual(measured['fabric_test']['total_mass_kg'], sum(scene['vertex_mass_kg']) * ratio)
            self.assertEqual(measured['constraints'], scene['constraints'])
            self.assertEqual(measured['vertices'], reference.json()['vertices'])
            self.assertEqual(measured['fabric_test']['direction'], 'warp')
            self.assertEqual(reference.json()['fabric_test']['direction'], 'weft')
            self.assertEqual(client.get(url+'?direction=invalid').status_code, 404)
            identity.return_value = {'email': self.bob}
            self.assertEqual(client.get(url).status_code, 404)
            identity.return_value = None
            self.assertEqual(client.get(url).status_code, 404)
        for value in (None, 0, -2, 1e300, 1e-300):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview.with_weight(scene, value)

    def test_legacy_detail_derives_measurements_but_preserves_edits_and_clears(self):
        from webapp.models import Fabric
        with fabrics.SessionLocal() as db:
            row = db.get(Fabric, self.record['id'])
            content = deepcopy(row.content)
            content.pop('physics_normalization')
            content['properties']['bend_warp'].update(value=None, origin='unknown', source=None)
            content['properties']['stretch_warp'].update(value=321., origin='user', source=None)
            row.content = content
            db.commit()
        derived = fabrics.get_fabric(self.alice, self.record['id'])
        self.assertIsNotNone(derived['content']['properties']['bend_warp']['value'])
        self.assertEqual(derived['content']['properties']['stretch_warp']['value'], 321.)
        saved = self.save(derived, values={'bend_warp': ''})
        self.assertIsNone(fabrics.get_fabric(self.alice, saved['id'])['content']['properties']['bend_warp']['value'])
        exported = fabrics.export_fabric(self.alice, saved['id'])
        self.assertIsNone(fmt.import_fabric(exported, 'saved.u3ma')['properties']['bend_warp']['value'])


class MeasurementFitTest(unittest.TestCase):
    def test_elastica_recovers_rigidity_despite_force_tare(self):
        import numpy as np
        from webapp.fabric_measurements import fit_loop, loop_factor
        rigidity, length, width, tare = 2.5e-5, .02, .05, .012
        points = [(r*length, -(rigidity*width*loop_factor(r)/length**2 + tare))
                  for r in np.linspace(.56, .93, 20)]
        fit = fit_loop(points, length, width)
        self.assertAlmostEqual(fit['value'], rigidity, places=12)
        self.assertAlmostEqual(fit['force_offset_n'], tare, places=12)
        self.assertLess(fit['normalized_rmse'], 1e-10)
        self.assertIsNone(fit_loop([[.018, 0]]*10, length, width))
        self.assertIsNone(fit_loop([[x, -y] for x,y in points], length, width))

    def test_raw_force_units_and_vendor_bend_are_not_confused(self):
        from webapp.fabric_measurements import normalize, GRAM_FORCE_N
        fab = json.loads((fmt.SPEC/'cupro_physics.json').read_text())
        values, curves, _ = normalize(fab)
        pair = fab['raw_data']['L']['U1']['samplesTree'][0][:2]
        curve = next(c for c in curves if c['source']=='FAB raw_data.L.U1.samplesTree[0]')
        self.assertEqual(curve['points'][0], [pair[0]*.01, pair[1]*GRAM_FORCE_N])
        fab['raw_data'] = None
        reported, _, _ = normalize(fab)
        self.assertNotIn('bend_warp', reported)
        self.assertNotIn('shear', reported)
        self.assertIn('stretch_warp', reported)

    def test_zero_missing_and_bad_optional_data(self):
        from webapp.fabric_measurements import normalize
        values, _, _ = normalize({'custom':{'browzwear':{'stretch':{'length':0,'width':'NaN'}}}})
        self.assertEqual(values['stretch_warp']['value'], 0)
        self.assertNotIn('stretch_weft', values)
        self.assertEqual(normalize({'raw_data':{'L':{'U1':{'length':2,'width':5,'samplesTree':'bad'}}}})[0], {})


class FabricSceneTest(unittest.TestCase):
    def test_material_axes_energy_area_load_and_missing_vs_zero(self):
        from webapp.fabric_preview import default_scene
        from webapp.fabric_swatch import apply_material
        p = fmt.properties()
        for key, value in dict(weight=100, stretch_warp=500, stretch_weft=1000,
                               bend_warp=1e-5, bend_weft=2e-5, shear=0, damping=0).items():
            p[key].update(value=value, origin='user')
        warp = apply_material(default_scene(), p, 'warp', 'stretch')
        weft = apply_material(default_scene(), p, 'weft', 'stretch')
        for a,b in zip(warp['membranes'], weft['membranes']):
            self.assertAlmostEqual(a['compliance'][0], b['compliance'][1])
            self.assertEqual(a['compliance'][2], -1)
            self.assertAlmostEqual(a['compliance'][0], 1/(.00005*500))
        self.assertAlmostEqual(sum(f[0] for f in warp['external_forces']), 1.)
        self.assertEqual(warp['fabric_test']['gravity'], 0)
        self.assertEqual(warp['fabric_test']['damping'], 0)
        self.assertAlmostEqual(warp['fabric_test']['expected_extension_percent'], 5)
        p['damping']['value'] = None
        self.assertEqual(apply_material(default_scene(),p)['fabric_test']['applied']['damping']['origin'], 'assumed')
        for start,count in warp['membrane_batches']:
            ids=[i for m in warp['membranes'][start:start+count] for i in m['ids']]
            self.assertEqual(len(ids),len(set(ids)))

    def test_swatch_mass_matches_area_times_imported_gsm_including_clamp(self):
        import numpy as np
        from webapp.fabric_preview import default_scene, with_weight
        scene = default_scene()
        triangles = np.asarray(scene['uv'])[scene['faces']]
        area = abs(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])).sum() / 2
        content = fmt.import_fabric(fmt.sample_package(), 'cupro.u3ma')
        gsm = content['properties']['weight']['value']
        measured = with_weight(scene, gsm)
        self.assertAlmostEqual(sum(measured['vertex_mass_kg']), area * gsm / 1000, places=10)
        self.assertAlmostEqual(measured['fabric_test']['total_mass_kg'], area * gsm / 1000, places=10)
        self.assertAlmostEqual(sum(scene['vertex_mass_kg']), area * .3, places=10)
        self.assertEqual(measured['constraints'], scene['constraints'])
        self.assertEqual(measured['interior_hinges'], scene['interior_hinges'])
        for i, (mass, inverse) in enumerate(zip(measured['vertex_mass_kg'], measured['inverse_mass'])):
            if i in scene['swatch']['pins']:
                self.assertEqual(inverse, 0)
            else:
                self.assertAlmostEqual(mass * inverse, 1)
        self.assertAlmostEqual(area, .09*.04)

    def test_swatches_have_a_clamped_root_and_no_constraint_write_races(self):
        from webapp.fabric_preview import default_scene
        scene = default_scene()
        self.assertEqual(len(scene['swatch']['pins']), 10)
        self.assertTrue(all(scene['vertices'][i][0] <= 0 for i in scene['swatch']['pins']))
        self.assertTrue(all(abs(scene['vertices'][i][0]-.08) < 1e-12 for i in scene['swatch']['tip']))
        for key, batches, indices in (('constraints', 'batches', lambda c: c[:2]),
                                      ('interior_hinges', 'interior_hinge_batches', lambda h: h['ids'])):
            for start, count in scene[batches]:
                vertices = [i for c in scene[key][start:start+count] for i in indices(c)]
                self.assertEqual(len(set(vertices)), len(vertices))
        self.assertTrue(all(h['compliance'] > 0 and h['angle'] == 0 for h in scene['interior_hinges']))


if __name__ == '__main__':
    unittest.main()
