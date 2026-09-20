"""Where a fabric can be bought: links the owner attaches, never a claim about how it drapes.

A listing sharing a fabric's name or fibre says nothing about its measured
properties, so every source states how it relates to them. Nothing here fetches
a page, reads a price, or carries anyone's affiliate tag.
"""
from datetime import datetime, timezone
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

MAX_SOURCES = 12
STALE_DAYS = 30
UNITS = {'yard': 'per yard', 'meter': 'per metre', 'precut': 'per precut piece', 'pack': 'per pack', 'other': 'each'}
AVAILABILITY = {'in_stock': 'In stock', 'out_of_stock': 'Out of stock', 'unknown': ''}
# How a listing relates to the properties above it. Only "exact" says they came from this product.
MATCHES = {
    'exact': ('Measured product', 'The measurements above were taken from this product.'),
    'unverified': ('Unverified link', 'Not checked against the measurements above. It may drape differently.'),
    'similar': ('Similar fabric', 'A suggestion of similar cloth, not the measured one. It may drape differently.'),
}
TEXT = dict(retailer=80, product_id=80, variant=120, composition=200, construction=200, unit_detail=80, private_note=1000)
PRIVATE = ('private_note',)
FIELDS = {'id', 'url', 'match', 'unit', 'availability', 'weight_gsm', 'width_cm', 'price', 'currency',
          'checked_at', *TEXT}
# Campaign and affiliate parameters identify whoever shared a link, not the product.
TRACKING = re.compile(r'(?i)^(utm_.*|gclid|fbclid|msclkid|mc_[ce]id)$')
# Amazon Associates parameters; elsewhere `tag` or `ref` may be what selects the product.
AMAZON_TRACKING = re.compile(r'(?i)^(tag|linkcode|linkid|ascsubtag|ref_?|camp|creative|creativeasin)$')


def retailer_for(url):
    """A readable retailer from the address: Amazon, Michaels, or the site's own name."""
    host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
    if re.fullmatch(r'(smile\.)?amazon\.[a-z.]{2,6}|a\.co|amzn\.(to|com)', host):
        return 'Amazon'
    if host in ('michaels.com', 'canada.michaels.com'):
        return 'Michaels'
    return host


def clean_url(value):
    """HTTPS only, no credentials, and without the sharer's tracking parameters."""
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 2000 or any(ord(c) < 33 for c in value.strip()):
        raise ValueError('Paste the product page address, starting with https://.')
    try:
        parts = urlsplit(value.strip())
        valid = parts.scheme == 'https' and bool(parts.hostname) and '.' in parts.hostname and not parts.username
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Paste the product page address, starting with https://.')
    amazon = retailer_for(value.strip()) == 'Amazon'
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not TRACKING.match(k) and not (amazon and AMAZON_TRACKING.match(k))])
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, query, ''))


def _number(value, label):
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValueError(f'{label} needs a number, or leave it blank.')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} needs a number, or leave it blank.') from None
    if not math.isfinite(result) or not 0 < result <= 1e7:
        raise ValueError(f'{label} needs a positive number, or leave it blank.')
    return result


def _checked(value):
    """When the owner last looked at the listing. A price without one is dated now."""
    if value in (None, ''):
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Use a date such as 2026-09-20 for when you checked the listing.') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if (moment - datetime.now(timezone.utc)).total_seconds() > 86400:        # a day's grace for time zones
        raise ValueError('The checked date cannot be in the future.')
    return moment.astimezone(timezone.utc).isoformat()


def validate(sources, now=None, stamp=True):
    """Normalise a fabric's sources. Only the address is required; unknown stays blank, never guessed.

    A price or availability the owner enters is dated now unless they say when
    they checked it. `stamp=False` is for data nobody here looked at.
    """
    if sources in (None, ''):
        return []
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise ValueError(f'A fabric can list up to {MAX_SOURCES} places to buy it.')
    result, seen = [], set()
    for source in sources:
        if not isinstance(source, dict) or set(source) - FIELDS:
            raise ValueError('Unknown field in a place to buy.')
        item = dict(id=str(source.get('id') or uuid4()), url=clean_url(source.get('url')))
        if item['id'] in seen or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', item['id']):
            raise ValueError('Each place to buy needs its own id.')
        seen.add(item['id'])
        for key, limit in TEXT.items():
            text = source.get(key) or ''
            if not isinstance(text, str) or len(text) > limit or any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError(f'Keep {key.replace("_", " ")} under {limit} characters.')
            item[key] = text.strip()
        item['retailer'] = item['retailer'] or retailer_for(item['url'])
        for key, allowed, default in (('match', MATCHES, 'unverified'), ('unit', UNITS, 'yard'),
                                      ('availability', AVAILABILITY, 'unknown')):
            item[key] = source.get(key) or default
            if not isinstance(item[key], str) or item[key] not in allowed:
                raise ValueError(f'Unknown {key}.')
        item['weight_gsm'] = _number(source.get('weight_gsm'), 'Weight')
        item['width_cm'] = _number(source.get('width_cm'), 'Usable width')
        item['price'] = _number(source.get('price'), 'Price')
        item['currency'] = str(source.get('currency') or '').strip().upper()
        if item['price'] is not None and not re.fullmatch(r'[A-Z]{3}', item['currency']):
            raise ValueError('Give the price a three-letter currency, such as USD.')
        if item['price'] is None:
            item['currency'] = ''
        item['checked_at'] = _checked(source.get('checked_at'))
        if stamp and item['checked_at'] is None and (item['price'] is not None or item['availability'] != 'unknown'):
            item['checked_at'] = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
        result.append(item)
    return result


def public(sources):
    """What may leave the account with an export: everything but the owner's private notes."""
    return [{key: value for key, value in source.items() if key not in PRIVATE} for source in sources or []]


def from_file(sources):
    """A file is untrusted and may come from a newer SewEasy: keep each source that validates, drop the rest."""
    kept = {}
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        try:
            item = validate([{k: v for k, v in source.items() if k in FIELDS and k not in PRIVATE}], stamp=False)[0]
        except ValueError:
            continue
        kept.setdefault(item['id'], item)
    return list(kept.values())[:MAX_SOURCES]


def describe(source, now=None):
    """The lines the library shows for one source. A price is always tied to its unit, variant and date."""
    now = now or datetime.now(timezone.utc)
    label, caution = MATCHES[source['match']]
    price = ''
    if source.get('price') is not None:
        unit = source.get('unit_detail') and f'per {source["unit_detail"]}' or UNITS[source['unit']]
        price = f'{source["price"]:,.2f} {source["currency"]} {unit}'
    checked, stale = '', False
    if source.get('checked_at'):
        moment = datetime.fromisoformat(source['checked_at'])
        stale = (now - moment).days > STALE_DAYS
        checked = f'Checked {moment.date().isoformat()}'
        if stale and (price or source['availability'] != 'unknown'):
            # An old price is kept, and said to be old, rather than shown as today's.
            checked += ' · may have changed'
    elif price or source['availability'] != 'unknown':
        checked, stale = 'Not dated · may have changed', True
    details = [d for d in (source.get('composition'), source.get('construction'),
                           source.get('weight_gsm') and f'{source["weight_gsm"]:g} g/m²',
                           source.get('width_cm') and f'{source["width_cm"]:g} cm wide') if d]
    return dict(title=' · '.join(filter(None, (source['retailer'], source.get('variant')))),
                match=label, caution=caution, exact=source['match'] == 'exact', price=price,
                availability=AVAILABILITY[source['availability']], checked=checked, stale=stale,
                details=' · '.join(details), product_id=source.get('product_id', ''))
