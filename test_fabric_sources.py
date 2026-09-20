"""Where-to-buy rules: what a source may claim, and what is shown for it (python -m unittest test_fabric_sources)."""
from datetime import datetime, timedelta, timezone
import unittest

from webapp import fabric_sources as sources

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def one(**fields):
    return sources.validate([dict(url='https://shop.example.com/linen', **fields)], now=NOW)[0]


class SourceRulesTest(unittest.TestCase):
    def test_only_the_address_is_required_and_unknown_stays_blank(self):
        item = one()
        self.assertEqual((item['retailer'], item['match'], item['unit'], item['availability']),
                         ('shop.example.com', 'unverified', 'yard', 'unknown'))
        self.assertTrue(all(item[key] is None for key in ('weight_gsm', 'width_cm', 'price', 'checked_at')))
        shown = sources.describe(item, now=NOW)
        self.assertEqual((shown['price'], shown['availability'], shown['checked'], shown['details']), ('', '', '', ''))
        self.assertEqual(sources.validate(None), [])

    def test_amazon_michaels_and_any_other_retailer_are_named_from_the_address(self):
        for url, retailer in (('https://www.amazon.com/dp/B0ABC', 'Amazon'), ('https://smile.amazon.co.uk/dp/B0ABC', 'Amazon'),
                              ('https://a.co/d/abc', 'Amazon'), ('https://www.michaels.com/product/1', 'Michaels'),
                              ('https://www.moodfabrics.com/linen', 'moodfabrics.com')):
            with self.subTest(url=url):
                self.assertEqual(sources.validate([dict(url=url)])[0]['retailer'], retailer)
        self.assertEqual(one(retailer='The corner shop')['retailer'], 'The corner shop')

    def test_links_are_https_without_credentials_and_lose_the_sharers_tracking(self):
        for bad in ('http://www.amazon.com/dp/B0ABC', 'javascript:alert(1)', 'https://user:pw@shop.example.com/x',
                    'https://localhost/x', 'https://shop.example.com/a b', 'ftp://shop.example.com/x', '', None, 7):
            with self.subTest(url=bad), self.assertRaisesRegex(ValueError, 'https://'):
                sources.clean_url(bad)
        self.assertEqual(sources.clean_url('https://www.Amazon.com/dp/B0ABC?tag=someone-20&th=1&linkCode=ll1&utm_source=x#reviews'),
                         'https://www.amazon.com/dp/B0ABC?th=1')
        # Elsewhere `tag` or `ref` may be what selects the product.
        self.assertEqual(sources.clean_url('https://shop.example.com/p?tag=linen&ref=42&fbclid=abc'),
                         'https://shop.example.com/p?tag=linen&ref=42')

    def test_a_similar_name_never_reads_as_a_measured_match(self):
        for match, exact in (('exact', True), ('unverified', False), ('similar', False)):
            shown = sources.describe(one(match=match), now=NOW)
            self.assertEqual(shown['exact'], exact)
            self.assertEqual('may drape differently' in shown['caution'], not exact)
        self.assertEqual(sources.describe(one(), now=NOW)['match'], 'Unverified link')
        with self.assertRaisesRegex(ValueError, 'match'):
            one(match='identical')

    def test_a_price_states_its_unit_variant_and_date(self):
        for fields, expected in ((dict(unit='yard'), '12.50 USD per yard'), (dict(unit='meter'), '12.50 USD per metre'),
                                 (dict(unit='precut'), '12.50 USD per precut piece'), (dict(unit='pack'), '12.50 USD per pack'),
                                 (dict(unit='precut', unit_detail='2-yard cut'), '12.50 USD per 2-yard cut')):
            with self.subTest(fields=fields):
                shown = sources.describe(one(price='12.5', currency='usd', variant='Navy', **fields), now=NOW)
                self.assertEqual(shown['price'], expected)
                self.assertIn('Navy', shown['title'])
                self.assertEqual(shown['checked'], 'Checked 2026-09-20')
        for fields in (dict(price=3), dict(price=3, currency='dollars'), dict(price=0, currency='USD'),
                       dict(price='cheap', currency='USD'), dict(unit='bolt'), dict(weight_gsm=-1), dict(width_cm=float('nan'))):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                one(**fields)

    def test_an_old_or_undated_quote_is_kept_and_labelled_not_shown_as_current(self):
        old = (NOW - timedelta(days=sources.STALE_DAYS + 1)).date().isoformat()
        stale = sources.describe(one(price=9, currency='EUR', availability='out_of_stock', checked_at=old), now=NOW)
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['checked'], f'Checked {old} · may have changed')
        self.assertEqual((stale['price'], stale['availability']), ('9.00 EUR per yard', 'Out of stock'))
        recent = sources.describe(one(price=9, currency='EUR', checked_at=(NOW - timedelta(days=3)).isoformat()), now=NOW)
        self.assertFalse(recent['stale'])
        self.assertNotIn('may have changed', recent['checked'])
        undated = sources.from_file([dict(url='https://shop.example.com/x', price=9, currency='EUR')])[0]
        self.assertIsNone(undated['checked_at'])
        self.assertEqual(sources.describe(undated, now=NOW)['checked'], 'Not dated · may have changed')
        with self.assertRaisesRegex(ValueError, 'future'):
            one(checked_at='2031-01-01')
        with self.assertRaisesRegex(ValueError, 'date'):
            one(checked_at='last week')

    def test_listing_details_are_shown_as_the_listings_own(self):
        shown = sources.describe(one(composition='100% linen', construction='Plain weave', weight_gsm='185',
                                     width_cm=140, product_id='B0ABC'), now=NOW)
        self.assertEqual(shown['details'], '100% linen · Plain weave · 185 g/m² · 140 cm wide')
        self.assertEqual(shown['product_id'], 'B0ABC')

    def test_limits_unknown_fields_and_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, 'up to 12'):
            sources.validate([dict(url='https://shop.example.com/x')] * (sources.MAX_SOURCES + 1))
        with self.assertRaisesRegex(ValueError, 'Unknown field'):
            one(affiliate='me-20')
        with self.assertRaisesRegex(ValueError, 'own id'):
            sources.validate([dict(id='a', url='https://shop.example.com/x'), dict(id='a', url='https://shop.example.com/y')])
        with self.assertRaisesRegex(ValueError, 'under 80'):
            one(retailer='x' * 81)

    def test_private_notes_never_leave_and_a_file_is_salvaged_not_trusted(self):
        item = one(private_note='Ask Sam for the trade discount')
        self.assertNotIn('private_note', sources.public([item])[0])
        self.assertEqual(item['private_note'], 'Ask Sam for the trade discount')
        kept = sources.from_file([
            dict(url='https://www.amazon.com/dp/B0ABC?tag=someone-20', private_note='smuggled', added_by_a_newer_version=1),
            dict(url='javascript:alert(1)'), 'not a source', dict(id='dup', url='https://shop.example.com/a'),
            dict(id='dup', url='https://shop.example.com/b')])
        self.assertEqual([k['url'] for k in kept], ['https://www.amazon.com/dp/B0ABC', 'https://shop.example.com/a'])
        self.assertEqual(kept[0]['private_note'], '')
        self.assertEqual(sources.from_file('nonsense'), [])


if __name__ == '__main__':
    unittest.main()
