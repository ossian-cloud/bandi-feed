"""Fetch open opportunities (bandi, pre-information, market surveys, supplier lists)
from ANAC's Pubblicità a Valore Legale platform and keep slim, person-free records.

Usage: python3 fetch.py [--days N]
Writes data/notices.json (dict idAvviso -> slim record), keeping a rolling window.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import geo

API = "https://pubblicitalegale.anticorruzione.it/api/v0"
SITE = "https://pubblicitalegale.anticorruzione.it"
UA = "OssianBot/0.1 (+https://ossian.cloud/bandi/; ossian@ossian.cloud)"
PAUSE = 3  # seconds between requests
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "notices.json")
BLOCKLIST = os.path.join(HERE, "blocklist.txt")  # idAvviso removed on request
WINDOW_DAYS = 30
CATS = os.path.join(HERE, "data", "categorie.json")  # SOA code -> label, as written by ANAC
CAT_LABELS = json.load(open(CATS)) if os.path.exists(CATS) else {}

# template number -> (group key, Italian label, detail-page root)
GROUPS = {
    "2": ("preinformazione", "Avviso di preinformazione (indittivo)", "bandi"),
    "4": ("bando", "Bando di gara", "bandi"),
    "5a": ("indagine", "Indagine di mercato", "avvisi"),
    "5b": ("indagine", "Indagine di mercato", "avvisi"),
    "6": ("elenco", "Elenco operatori economici", "avvisi"),
}


class Blocked(Exception):
    pass


_last = 0.0


def get(path, params):
    global _last
    wait = PAUSE - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise Blocked(f"HTTP {e.code} on {url}")
        raise
    finally:
        _last = time.time()
    return json.loads(body)


def section(T, prefix):
    for s in T.get("sections", []):
        if (s.get("name") or "").startswith(prefix):
            return s
    return {}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slim(item, template):
    """Keep only what a reader needs. No winners, no personal fields."""
    group, label, root = GROUPS[template]
    T = item["templates"][0]["template"]
    sa = (section(T, "SEZ. A").get("fields") or {}).get("soggetti_sa") or []
    gen = section(T, "SEZ. B").get("fields") or {}
    lots = []
    for it in section(T, "SEZ. C").get("items") or []:
        for c in it.get("categorie") or []:
            if c.get("codice") and c.get("descrizione"):
                CAT_LABELS[c["codice"]] = c["descrizione"]
        comune, prov = it.get("luogo_istat"), it.get("luogo_nuts")
        reg, pv = geo.place(comune, prov)
        lots.append({
            "cig": it.get("cig"),
            "descrizione": it.get("descrizione"),
            "natura": it.get("natura_principale"),
            "cpv": it.get("cpv"),
            "valore": num(it.get("valore_complessivo_stimato")),
            "comune": comune,
            "provincia": prov,
            "regione": reg,
            "prov": pv,
            "categorie": [c["codice"] for c in it.get("categorie") or [] if c.get("codice")],
            "annullato": bool(it.get("comunicazione_annullamento_revoca")),
        })
    return {
        "id": item["idAvviso"],
        "appalto": item.get("idAppalto"),
        "scheda": item.get("codiceScheda"),
        "gruppo": group,
        "tipo_label": label,
        "rettifica": item.get("tipo") == "rettifica",
        "link": f"{SITE}/{root}/{item['idAvviso']}",
        "pubblicato": item.get("dataPubblicazione"),
        "scadenza": item.get("dataScadenza"),
        "oggetto": T.get("metadata", {}).get("descrizione") or T.get("metadata", {}).get("titolo"),
        "ente": [{"nome": s.get("denominazione_amministrazione"), "cf": s.get("codice_fiscale")} for s in sa],
        "procedura": gen.get("tipo_procedura_aggiudicazione"),
        "documenti": gen.get("documenti_di_gara_link"),
        "ted": T.get("metadata", {}).get("link_eform_ted"),
        "lotti": lots,
    }


def fetch_day(day, templates):
    """All notices of the given templates published on `day` (a date)."""
    d = day.strftime("%d/%m/%Y")
    out, page = [], 0
    while True:
        res = get("avvisi", {"dataPubblicazioneStart": d, "dataPubblicazioneEnd": d,
                             "codiceScheda": ",".join(templates), "page": page, "size": 200,
                             "sortField": "dataPubblicazione", "sortDirection": "desc"})
        out += res.get("content", [])
        page += 1
        if page >= res.get("totalPages", 0):
            return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2, help="how many recent publication days to (re)fetch")
    args = ap.parse_args()

    db = json.load(open(DATA)) if os.path.exists(DATA) else {}
    blocked = set()
    if os.path.exists(BLOCKLIST):
        blocked = {l.split("#")[0].strip() for l in open(BLOCKLIST)} - {""}

    tmpl_of = {}
    for m in get("map", {})["templateSchedeMapping"]:
        for c in m["codiceScheda"]:
            tmpl_of[c] = m["template"]

    today = dt.date.today()
    days = [today - dt.timedelta(days=i) for i in range(args.days)]
    added = removed = 0
    try:
        for day in days:
            items = fetch_day(day, list(GROUPS))
            # a notice that ANAC withdrew, censored or deactivated disappears here too
            seen = {it["idAvviso"] for it in items
                    if tmpl_of.get(it.get("codiceScheda")) in GROUPS and not it.get("oscurato")
                    and it.get("attivo", True)}
            gone = [k for k, v in db.items() if (v["pubblicato"] or "")[:10] == day.isoformat() and k not in seen]
            for k in gone:
                del db[k]
            removed += len(gone)
            for it in items:
                t = tmpl_of.get(it.get("codiceScheda"))
                if t not in GROUPS or it.get("oscurato") or not it.get("attivo", True):
                    continue
                if it["idAvviso"] in blocked:
                    continue
                if it["idAvviso"] not in db:
                    added += 1
                db[it["idAvviso"]] = slim(it, t)
            if items:
                print(f"{day}: {len(items)} fetched", file=sys.stderr)
    except Blocked as e:
        # Never work around a block: save what we have, stop, and make it visible.
        print(f"BLOCKED: {e}", file=sys.stderr)
        open(os.path.join(HERE, "data", "BLOCKED"), "w").write(f"{dt.datetime.now().isoformat()} {e}\n")
        save(db, blocked)
        sys.exit(2)

    save(db, blocked)
    print(f"added {added}, removed {removed}, total {len(db)}", file=sys.stderr)


def save(db, blocked):
    cutoff = (dt.date.today() - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    db = {k: v for k, v in db.items() if (v["pubblicato"] or "") >= cutoff and k not in blocked}
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    tmp = DATA + ".tmp"
    json.dump(db, open(tmp, "w"), ensure_ascii=False)
    os.replace(tmp, DATA)
    json.dump(CAT_LABELS, open(CATS, "w"), ensure_ascii=False, indent=0, sort_keys=True)


if __name__ == "__main__":
    main()
