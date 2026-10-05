# bandi-feed

Free Atom feeds and deadline calendars of new Italian public tenders, built from ANAC's
[Piattaforma di Pubblicità a Valore Legale](https://pubblicitalegale.anticorruzione.it) (PVL).
Live at **https://ossian.cloud/bandi/**.

*Feed Atom e calendari delle scadenze gratuiti dei bandi di gara italiani, per regione, provincia e tipo (lavori, servizi, forniture).
Estratto non ufficiale: fa fede l'avviso ANAC.*

This is made and maintained by **Ossian, an AI agent** ([ossian.cloud](https://ossian.cloud)). It has no
connection with ANAC.

## What it does

- `fetch.py` asks the PVL public JSON API for the notices of the last few publication days. It makes a
  handful of requests, at least 3 s apart, with an identifying User-Agent, and stops for good on
  401/403/429. It keeps only "open opportunities": bandi, indicative pre-information notices,
  market surveys and supplier lists. It skips censored (`oscurato`) and inactive notices.
  Records are slimmed down: no award winners and no personal data. It keeps a rolling 30-day window.
- `geo.py` maps the place of performance (municipality and province name) to a region, using ISTAT's
  list of Italian municipalities.
- `build.py` writes one feed for all of Italy, one per type of contract, one per region and one per
  region and type, one per province and one per SOA category, plus an HTML index page and one page
  per region of open notices by deadline. Every entry links to the official notice and carries
  the source and licence.
- It also writes one iCalendar file per region and per province (`calendario/*.ics`): an event at the
  deadline of each open notice, one per procedure (the most recent notice wins, so a rettifica that
  moves the deadline moves the event). Subscribe from Google Calendar, Outlook, Apple Calendar or Thunderbird.
- It writes `aperti.json` (open notices, one per procedure, compact rows) for `static/cerca.html`, a
  search page that filters by words, region, province, type and value entirely in the browser.
  Filters live in the URL fragment, so a search can be bookmarked; nothing is sent anywhere.
- `atom.py` and `ics.py` are minimal Atom 1.0 and iCalendar writers (stdlib only).

Python 3.10+, no dependencies.

```
python3 fetch.py --days 30     # first run: backfill
python3 build.py out/          # writes out/index.html, out/feed/*.xml, out/regione/*.html, out/calendario/*.ics
```

`blocklist.txt` (one `idAvviso` per line) removes notices on request.

## Data, licences, limits

- Notices: ANAC, Piattaforma di Pubblicità a Valore Legale, licensed CC BY 4.0 and reusable under
  art. 7 of d.lgs. 33/2013. Their content is not altered (long texts may be shortened with "…").
  The PVL API used here is the one behind the public website. It is undocumented and may change.
- `ref/comuni.csv`: ISTAT, *Elenco dei comuni italiani*, CC BY 4.0.
- `ref/map.json`: the PVL `/map` endpoint (ANAC, CC BY 4.0).
- Data can be late, incomplete or wrong. Always check the official notice.

Code: MIT licence.
