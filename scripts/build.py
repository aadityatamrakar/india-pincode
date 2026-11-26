#!/usr/bin/env python3
"""India Post PIN directory (CSV) -> one small JSON file per PIN code, for a static API.

    python3 scripts/build.py [data/pincode-data.csv.gz] [out-dir]

Writes  <out>/v1/<pin>.json  (e.g. v1/485001.json), plus  v1/states.json  (every state with its districts)
and  v1/meta.json.  The site/ folder (home page) is copied into <out> as is.

Clean-up applied to the raw India Post rows (see README):
- ALL-CAPS names become Title Case ("MADHYA PRADESH" -> "Madhya Pradesh"); mixed-case names are kept.
- Office suffixes (B.O, S.O, H.O, BO, SO, HO ...) are moved into "type"; the name is the place alone.
- Rows with state/district "NA" are filled from the other offices of the same PIN, else from the division.
- A few districts renamed since the data was compiled get their current name (RENAMED below).
- Coordinates that are missing or outside India are dropped.
Only the standard library is used, so it runs anywhere Python 3.9+ runs (GitHub Actions included).
"""
import csv
import gzip
import io
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else 'data/pincode-data.csv.gz')
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else '_site')
SITE = Path(__file__).resolve().parent.parent / 'site'

SMALL = {'and', 'of', 'the', 'in', 'on', 'at', 'by', 'for', 'to', 'de'}
ROMAN = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)$', re.I)
# Short acronyms that stay upper case after title-casing.
KEEP_UPPER = {'nct', 'gpo', 'mdg', 'iit', 'iim', 'aiims', 'bhel', 'ntpc', 'ongc', 'isro', 'crpf', 'bsf', 'cisf', 'itbp',
              'ntr', 'spsr', 'rms', 'rs', 'ps', 'cgo', 'pg', 'nit', 'sail', 'ofk', 'cpwd', 'idpl', 'iti', 'ncl', 'secl', 'mes', 'sbi', 'ii'}

def title(s: str) -> str:
    s = re.sub(r'\s+', ' ', s.strip())
    if not s or s != s.upper():  # mixed case already: trust it
        return s
    words = s.lower().split(' ')
    out = []
    for i, w in enumerate(words):
        if i and w in SMALL:
            out.append(w)
        elif ROMAN.match(w) or w in KEEP_UPPER:
            out.append(w.upper())
        else:
            out.append(re.sub(r"(^|[-(/.'&])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w))
    return ' '.join(out)

STATE_FIX = {  # after title-casing
    'The Dadra and Nagar Haveli and Daman and Diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'Pondicherry': 'Puducherry', 'Chattisgarh': 'Chhattisgarh', 'Orissa': 'Odisha',
}
CIRCLE_STATE = {  # fallback for state "NA" when no other office of the PIN knows it
    'Chattisgarh Circle': 'Chhattisgarh', 'Tamilnadu Circle': 'Tamil Nadu', 'Jammu Kashmir Circle': 'Jammu and Kashmir',
}
# States each postal circle serves. A row whose state is not one of its circle's is a data-entry slip
# (e.g. Agartala offices filed under "Telangana / Nirmal") and is re-filled like "NA". Unknown circles: no check.
CIRCLE_STATES = {
    'Andhra Pradesh Circle': {'Andhra Pradesh', 'Telangana', 'Puducherry'},
    'Telangana Circle': {'Telangana', 'Andhra Pradesh'},
    'Assam Circle': {'Assam', 'Meghalaya'},
    'Bihar Circle': {'Bihar', 'Jharkhand'},
    'Chattisgarh Circle': {'Chhattisgarh'},
    'Delhi Circle': {'Delhi'},
    'Gujarat Circle': {'Gujarat', 'Dadra and Nagar Haveli and Daman and Diu'},
    'Haryana Circle': {'Haryana'},
    'Himachal Pradesh Circle': {'Himachal Pradesh'},
    'Jammu Kashmir Circle': {'Jammu and Kashmir', 'Ladakh'},
    'Jharkhand Circle': {'Jharkhand'},
    'Karnataka Circle': {'Karnataka'},
    'Kerala Circle': {'Kerala', 'Lakshadweep', 'Puducherry'},
    'Madhya Pradesh Circle': {'Madhya Pradesh'},
    'Maharashtra Circle': {'Maharashtra', 'Goa'},
    'North Eastern Circle': {'Arunachal Pradesh', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Tripura'},
    'Odisha Circle': {'Odisha'},
    'Punjab Circle': {'Punjab', 'Chandigarh'},
    'Rajasthan Circle': {'Rajasthan'},
    'Tamilnadu Circle': {'Tamil Nadu', 'Puducherry'},
    'Uttar Pradesh Circle': {'Uttar Pradesh', 'Uttarakhand'},
    'Uttarakhand Circle': {'Uttarakhand'},
    'West Bengal Circle': {'West Bengal', 'Sikkim', 'Andaman and Nicobar Islands'},
}
# Districts renamed after the directory was compiled (state, India Post name) -> current name.
RENAMED = {
    ('Madhya Pradesh', 'Hoshangabad'): 'Narmadapuram',
    ('Madhya Pradesh', 'East Nimar'): 'Khandwa',
    ('Madhya Pradesh', 'West Nimar'): 'Khargone',
    ('Puducherry', 'Pondicherry'): 'Puducherry',
}
SUFFIX = re.compile(r'\s+\(?(h\.?\s?o|s\.?\s?o|b\.?\s?o|g\.?\s?p\.?\s?o|h\.?\s?q|m\.?d\.?g)\.?\)?\.?$', re.I)
TYPE = {'HO': 'HO', 'PO': 'SO', 'SO': 'SO', 'BO': 'BO'}

def coord(lat: str, lng: str):
    try:
        a, b = float(lat), float(lng)
    except ValueError:
        return None
    return (round(a, 5), round(b, 5)) if 6 <= a <= 37.5 and 68 <= b <= 97.5 else None

def read_rows():
    raw = gzip.open(SRC) if SRC.suffix == '.gz' else SRC.open('rb')
    with io.TextIOWrapper(raw, encoding='utf-8', errors='replace', newline='') as fh:
        for r in csv.DictReader(fh):
            yield {k.strip().lower(): (v or '').strip() for k, v in r.items() if k}

def na(s: str) -> bool:
    return not s or s.upper() in ('NA', 'N/A', 'NULL', '-')

def main():
    rows = []
    for r in read_rows():
        pin = r.get('pincode', '')
        if not re.fullmatch(r'[1-9]\d{5}', pin):
            continue
        name = r.get('officename', '')
        typ = TYPE.get(r.get('officetype', '').upper(), r.get('officetype', '').upper() or 'BO')
        rows.append({
            'pin': pin,
            'name': title(SUFFIX.sub('', name)),
            'type': typ,
            'delivery': r.get('delivery', '').lower() == 'delivery',
            'district': None if na(r.get('district', '')) else title(r['district']),
            'state': None if na(r.get('statename', '')) else STATE_FIX.get(title(r['statename']), title(r['statename'])),
            'division': title(re.sub(r'\s+Division$', '', r.get('divisionname', ''), flags=re.I)),
            'region': title(re.sub(r'\s+Region$', '', r.get('regionname', ''), flags=re.I)),
            'circle': title(re.sub(r'\s+Circle$', '', r.get('circlename', ''), flags=re.I)),
            '_circle': r.get('circlename', ''),
            'coord': coord(r.get('latitude', ''), r.get('longitude', '')),
        })

    misfiled = Counter()
    for o in rows:
        ok = CIRCLE_STATES.get(o['_circle'])
        if o['state'] and ok and o['state'] not in ok:
            misfiled[(o['_circle'], o['state'])] += 1
            o['state'] = o['district'] = None
    if misfiled:
        print('misfiled (re-filled):', dict(misfiled))

    # Fill "NA" state/district: same PIN first, then the division's most common value, then the circle.
    by_pin = defaultdict(list)
    for o in rows:
        by_pin[o['pin']].append(o)
    div = defaultdict(Counter)
    for o in rows:
        if o['state'] and o['district']:
            div[(o['_circle'], o['division'])][(o['state'], o['district'])] += 1
    filled = 0
    for offices in by_pin.values():
        known = Counter((o['state'], o['district']) for o in offices if o['state'] and o['district'])
        for o in offices:
            if o['state'] and o['district']:
                continue
            guess = known.most_common(1) or div[(o['_circle'], o['division'])].most_common(1)
            if guess:
                o['state'] = o['state'] or guess[0][0][0]
                o['district'] = o['district'] or guess[0][0][1]
            else:
                o['state'] = o['state'] or CIRCLE_STATE.get(o['_circle'], o['circle'])
            filled += 1
    for o in rows:
        if o['district']:
            o['district'] = RENAMED.get((o['state'], o['district']), o['district'])

    api = OUT / 'v1'
    if OUT.exists():
        shutil.rmtree(OUT)
    api.mkdir(parents=True)
    states = defaultdict(Counter)
    order = {'HO': 0, 'SO': 1, 'BO': 2}
    for pin, offices in sorted(by_pin.items()):
        # The PIN's own district/state: the one most of its head/sub offices are in, else most of all offices.
        main = [o for o in offices if o['type'] in ('HO', 'SO')] or offices
        (state, district), _ = Counter((o['state'], o['district']) for o in main).most_common(1)[0]
        pts = [o['coord'] for o in main if o['coord']] or [o['coord'] for o in offices if o['coord']]
        # Offices often share the PIN's centre point; the most common one is the best single location.
        centre = Counter(pts).most_common(1)[0][0] if pts else None
        offices.sort(key=lambda o: (order.get(o['type'], 3), o['name']))
        seen = set()
        out_offices = []
        for o in offices:
            key = (o['name'], o['type'])
            if key in seen:
                continue
            seen.add(key)
            e = {'name': o['name'], 'type': o['type'], 'delivery': o['delivery']}
            if o['district'] != district or o['state'] != state:
                e['district'] = o['district']
                if o['state'] != state:
                    e['state'] = o['state']
            if o['coord'] and o['coord'] != centre:
                e['lat'], e['lng'] = o['coord']
            out_offices.append(e)
        doc = {'pin': pin, 'state': state, 'district': district, 'division': main[0]['division'],
               'region': main[0]['region'], 'circle': main[0]['circle']}
        if centre:
            doc['lat'], doc['lng'] = centre
        doc['offices'] = out_offices
        (api / f'{pin}.json').write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        states[state][district] += 1

    states_doc = [{'state': s, 'pins': sum(d.values()),
                   'districts': [{'district': k, 'pins': v} for k, v in sorted(d.items())]}
                  for s, d in sorted(states.items())]
    (api / 'states.json').write_text(json.dumps(states_doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    meta = {'pins': len(by_pin), 'offices': len(rows), 'states': len(states),
            'districts': sum(len(d) for d in states.values()), 'built': date.today().isoformat(),
            'source': 'India Post - All India Pincode Directory, data.gov.in (Government Open Data License - India)'}
    (api / 'meta.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    if SITE.exists():
        for f in SITE.iterdir():
            (shutil.copytree if f.is_dir() else shutil.copy2)(f, OUT / f.name)
    (OUT / '.nojekyll').write_text('')
    print(f"{meta['pins']} PINs, {meta['offices']} offices, {meta['states']} states, {meta['districts']} districts "
          f"({filled} NA rows filled) -> {api}")

if __name__ == '__main__':
    main()
