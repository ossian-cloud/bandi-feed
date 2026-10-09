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
  region and type, one per province, one per SOA category and one per CPV division (sector), plus an HTML index page and one page
  per region, per province, per sector and per sector in each region (from 3 open notices; indexed from 5)
  of open notices by deadline. Every entry links to the official notice and carries the source and licence.
- `titles.py` makes page titles readable: it drops the procedural boilerplate in front of the real object
  ("Procedura aperta ai sensi dell'art. 71 ... per l'affidamento del") and fixes ALL-CAPS text. It only
  removes and re-cases the official words, never adds any; the page heading keeps the full object.
- It also writes one iCalendar file per region and per province (`calendario/*.ics`): an event at the
  deadline of each open notice, one per procedure (the most recent notice wins, so a rettifica that
  moves the deadline moves the event). Subscribe from Google Calendar, Outlook, Apple Calendar or Thunderbird.
- It writes `aperti.json` (open notices, one per procedure, compact rows) for `static/cerca.html`, a
  search page that filters by words, region, province, type, sector and value entirely in the browser.
  Filters live in the URL fragment, so a search can be bookmarked; nothing is sent anywhere.
- PVL gives each lot's CPV as an Italian label only. `ref/cpv_it.json` (CPV 2008, from the EU Publications
  Office's EU Vocabularies SPARQL endpoint, release 20260520-0) maps labels back to codes; on 2026-10-06
  all 6,367 labelled lots matched exactly one code. Entries show the code, and the search page can filter by division.
- It writes `feed/su-misura.json` (every notice with its filter fields and its ready-made Atom entry) for
  `static/su-misura.php`, which serves a feed for any combination of the search filters
  (`?r=Regione&p=Provincia&n=Servizi&c=72&q=parole&v=100000`). It reads only the query string and stores nothing.
  The search page links to the feed of the current search.
- One page per open procedure (and closed ones for 14 days, `noindex`) at `avviso/<id>.html`. The hosting caps
  the number of files, so the pages are stored in 16 gzipped JSON shards (`avviso/data/<hex>.json.gz`) and served
  by `static/avviso/page.php` through a rewrite in `static/avviso/.htaccess` (Apache). URLs look like static files.
- `atom.py` and `ics.py` are minimal Atom 1.0 and iCalendar writers (stdlib only).

Python 3.10+, no dependencies.

```
python3 fetch.py --days 30     # first run: backfill
python3 build.py out/          # writes out/index.html, out/feed/*.xml, out/regione/*.html, out/provincia/*.html, out/sitemap.xml, out/calendario/*.ics
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
