"""Public sample provenance, isolated copies and useful browser input values."""
from copy import deepcopy
import json
import math
import unittest
from uuid import uuid4

from webapp import fabric_catalog as catalog, fabric_formats as fmt, fabrics
import test_fabrics as fixtures


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.records = {r['content']['catalog']['id']: r for r in catalog.standard_fabrics()}

    def test_public_units_and_provenance_are_not_solver_guesses(self):
        cotton = self.records['cotton-twill']['content']
        self.assertEqual(cotton['properties']['weight']['origin'], 'reported')
        self.assertEqual(cotton['properties']['weight']['value'], 184)
        self.assertAlmostEqual(cotton['properties']['bend_warp']['value'], 23.33 * 1e-6)
        self.assertAlmostEqual(cotton['properties']['bend_weft']['value'], 4.3 * 1e-6)
        self.assertEqual(cotton['properties']['bend_warp']['origin'], 'measured')
        self.assertEqual(cotton['curves'], [])
        linen = self.records['linen-plain']['content']
        self.assertEqual(linen['properties']['weight']['value'], 199.7)
        self.assertEqual(linen['properties']['thickness']['value'], .51)
        self.assertEqual(linen['properties']['bend_warp']['origin'], 'estimated')
        self.assertNotIn('Vasile', linen['properties']['bend_warp']['source'])
        twill = self.records['stretch-twill']['content']['properties']
        self.assertAlmostEqual(twill['bend_warp']['value'], .356 * 1e-4)
        self.assertAlmostEqual(twill['bend_weft']['value'], .093 * 1e-4)
        self.assertEqual(twill['stretch_warp']['origin'], 'estimated')

    def test_collection_is_offline_repeatable_and_returns_detached_templates(self):
        first = catalog.standard_fabrics()
        self.assertEqual(first, catalog.standard_fabrics())
        self.assertEqual(len(first), 12)
        first[0]['content']['properties']['weight']['value'] = 999
        first[0]['content']['catalog']['notes'] = 'changed'
        self.assertNotEqual(first, catalog.standard_fabrics())
        self.assertTrue(all(r['standard'] and not r['has_source'] for r in first))

    def test_estimates_and_missing_fields_are_honest(self):
        for key, r in self.records.items():
            with self.subTest(fabric=key):
                props = r['content']['properties']
                fmt.validate_properties(props)
                for name in ('friction', 'damping'):
                    self.assertIsNone(props[name]['value'])
                    self.assertEqual(props[name]['origin'], 'unknown')
                if not r['content']['catalog']['references']:
                    self.assertTrue(all(p['origin'] in ('unknown', 'estimated') for p in props.values()))
                    self.assertEqual(catalog.evidence_label(r['content']), 'Estimated preset')
                else:
                    self.assertEqual(catalog.evidence_label(r['content']), 'Measurements + estimates')
                    self.assertTrue(all(ref['license'] == 'CC BY 4.0'
                                        for ref in r['content']['catalog']['references']))

    def test_all_catalog_records_roundtrip_with_licenses_and_credits(self):
        for r in self.records.values():
            with self.subTest(fabric=r['name']):
                raw = fmt.export_fabric(r)
                imported = fmt.import_fabric(raw, 'fabric.u3ma')
                self.assertEqual(imported['properties'], r['content']['properties'])
                self.assertEqual(imported['catalog'], r['content']['catalog'])
                files, _, _, _ = fmt.read_package(raw, 'fabric.u3ma')
                credits = files['seweasy-fabric-sources.txt'].decode('utf-8')
                for ref in imported['catalog']['references']:
                    self.assertIn(ref['authors'], credits)
                    self.assertIn(ref['url'], credits)
                    self.assertIn(ref['license'], credits)
                # Re-export preserves every companion byte, and doesn't add duplicates.
                exported = fmt.export_fabric(dict(id=str(uuid4()), name=r['name'], content=imported), raw, 'fabric.u3ma')
                self.assertEqual(fmt.read_package(exported, 'fabric.u3ma')[0]['seweasy-fabric-sources.txt'],
                                 files['seweasy-fabric-sources.txt'])

    def test_every_template_has_its_own_representative_display_color(self):
        import re
        formats = fmt
        records = catalog.standard_fabrics()
        shades = [r['content']['appearance'].get('display_color') for r in records]
        self.assertTrue(all(re.fullmatch(r'#[0-9a-f]{6}', shade or '') for shade in shades))
        self.assertEqual(len(set(shades)), len(records))          # twelve tiles that can be told apart
        denim = next(r for r in records if r['id'] == 'standard:catalog:cotton-denim')
        self.assertEqual(denim['content']['appearance']['display_color'], '#2f4468')
        # It is presentation: no property claims it, and it rides with copies, garments and exports.
        self.assertTrue(all('color' not in (p.get('source') or '') for p in denim['content']['properties'].values()))
        self.assertEqual(fabrics.library_snapshot(None, denim['id'])['display_color'], '#2f4468')
        exported = formats.export_fabric(denim)
        self.assertEqual(formats.import_fabric(exported, 'denim.u3ma')['appearance']['display_color'], '#2f4468')
        self.assertIn(b'display colour = #2f4468', formats.read_package(exported, 'denim.u3ma')[0][formats.NOTES_PATH])

    def test_catalog_metadata_cannot_inject_active_links(self):
        for link in ('javascript:alert(1)', 'data:text/html,test', 'file:///test', 'https://[',
                     'https://user:pass@example.test/', 'https://example.test/\nscript'):
            r = deepcopy(self.records['cotton-twill'])
            raw = fmt.export_fabric(r)
            files, manifest, document, _ = fmt.read_package(raw, 'fabric.u3ma')
            document['custom']['seweasy']['catalog']['references'][0]['url'] = link
            files[manifest] = json.dumps(document).encode()
            with self.subTest(link=link), self.assertRaises(ValueError):
                fmt.import_fabric(fmt.pack(files), 'unsafe.u3ma')

    def test_credits_never_replace_an_imported_companion(self):
        r = self.records['cotton-twill']
        raw = fmt.export_fabric(r)
        files, _, _, _ = fmt.read_package(raw, 'fabric.u3ma')
        files.pop('seweasy-fabric-sources.txt')
        files['SewEasy-Fabric-Sources.txt'] = b'vendor-owned original content'
        raw = fmt.pack(files)
        imported = fmt.import_fabric(raw, 'fabric.u3ma')
        result = fmt.export_fabric(dict(id=str(uuid4()), name='Copy', content=imported), raw, 'fabric.u3ma')
        saved = fmt.read_package(result, 'fabric.u3ma')[0]
        self.assertEqual(saved['SewEasy-Fabric-Sources.txt'], files['SewEasy-Fabric-Sources.txt'])
        self.assertIn('Akter', saved['seweasy-fabric-sources-2.txt'].decode())

    def test_every_material_builds_finite_distinct_swatch_inputs(self):
        from webapp.fabric_preview import scene_for
        signatures = set()
        for r in self.records.values():
            warp = scene_for('sample@example.test', r['id'], 'warp')
            weft = scene_for('sample@example.test', r['id'], 'weft')
            self.assertTrue(all(math.isfinite(h['compliance']) and h['compliance'] > 0
                                for h in warp['interior_hinges']))
            self.assertAlmostEqual(sum(warp['vertex_mass_kg']),
                                   .09 * .04 * r['content']['properties']['weight']['value'] / 1000)
            self.assertNotEqual(warp['interior_hinges'], weft['interior_hinges'])
            signatures.add(tuple(p['value'] for p in r['content']['properties'].values()))
        self.assertEqual(len(signatures), len(self.records))


class CatalogStorageTest(unittest.TestCase):
    # Reuse the isolated database fixture without repeating the base test suite.
    setUp = fixtures.FabricStorageTest.setUp
    save = fixtures.FabricStorageTest.save

    def test_named_copy_keeps_attribution_and_detaches_from_standard(self):
        record = next(r for r in catalog.standard_fabrics() if r['content']['catalog']['id'] == 'linen-plain')
        copied = fabrics.copy_fabric(self.alice, record['id'], 'My summer linen')
        with self.assertRaisesRegex(ValueError, 'Save a copy'):
            self.save(record, values={'weight': 200})
        self.save(copied, values={'weight': 210})
        reopened = fabrics.get_fabric(self.alice, copied['id'])
        self.assertEqual(reopened['content']['properties']['weight']['origin'], 'user')
        self.assertEqual(reopened['content']['catalog'], record['content']['catalog'])
        self.assertEqual(fabrics.get_fabric(self.alice, record['id'])['content']['properties']['weight']['value'], 199.7)
        imported = fmt.import_fabric(fabrics.export_fabric(self.alice, copied['id']), 'linen.u3ma')
        self.assertEqual(imported['catalog'], record['content']['catalog'])
        self.assertEqual(imported['properties'], reopened['content']['properties'])


if __name__ == '__main__':
    unittest.main()
