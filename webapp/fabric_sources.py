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
# Campaign parameters and affiliate-network click ids identify whoever shared a link, not the product.
TRACKING = re.compile(r'(?i)^(utm_.*|gclid|gbraid|wbraid|dclid|fbclid|msclkid|ttclid|epik|mc_[ce]id|irclickid|irgwc'
                      r'|sscid|awc|cjevent|cjdata|ranmid|raneaid|ransiteid)$')
# A retailer's own affiliate and click parameters, removed only on its site: elsewhere
# `tag`, `ref` or `hash` may be what selects the product.
RETAILER_TRACKING = {name: re.compile(f'(?i)^({keys})$') for name, keys in {
    'Amazon': r'tag|linkcode|linkid|ascsubtag|ref_?|camp|creative|creativeasin',
    'eBay': r'mkcid|mkrid|mkevt|campid|toolid|customid|_trkparms|_trksid|hash|amdata|itmmeta|itmprp',
    'Etsy': r'ref|click_key|click_sum',
    'Walmart': r'wmlspartner|affiliates_ad_id|campaign_id|sourceid|veh|ath[a-z]*',
}.items()}

# Retailers named from a product link's host, so the owner need not type one. A subdomain
# belongs to its parent (m.ebay.com, canada.michaels.com). JOANN and Fabric.com closed and
# their addresses now forward to Michaels and Amazon, so neither is listed.
RETAILERS = {
    # Marketplaces and craft chains
    'Amazon': ('a.co', 'amzn.to', 'amzn.com'),
    'eBay': ('ebay.us',),
    'Etsy': ('etsy.com',),
    'Michaels': ('michaels.com',),
    'Hobby Lobby': ('hobbylobby.com',),
    'Walmart': ('walmart.com', 'walmart.ca'),
    # United States
    'Mood Fabrics': ('moodfabrics.com',),
    'Fabric Wholesale Direct': ('fabricwholesaledirect.com',),
    'OnlineFabricStore': ('onlinefabricstore.com',),
    'Spoonflower': ('spoonflower.com',),
    'Fashion Fabrics Club': ('fashionfabricsclub.com',),
    'Fabric Mart': ('fabricmartfabrics.com',),
    'Denver Fabrics': ('denverfabrics.com',),
    'Vogue Fabrics': ('voguefabricsstore.com',),
    'Fabric Guru': ('fabricguru.com',),
    'Stylish Fabric': ('stylishfabric.com',),
    'Big Z Fabric': ('bigzfabric.com',),
    'Cali Fabrics': ('califabrics.com',),
    'LA Finch Fabrics': ('lafinchfabrics.com',),
    'Style Maker Fabrics': ('stylemakerfabrics.com',),
    'Stonemountain & Daughter': ('stonemountainfabric.com',),
    'Harts Fabric': ('hartsfabric.com',),
    'Britex Fabrics': ('britexfabrics.com',),
    'B&J Fabrics': ('bandjfabrics.com',),
    'Emma One Sock': ('emmaonesock.com',),
    'Fabrics-store.com': ('fabrics-store.com',),
    'Girl Charlee': ('girlcharlee.com',),
    'Surge Fabric Shop': ('surgefabricshop.com',),
    "Nature's Fabrics": ('naturesfabrics.com',),
    'Organic Cotton Plus': ('organiccottonplus.com',),
    'Dharma Trading': ('dharmatrading.com',),
    'Hawthorne Supply Co': ('hawthornesupplyco.com',),
    'Fat Quarter Shop': ('fatquartershop.com',),
    'Missouri Star Quilt Co': ('missouriquiltco.com',),
    'Connecting Threads': ('connectingthreads.com',),
    'Shabby Fabrics': ('shabbyfabrics.com',),
    'WAWAK': ('wawak.com',),
    'Sailrite': ('sailrite.com',),
    'Ripstop by the Roll': ('ripstopbytheroll.com',),
    'Rockywoods': ('rockywoods.com',),
    'Seattle Fabrics': ('seattlefabrics.com',),
    # Canada
    'Fabricville': ('fabricville.com',),
    'Fabricland': ('fabricland.ca', 'fabriclandwest.com'),
    'Club Tissus': ('clubtissus.com', 'thefabricclub.ca'),      # its English storefront
    "Len's Mill Stores": ('lensmill.com',),
    'Blackbird Fabrics': ('blackbirdfabrics.com',),
    'Core Fabrics': ('corefabricstore.com',),
    # United Kingdom
    'Minerva': ('minerva.com',),
    'Fabric Godmother': ('fabricgodmother.co.uk',),
    'Croft Mill': ('croftmill.co.uk',),
    'Fabworks': ('fabworks.co.uk',),
    'Abakhan': ('abakhan.co.uk',),
    'Hobbycraft': ('hobbycraft.co.uk',),
    'John Lewis': ('johnlewis.com',),
    'Dunelm': ('dunelm.com',),
    'Fabricland UK': ('fabricland.co.uk',),
    'Guthrie & Ghani': ('guthrie-ghani.co.uk',),
    'Empress Mills': ('empressmills.co.uk',),
    'Tissu Fabrics': ('tissufabrics.co.uk',),
    'Dalston Mill Fabrics': ('dalstonmillfabrics.co.uk',),
    'Pound Fabrics': ('poundfabrics.co.uk',),
    'Merchant & Mills': ('merchantandmills.com',),
    # Europe
    'stoffe.de': ('stoffe.de',),
    'myfabrics': ('myfabrics.co.uk',),
    'tissus.net': ('tissus.net',),
    'Selfmade': ('selfmade.com', 'stoffundstil.de'),
    'buttinette': ('buttinette.com',),
    'Rijs Textiles': ('rijstextiles.com',),
    'Mondial Tissus': ('mondialtissus.fr',),
    'Tissus des Ursules': ('tissusdesursules.fr',),
    'Cousette': ('cousette.com',),
    'Lebenskleidung': ('lebenskleidung.com',),
    # Australia and New Zealand
    'Spotlight': ('spotlightstores.com',),
    'Lincraft': ('lincraft.com.au',),
    'The Remnant Warehouse': ('theremnantwarehouse.com.au', 'theremnantwarehouse.com'),
    'Tessuti Fabrics': ('tessuti-shop.com',),
    'The Fabric Store': ('wearethefabricstore.com',),
}
# One site per country: only real storefronts, so amazon.example.net is not called Amazon.
COUNTRY_SITES = {
    'Amazon': re.compile(r'amazon\.(com|ca|co\.uk|de|fr|it|es|nl|se|pl|ie|in|sg|ae|sa|eg|co\.jp|co\.za|com\.(au|be|br|mx|tr))'),
    'eBay': re.compile(r'ebay\.(com|ca|co\.uk|de|fr|it|es|nl|be|at|ch|ie|pl|com\.au)'),
}
RETAILER_NAMES = sorted(RETAILERS, key=str.casefold)
_HOSTS = {host: name for name, hosts in RETAILERS.items() for host in hosts}


def _host(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def retailer_for(url):
    """A readable retailer from the address: a known shop's name, else the site's own host."""
    host = _host(url)
    labels = host.split('.')
    for start in range(len(labels) - 1):
        site = '.'.join(labels[start:])
        if site in _HOSTS:
            return _HOSTS[site]
        for name, pattern in COUNTRY_SITES.items():
            if pattern.fullmatch(site):
                return name
    return host


def retailer_name(source):
    """The owner's own name for the shop; a bare host saved before the shop was listed gains its name."""
    typed = source.get('retailer') or ''
    return retailer_for(source['url']) if typed.lower() in ('', _host(source['url'])) else typed


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
    own = RETAILER_TRACKING.get(retailer_for(value.strip()))
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not TRACKING.match(k) and not (own and own.match(k))])
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
        item['retailer'] = retailer_name(item)
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
            # A file cannot call its link Amazon: the shop is named from the address it really points to.
            item = validate([{k: v for k, v in source.items() if k in FIELDS and k not in (*PRIVATE, 'retailer')}],
                            stamp=False)[0]
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
    return dict(title=' · '.join(filter(None, (retailer_name(source), source.get('variant')))),
                match=label, caution=caution, exact=source['match'] == 'exact', price=price,
                availability=AVAILABILITY[source['availability']], checked=checked, stale=stale,
                details=' · '.join(details), product_id=source.get('product_id', ''))
