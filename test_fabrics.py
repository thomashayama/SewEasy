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

from PIL import Image

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User
from webapp import fabrics
from webapp import fabric_formats as fmt


def shirley_package():
    doc = fmt.empty_document('QA Test Fabric shirley')
    doc['material']['physics']['devices']['fab'] = 'physics.json'
    return fmt.pack({'material.u3m': json.dumps(doc).encode(),
                     'physics.json': (fmt.SPEC/'shirley_physics.json').read_bytes()})


def image_bytes(pixels, kind='PNG', color=(190, 170, 150)):
    buffer = BytesIO()
    Image.new('RGB', pixels, color).save(buffer, format=kind)
    return buffer.getvalue()


def image_node(path, pixels=(256, 256), dpi=300, scale=1.):
    """A U3M 1.1 image: physical millimetres, dpi per axis, and a repeat mode."""
    return dict(path=path, dpi=dict(x=dpi, y=dpi), repeat=dict(rotation=0, mode='normal'),
                width=pixels[0]/dpi*25.4*scale, height=pixels[1]/dpi*25.4*scale)


def side(basecolor=None, normal=None, preview=None):
    """Every required 1.1 visualisation slot, with textures only where given."""
    values = dict(alpha=1, anisotropy_value=0, anisotropy_rotation=0, clearcoat_value=0,
                  clearcoat_roughness=0, ior=1.4, metalness=0, displacement=0, roughness=.7,
                  sheen_value=0, sheen_tint=0, specular_value=.5, specular_tint=0,
                  subsurface_radius=0, subsurface_value=0, transmission=0)
    result = {key: dict(constant=value, texture=None) for key, value in values.items()}
    result.update(shader='principled', preview=preview,
                  basecolor=dict(constant=dict(r=.5, g=.5, b=.5), texture=None if basecolor is None else
                                 dict(mode='multiply', factor=dict(r=1, g=1, b=1), image=basecolor)),
                  subsurface_color=dict(constant=dict(r=0, g=0, b=0), texture=None),
                  clearcoat_normal=dict(constant=dict(x=0, y=0, z=1), texture=None),
                  normal=dict(constant=dict(x=0, y=0, z=1), texture=None if normal is None else
                              dict(scale=1., image=normal)))
    return result


def appearance_package(scale=1., files=None, back=False, edit=None):
    """An appearance-only material: real textures, no measurements at all."""
    doc = fmt.empty_document('Printed cotton lawn')
    doc['material']['front'] = side(basecolor=image_node('textures/base.png', scale=scale),
                                    normal=image_node('textures/normal.png', (128, 128)),
                                    preview=dict(path='preview.jpg', dpi=dict(x=300, y=300),
                                                 width=64/300*25.4, height=64/300*25.4))
    extra = {}
    if back:                            # A wrong side with its own, differently sized, map.
        doc['material']['back'] = side(basecolor=image_node('textures/back.png', (64, 32)))
        extra['textures/back.png'] = image_bytes((64, 32), color=(20, 120, 60))
    if edit:
        edit(doc)
    return fmt.pack(dict({'material.u3m': json.dumps(doc).encode(),
                          'textures/base.png': image_bytes((256, 256)),
                          'textures/normal.png': image_bytes((128, 128)),
                          'preview.jpg': image_bytes((64, 64), 'JPEG')}, **extra, **(files or {})))


def decoded(data_url):
    from base64 import b64decode
    return Image.open(BytesIO(b64decode(data_url.split(',', 1)[1]))).convert('RGB')


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

    def test_published_cotton_quality_flags_prevent_bending_estimates(self):
        raw = shirley_package()
        content = fmt.import_fabric(raw, 'shirley.u3ma')
        props = content['properties']
        self.assertEqual(props['weight']['value'], 300)
        self.assertEqual(props['weight']['origin'], 'measured')
        self.assertAlmostEqual(props['thickness']['value'], .20203900337219238)
        self.assertAlmostEqual(props['stretch_warp']['value'], 72.36051177978516)
        self.assertAlmostEqual(props['stretch_weft']['value'], 51.73408508300781)
        self.assertEqual(len(content['curves']), 102)
        self.assertEqual(content['physics_normalization']['bending_fits'], {})
        for axis in ('warp', 'weft'):
            self.assertIsNone(props['bend_'+axis]['value'])
            self.assertIn('low-force', props['bend_'+axis]['source'])
        exported = fmt.export_fabric(dict(id=str(uuid4()), name='Cotton copy', content=content), raw, 'shirley.u3ma')
        self.assertEqual(fmt.read_package(exported, 'copy.u3ma')[0]['physics.json'],
                         (fmt.SPEC/'shirley_physics.json').read_bytes())
        self.assertEqual(fmt.import_fabric(exported, 'copy.u3ma')['properties'], props)

    def test_old_export_retires_flagged_estimates_but_preserves_user_values(self):
        files, manifest, doc, _ = fmt.read_package(shirley_package(), 'shirley.u3ma')
        values = fmt.import_fabric(shirley_package(), 'shirley.u3ma')['properties']
        values['bend_warp'].update(value=1.72e-5, origin='estimated',
            source='FAB raw_data.L U1/D1 loading cycles; short-loop elastica fit v1')
        values['bend_weft'].update(value=3e-5, origin='user', source=None)
        doc['custom'] = {'seweasy': {'schema': 1, 'properties': values}}
        files[manifest] = json.dumps(doc).encode()
        content = fmt.import_fabric(fmt.pack(files), 'old-copy.u3ma')
        self.assertIsNone(content['properties']['bend_warp']['value'])
        self.assertEqual(content['properties']['bend_weft'], values['bend_weft'])

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


class TextureImportTest(unittest.TestCase):
    """Appearance-only materials: resolved, measured against their declared scale, never altered."""

    def test_appearance_only_material_records_textures_and_importer(self):
        raw = appearance_package()
        content = fmt.import_fabric(raw, 'lawn.u3ma')
        self.assertTrue(all(p['value'] is None for p in content['properties'].values()))
        self.assertEqual(content['source']['importer'], fmt.IMPORTER)
        self.assertEqual(content['source']['filename'], 'lawn.u3ma')
        self.assertFalse(content['source']['has_raw_measurements'])
        textures = {t['role']: t for t in content['textures']}
        self.assertEqual(set(textures), {'front.basecolor.texture.image',
                                         'front.normal.texture.image', 'front.preview'})
        base = textures['front.basecolor.texture.image']
        self.assertEqual((base['format'], base['pixels'], base['dpi']), ('PNG', [256, 256], [300, 300]))
        self.assertAlmostEqual(base['size_mm'][0], 256/300*25.4)
        self.assertEqual(textures['front.normal.texture.image']['pixels'], [128, 128])
        self.assertEqual(textures['front.preview']['format'], 'JPEG')
        self.assertTrue(all(t['warning'] is None for t in content['textures']))
        # Round trips keep the texture bytes byte-for-byte, not re-encoded.
        exported = fmt.export_fabric(dict(id=str(uuid4()), name='Lawn', content=content), raw, 'lawn.u3ma')
        self.assertEqual(fmt.read_package(exported, 'lawn.u3ma')[0]['textures/base.png'],
                         fmt.read_package(raw, 'lawn.u3ma')[0]['textures/base.png'])
        self.assertEqual(fmt.import_fabric(exported, 'lawn.u3ma')['textures'], content['textures'])

    def test_mismatched_and_missing_texture_scale_is_reported_not_corrected(self):
        content = fmt.import_fabric(appearance_package(scale=2.), 'lawn.u3ma')
        base = next(t for t in content['textures'] if t['role'].startswith('front.basecolor'))
        self.assertIn('256×256 px', base['warning'])
        self.assertIn('512×512 px', base['warning'])
        # The declared size stays as the vendor wrote it; only the reader complains.
        self.assertAlmostEqual(base['size_mm'][0], 2*256/300*25.4)
        self.assertIsNone(next(t for t in content['textures'] if t['role'] == 'front.preview')['warning'])
        files, manifest, doc, _ = fmt.read_package(appearance_package(), 'lawn.u3ma')
        doc['material']['front']['basecolor']['texture']['image']['dpi'] = dict(x=0, y=300)
        files[manifest] = json.dumps(doc).encode()
        content = fmt.import_fabric(fmt.pack(files), 'lawn.u3ma')
        self.assertIn('physical size', next(t for t in content['textures']
                                            if t['role'].startswith('front.basecolor'))['warning'])

    def test_rejects_unreadable_unsupported_oversized_and_missing_textures(self):
        cases = {'not a readable image': b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                 'Convert it to PNG': image_bytes((32, 32), 'GIF')}
        for message, data in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                fmt.import_fabric(appearance_package(files={'textures/base.png': data}), 'lawn.u3ma')
        with patch.object(fmt, 'MAX_TEXTURE_SIDE', 64), self.assertRaisesRegex(ValueError, '256×256 px'):
            fmt.import_fabric(appearance_package(), 'lawn.u3ma')
        files, _, _, _ = fmt.read_package(appearance_package(), 'lawn.u3ma')
        del files['textures/normal.png']
        with self.assertRaisesRegex(ValueError, 'Missing companion file: textures/normal.png'):
            fmt.import_fabric(fmt.pack(files), 'lawn.u3ma')

    def test_base_colour_maps_are_render_ready_at_their_declared_size(self):
        content = fmt.import_fabric(appearance_package(back=True), 'lawn.u3ma')
        maps = content['texture_maps']
        self.assertEqual(set(maps), {'front', 'back'})                  # never the normal map or the preview
        self.assertAlmostEqual(maps['front']['size_mm'][0], 256/300*25.4)
        self.assertEqual(maps['back']['pixels'], [64, 32])
        self.assertAlmostEqual(maps['back']['size_mm'][1], 32/300*25.4)
        for side_map in maps.values():
            self.assertTrue(side_map['image'].startswith('data:image/webp;base64,'))
            self.assertLessEqual(len(side_map['image']), fmt.TEXTURE_MAP_BYTES * 4 // 3 + 64)
            self.assertLessEqual(max(decoded(side_map['image']).size), fmt.TEXTURE_MAP_PX)
        red, green, blue = decoded(maps['back']['image']).getpixel((5, 5))
        self.assertTrue(abs(red - 20) < 12 and abs(green - 120) < 12 and abs(blue - 60) < 12)
        # A large scan is reduced for the garment's copy; the stored original is not.
        big = fmt.import_fabric(appearance_package(files={'textures/base.png': image_bytes((1400, 700))},
                                                   edit=lambda d: d['material']['front']['basecolor']['texture']['image']
                                                   .update(width=1400/300*25.4, height=700/300*25.4)), 'big.u3ma')
        self.assertEqual(big['texture_maps']['front']['pixels'], [512, 256])
        self.assertAlmostEqual(big['texture_maps']['front']['size_mm'][0], 1400/300*25.4)
        # The U3M multiply factor tints the map.
        tinted = fmt.import_fabric(appearance_package(edit=lambda d: d['material']['front']['basecolor']['texture']
                                                      .update(factor=dict(r=1, g=.5, b=0))), 'tint.u3ma')
        red, green, blue = decoded(tinted['texture_maps']['front']['image']).getpixel((9, 9))
        self.assertTrue(abs(red - 190) < 12 and abs(green - 85) < 12 and blue < 12)

    def test_a_map_that_cannot_be_drawn_is_still_imported_and_stored(self):
        unsized = fmt.import_fabric(appearance_package(edit=lambda d: d['material']['front']['basecolor']['texture']['image']
                                                       .update(width=0)), 'unsized.u3ma')
        self.assertEqual(unsized['texture_maps'], {})                   # no physical size to draw it at
        self.assertEqual(len(unsized['textures']), 3)
        with patch.object(fmt, 'TEXTURE_MAP_DECODE_PIXELS', 1000):
            huge = fmt.import_fabric(appearance_package(), 'huge.u3ma')
        self.assertEqual(huge['texture_maps'], {})
        self.assertEqual(fmt.import_fabric(fmt.sample_package(), 'cupro.u3ma')['texture_maps'], {})

    def test_published_vendor_1_0_material_is_refused_with_an_upgrade_message(self):
        raw = (fmt.SPEC/'vendor_example_1.0.u3m').read_bytes()
        self.assertEqual(json.loads(raw)['schema'], '1.0')
        for name, package in (('example.u3m', raw), ('example.u3ma', fmt.pack({'example.u3m': raw}))):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'U3M 1.0 material') as caught:
                fmt.import_fabric(package, name)
            self.assertIn('Re-export the material as 1.1', str(caught.exception))


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

    def test_an_override_keeps_the_imported_measurement_restorable_with_its_provenance(self):
        measured = deepcopy(self.record['content']['properties']['weight'])
        changed = self.save(values={'weight': '80', 'friction': ''})
        self.assertEqual(changed['content']['properties']['weight']['origin'], 'user')
        imported = fabrics.imported_properties(self.alice, self.record['id'])
        self.assertEqual(imported['weight'], measured)
        self.assertEqual(imported['friction']['value'], .2)       # a cleared field is still in the file
        restored = fabrics.update_fabric(self.alice, changed['id'], changed['edit_token'], name=changed['name'],
                                         description='', values={}, restore=['weight', 'friction'])
        self.assertEqual(restored['content']['properties']['weight'], measured)
        self.assertEqual(restored['content']['properties']['friction']['origin'], 'reported')
        # An edit made after restoring wins; it is a new value, not the file's.
        edited = fabrics.update_fabric(self.alice, restored['id'], restored['edit_token'], name=restored['name'],
                                       description='', values={'weight': '90'}, restore=['weight'])
        self.assertEqual(edited['content']['properties']['weight']['origin'], 'user')
        self.assertEqual(fabrics.imported_properties(self.bob, 'standard:canvas'), {})
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            fabrics.imported_properties(self.bob, self.record['id'])
        blank = fabrics.create_fabric(self.alice, 'Hand entered')
        with self.assertRaisesRegex(ValueError, 'no imported measurements'):
            fabrics.update_fabric(self.alice, blank['id'], blank['edit_token'], name='Hand entered',
                                  description='', values={}, restore=['weight'])

    def test_display_color_travels_with_copies_snapshots_and_exports(self):
        saved = fabrics.update_fabric(self.alice, self.record['id'], self.record['edit_token'],
                                      name=self.record['name'], description='', values={}, display_color='#1F3A5F')
        self.assertEqual(saved['content']['appearance']['display_color'], '#1f3a5f')
        self.assertEqual(fabrics.snapshot(self.alice, saved['id'])['display_color'], '#1f3a5f')
        self.assertEqual(fabrics.copy_fabric(self.alice, saved['id'])['content']['appearance']['display_color'], '#1f3a5f')
        exported = fabrics.export_fabric(self.alice, saved['id'])
        self.assertEqual(fmt.import_fabric(exported, 'navy.u3ma')['appearance']['display_color'], '#1f3a5f')
        # None leaves it alone; an empty value clears it everywhere it travelled.
        kept = self.save(saved, name='Navy cupro')
        self.assertEqual(kept['content']['appearance']['display_color'], '#1f3a5f')
        cleared = fabrics.update_fabric(self.alice, kept['id'], kept['edit_token'], name=kept['name'],
                                        description='', values={}, display_color='')
        self.assertNotIn('display_color', cleared['content']['appearance'])
        self.assertNotIn('display_color', fabrics.snapshot(self.alice, cleared['id']))
        self.assertNotIn('display_color', fmt.import_fabric(
            fabrics.export_fabric(self.alice, cleared['id']), 'plain.u3ma')['appearance'])
        with self.assertRaisesRegex(ValueError, 'hex'):
            fabrics.update_fabric(self.alice, cleared['id'], cleared['edit_token'], name=cleared['name'],
                                  description='', values={}, display_color='navy')

    def test_hearts_reference_fabrics_without_copying_and_stay_out_of_the_wardrobe(self):
        from webapp import fabric_favorites as hearts
        from webapp.favorites import Favorites
        from webapp.wardrobe import Wardrobe
        poplin = 'standard:catalog:light-cotton-poplin'
        with patch.object(hearts, 'SessionLocal', fabrics.SessionLocal):
            hearts.set_favorite(self.alice, poplin, True)
            hearts.set_favorite(self.alice, self.record['id'], True)
            hearts.set_favorite(self.alice, self.record['id'], True)       # a second tab
            self.assertEqual(hearts.keys(self.alice), {poplin, self.record['id']})
            # Most recent first, each once; hearting a standard fabric made no copy.
            self.assertEqual([r['id'] for r in hearts.favorites(self.alice)], [self.record['id'], poplin])
            self.assertEqual(len(fabrics.list_fabrics(self.alice)), 1)
            self.assertEqual(hearts.keys(self.bob), set())
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                hearts.set_favorite(self.bob, self.record['id'], True)   # someone else's fabric
            with self.assertRaisesRegex(ValueError, 'Sign in'):
                hearts.set_favorite(None, poplin, True)
            self.assertEqual((hearts.keys(None), hearts.favorites(None)), (set(), []))
            # A heart whose fabric no longer resolves is skipped, not an error.
            from webapp.models import WardrobeFavorite
            with fabrics.SessionLocal() as db:
                db.add(WardrobeFavorite(owner_email=self.alice, kind='fabric', item_id='standard:catalog:retired'))
                db.commit()
            self.assertEqual(len(hearts.favorites(self.alice)), 2)
            hearts.set_favorite(self.alice, 'standard:catalog:retired', False)   # and can still be removed
            self.assertNotIn('standard:catalog:retired', hearts.keys(self.alice))
            # The quick list shows each fabric once, hearts first.
            groups = {}
            for item in fabrics.assignable(self.alice):
                groups.setdefault(item['group'], []).append(item['id'])
            self.assertEqual(groups['Favorites'], [self.record['id'], poplin])
            self.assertNotIn('My fabrics', groups)
            self.assertNotIn(poplin, groups['Common fabrics'])
            self.assertEqual(len(groups['Common fabrics']), 11)
            self.assertEqual({i['group'] for i in fabrics.assignable(None)}, {'Common fabrics'})
        # Garment and outfit favorites neither count nor list fabric hearts.
        import webapp.favorites as wardrobe_favorites
        with patch.object(wardrobe_favorites, 'SessionLocal', fabrics.SessionLocal):
            wardrobe = Favorites(Wardrobe(self.alice, {}))
            self.assertEqual(wardrobe.keys(), set())
            self.assertEqual(wardrobe.list(), [])
            with self.assertRaises(ValueError):
                wardrobe.set('fabric', poplin, True)

    def test_weight_classes_follow_the_apparel_boundaries(self):
        content = deepcopy(self.record['content'])
        for weight, expected in ((None, None), (60, 'light'), (134.9, 'light'), (135, 'medium'),
                                 (270, 'medium'), (270.1, 'heavy'), (400, 'heavy')):
            content['properties']['weight']['value'] = weight
            self.assertEqual(fabrics.weight_class(content), expected)
        self.assertEqual(set(fabrics.WEIGHT_CLASSES), {'light', 'medium', 'heavy'})
        common = fabrics.standard_fabrics()
        names = lambda **filters: {r['name'] for r in common if fabrics.matches(r, **filters)}
        self.assertEqual(names(weight='heavy'), {'Cotton denim', 'Cotton canvas'})
        self.assertEqual(names(query='  KNIT '), {'Cotton jersey', 'Stretch jersey'})        # weave text, any case
        self.assertEqual(names(query='cotton', weight='light'), {'Lightweight cotton poplin'})
        self.assertEqual(names(query='velvet'), set())
        # Drape presets have no weight, so a weight filter never claims them.
        self.assertFalse(any(fabrics.matches(r, weight='light') for r in common if r['id'] == 'standard:canvas'))
        self.assertTrue(fabrics.matches(self.record, query='cupro'))

    def test_export_as_a_folder_and_notes_on_what_other_applications_will_not_read(self):
        edited = self.save(values={'weight': '80', 'friction': ''})
        archive = fabrics.export_fabric(self.alice, edited['id'])
        folder = fabrics.export_fabric(self.alice, edited['id'], bundle=True)
        packed, unpacked = fmt.read_package(archive, 'a.u3ma')[0], fmt.read_package(folder, 'a.zip')[0]
        # The same files either way; only the container differs.
        self.assertEqual({k: v for k, v in packed.items() if k != 'material.u3m'},
                         {k: v for k, v in unpacked.items() if k != 'material.u3m'})
        with ZipFile(BytesIO(folder)) as plain:
            self.assertTrue(all(entry.flag_bits & 0x800 == 0 for entry in plain.infolist()))   # an ordinary ZIP
        self.assertEqual(fmt.import_fabric(folder, 'a.zip')['properties'], edited['content']['properties'])
        self.assertEqual(unpacked['physics.json'], (fmt.SPEC/'cupro_physics.json').read_bytes())
        notes = unpacked[fmt.NOTES_PATH].decode()
        native, extension = notes.split('Written only to the custom.seweasy extension')
        self.assertIn('weight = 80 g/m2 (user)', native)
        self.assertIn('stretch_warp = ', extension)
        self.assertNotIn('stretch_warp', native)
        self.assertRegex(notes, r'left empty rather than zero: .*friction')
        self.assertIn('remain the original laboratory data', notes)
        # Nothing about the account or the library travels with a fabric.
        for data in unpacked.values():
            for private in (self.alice.encode(), edited['edit_token'].encode(), b'alice'):
                self.assertNotIn(private, data)
        # Importing our own export and exporting again replaces the notes; a vendor's file of that name is kept.
        again = fabrics.import_fabric(self.alice, folder, 'round.zip', name='Round trip')
        twice = fmt.read_package(fabrics.export_fabric(self.alice, again['id']), 'b.u3ma')[0]
        self.assertEqual([k for k in twice if 'export-notes' in k], [fmt.NOTES_PATH])
        vendor = dict(packed, **{fmt.NOTES_PATH: b'Vendor release notes'})
        kept = fabrics.import_fabric(self.alice, fmt.pack(vendor), 'vendor.u3ma', name='Vendor notes')
        result = fmt.read_package(fabrics.export_fabric(self.alice, kept['id']), 'c.u3ma')[0]
        self.assertEqual(result[fmt.NOTES_PATH], b'Vendor release notes')
        self.assertTrue(result['seweasy-export-notes-2.txt'].startswith(fmt.NOTES_HEADING.encode()))

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

    def test_normalizer_upgrade_retires_flagged_fits_without_overwriting_edits(self):
        from webapp.models import Fabric
        from webapp.fabric_measurements import VERSION
        record = fabrics.import_fabric(self.alice, shirley_package(), 'shirley.u3ma')
        for weft_value, origin in ((3e-5, 'user'), (None, 'unknown')):
            with self.subTest(origin=origin):
                with fabrics.SessionLocal() as db:
                    row = db.get(Fabric, record['id'])
                    content = deepcopy(row.content)
                    content['physics_normalization'] = {'version': 1, 'bending_fits': {}}
                    content['properties']['bend_warp'].update(value=1.72e-5, origin='estimated',
                        source='FAB raw_data.L U1/D1 loading cycles; short-loop elastica fit v1')
                    content['properties']['bend_weft'].update(value=weft_value, origin=origin, source=None)
                    row.content = content
                    db.commit()
                derived = fabrics.get_fabric(self.alice, record['id'])
                self.assertEqual(derived['content']['physics_normalization']['version'], VERSION)
                self.assertIsNone(derived['content']['properties']['bend_warp']['value'])
                self.assertEqual(derived['content']['properties']['bend_weft']['value'], weft_value)
                self.assertEqual(derived['content']['properties']['bend_weft']['origin'], origin)
                # Detail reads are not writes; only save persists the new normalization.
                with fabrics.SessionLocal() as db:
                    self.assertEqual(db.get(Fabric, record['id']).content['physics_normalization']['version'], 1)
                saved = self.save(derived)
                self.assertEqual(saved['content'], fabrics.get_fabric(self.alice, record['id'])['content'])


    def test_records_read_by_an_older_importer_gain_texture_details_without_lockout(self):
        from webapp.models import Fabric
        record = fabrics.import_fabric(self.alice, appearance_package(), 'lawn.u3ma')
        with fabrics.SessionLocal() as db:
            row = db.get(Fabric, record['id'])
            content = deepcopy(row.content)
            content.pop('textures')
            content['source']['importer'] = 'seweasy-u3m/1'
            row.content = content
            db.commit()
        derived = fabrics.get_fabric(self.alice, record['id'])
        self.assertEqual(derived['content']['source']['importer'], fmt.IMPORTER)
        self.assertEqual(len(derived['content']['textures']), 3)
        # A reader that grew stricter must not hide a fabric its owner already saved.
        with patch.object(fmt, 'MAX_TEXTURE_SIDE', 64):
            stored = fabrics.get_fabric(self.alice, record['id'])
        self.assertEqual(stored['content']['source']['importer'], 'seweasy-u3m/1')
        self.assertNotIn('textures', stored['content'])


class MeasurementFitTest(unittest.TestCase):
    def test_quality_flags_only_block_the_affected_direction_and_keep_curves(self):
        from webapp.fabric_measurements import normalize
        fab = json.loads((fmt.SPEC/'cupro_physics.json').read_text())
        fab['raw_data']['warnings'] = {'BendRigidityWarp': 'low-force', 'FutureVendorTest': 'unknown-code'}
        before = deepcopy(fab)
        values, curves, metadata = normalize(fab)
        self.assertIsNone(values['bend_warp']['value'])
        self.assertAlmostEqual(values['bend_weft']['value'], 1.60237475888735e-5)
        self.assertEqual(len(curves), 102)
        self.assertEqual(metadata['raw_warnings'], fab['raw_data']['warnings'])
        self.assertEqual(metadata['warnings'][0]['source'], 'FAB raw_data.warnings.BendRigidityWarp')
        self.assertEqual(fab, before)

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
