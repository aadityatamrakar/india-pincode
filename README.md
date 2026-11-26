# India PIN Code API

A free, static JSON API for Indian PIN codes. No API key, no signup, no rate limit, CORS enabled. One small JSON file per PIN (19,586 PINs) with the state, district and every post office. Served from GitHub Pages.

- Home page and live demo: https://aadityatamrakar.github.io/india-pincode/
- Base URL: `https://aadityatamrakar.github.io/india-pincode/v1/`

## Endpoints

| Endpoint | Returns |
| --- | --- |
| `/v1/{pin}.json` | One PIN: state, district, division/region/circle, centre point, all offices. Unknown PIN returns HTTP 404. |
| `/v1/states.json` | Every state with PIN counts and its districts (`[{state, pins, districts:[{district, pins}]}]`). |
| `/v1/meta.json` | PIN/office/state/district counts, build date, data source. |

GET only. There is no search endpoint, you need the 6-digit PIN.

## Response

`GET /v1/485001.json` (offices trimmed):

```json
{
  "pin": "485001",
  "state": "Madhya Pradesh",
  "district": "Satna",
  "division": "Satna",
  "region": "Jabalpur",
  "circle": "Madhya Pradesh",
  "lat": 24.58158,
  "lng": 80.82406,
  "offices": [
    { "name": "Satna", "type": "HO", "delivery": true, "lat": 24.56178, "lng": 80.83003 },
    { "name": "Satna Civil Line", "type": "SO", "delivery": false, "lat": 24.58117, "lng": 80.82364 },
    { "name": "Satna Semaria Chowk", "type": "SO", "delivery": false },
    { "name": "Bagha", "type": "BO", "delivery": true, "lat": 24.579, "lng": 80.832 }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `pin` | 6-digit PIN as a string |
| `state`, `district` | State/UT and district of the PIN (where most of its HO/SO offices are) |
| `division`, `region`, `circle` | India Post units, without the words Division/Region/Circle |
| `lat`, `lng` | Approximate centre of the PIN; omitted if no usable coordinates |
| `offices[]` | All offices, sorted HO, SO, BO, then by name |
| `offices[].name` | Place name, office suffix (B.O, S.O, H.O) removed |
| `offices[].type` | `HO` head office, `SO` sub office, `BO` branch office (usually a village) |
| `offices[].delivery` | `true` if the office delivers mail |
| `offices[].district`, `.state` | Only when different from the PIN's |
| `offices[].lat`, `.lng` | Only when different from the PIN's centre |

## Usage

JavaScript:

```js
const BASE = "https://aadityatamrakar.github.io/india-pincode/v1/";

async function lookupPin(pin) {
  const res = await fetch(BASE + pin + ".json");
  if (res.status === 404) return null; // PIN not found
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}
```

Form autofill:

```js
const cache = {};
pinInput.addEventListener("input", async (e) => {
  const pin = e.target.value.trim();
  if (!/^[1-9]\d{5}$/.test(pin)) return;
  const res = await fetch(BASE + pin + ".json");
  if (!res.ok) return;
  const d = (cache[pin] ??= await res.json());
  state.value = d.state;
  district.value = d.district;
  let list = d.offices.filter((o) => o.type !== "BO");
  if (!list.length) list = d.offices; // some PINs have only BOs
  town.replaceChildren(...list.map((o) => new Option(o.name, o.name)));
});
```

curl:

```sh
curl -s https://aadityatamrakar.github.io/india-pincode/v1/485001.json
curl -s https://aadityatamrakar.github.io/india-pincode/v1/states.json | jq '.[].state'
```

Python:

```python
import json, urllib.request, urllib.error

BASE = "https://aadityatamrakar.github.io/india-pincode/v1/"

def lookup(pin):
    try:
        with urllib.request.urlopen(BASE + pin + ".json", timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
```

## Caching

GitHub Pages caches for about 10 minutes (`max-age=600`) and the data changes rarely. Cache responses in your app instead of re-fetching the same PIN. Best effort, no SLA: for heavy production use, host a copy yourself.

## Rebuilding

Python 3.9+ standard library only.

```sh
python3 -I scripts/build.py data/pincode-data.csv.gz _site   # ~4 s
python3 -m http.server -d _site 8765                          # preview
```

To use a newer directory: download the CSV from data.gov.in (All India Pincode Directory), save it as `data/pincode-data.csv`, run `gzip -f data/pincode-data.csv`, then rebuild. The CSV needs the columns `pincode, officename, officetype, delivery, district, statename, divisionname, regionname, circlename, latitude, longitude`.

Clean-up done by `scripts/build.py`: Title Case names; office suffixes moved to `type`; "NA" state/district filled from the same PIN or division; rows filed under a state their postal circle does not serve corrected; renamed districts updated (Hoshangabad to Narmadapuram, East Nimar to Khandwa, West Nimar to Khargone); coordinates outside India dropped.

## Deployment

`.github/workflows/pages.yml` runs on every push to `main` that touches `data/`, `scripts/`, `site/` or the workflow (and on manual dispatch). It builds `_site` with the script and publishes it with `actions/deploy-pages`. The generated JSON is never committed. One-time setup: in the repo, Settings, Pages, set Source to "GitHub Actions".

## Data and licence

Data: India Post, *All India Pincode Directory*, from [data.gov.in](https://www.data.gov.in/), under the [Government Open Data License - India](https://data.gov.in/government-open-data-license-india). Attribute India Post / data.gov.in when you use it.

Code: MIT, see [LICENSE](LICENSE).

## Disclaimer

Not an official India Post service, no warranty. District boundaries follow India Post and can lag newly created districts. Coordinates are approximate. Verify anything critical with India Post.
