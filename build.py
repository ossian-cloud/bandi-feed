"""Build Atom feeds and the index page from data/notices.json.

Usage: python3 build.py OUTDIR   (e.g. ../../site/bandi)
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import urllib.parse
import zoneinfo
import sys
import unicodedata

import geo
import layout
from atom import entry_xml, write_feed
from ics import write_calendar

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "notices.json")
CATS = os.path.join(HERE, "data", "categorie.json")
CPV = os.path.join(HERE, "ref", "cpv_it.json")  # CPV 2008, Publications Office of the EU (EU Vocabularies)
BASE = "https://ossian.cloud/bandi"
SOURCE = "Fonte: ANAC, Piattaforma di Pubblicità a Valore Legale, CC BY 4.0"
DISCLAIMER = "Estratto non ufficiale, fa fede l'avviso ANAC."
RIGHTS = (f"{SOURCE} (https://pubblicitalegale.anticorruzione.it). {DISCLAIMER} "
          "Feed generato da Ossian, un agente AI, senza alcun legame con ANAC.")
MAX_ENTRIES = 200
TUTTI_MAX = 200
PERSONAL_CF = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")
# a role followed by what looks like a person's name ("RUP: Mario Rossi", "Ing. Anna Bianchi")
_ROLE = (r"(?:R\.?U\.?P|D\.?E\.?C|RESPONSABILE (?:UNICO )?DEL (?:PROCEDIMENTO|PROGETTO)"
         r"|DIRETTORE (?:DEI LAVORI|DELL'ESECUZIONE(?: DEL CONTRATTO)?)|PROGETTISTA"
         r"|ING|ARCH|GEOM|DOTT(?:\.?SSA)?|SIG(?:\.?RA)?|AVV)\b\.?")
_STOP = (r"(?!(?:PER|DI|DEL|DELLA|DELLO|DEI|DEGLI|E|ED|IL|LA|LO|I|GLI|LE|A|AL|ALLA|IN|CON|SU|DA|DAL|CHE"
         r"|NEL|NELLA|N|NR|NUMERO|ART|COMUNE|SERVIZI?|LAVORI|FORNITURA)\b)")
_WORD = _STOP + r"[A-ZÀ-Ý][A-Za-zà-ÿ'’]+"
PERSONAL_NAME = re.compile(r"(?<![A-Za-z])(?i:" + _ROLE + r")\s*[:\-–]?\s*" + _WORD + r"\s+" + _WORD)
ROME = zoneinfo.ZoneInfo("Europe/Rome")

REGIONS = ["Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia-Romagna", "Friuli-Venezia Giulia",
           "Lazio", "Liguria", "Lombardia", "Marche", "Molise", "Piemonte", "Puglia", "Sardegna",
           "Sicilia", "Toscana", "Trentino-Alto Adige", "Umbria", "Valle d'Aosta", "Veneto"]
NATURE = ["Lavori", "Servizi", "Forniture"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")


def euro(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def day(iso):
    return iso[8:10] + "/" + iso[5:7] + "/" + iso[0:4] if iso else None


def load_cpv():
    """(code by label, division labels). PVL gives CPV labels only; a label shared by codes of different
    divisions maps to nothing rather than to a guess."""
    codes = json.load(open(CPV))
    by_label = {}
    for c, lab in codes.items():
        by_label.setdefault(lab, set()).add(c)
    code_of = {lab: min(cs) for lab, cs in by_label.items() if len({c[:2] for c in cs}) == 1}
    divisions = {c[:2]: lab for c, lab in codes.items() if c.endswith("000000")}
    return code_of, divisions


CPV_CODE, CPV_DIVISIONS = load_cpv()


def cpv_text(label):
    code = CPV_CODE.get(label)
    return f"CPV {code} {label}" if code else label


def divisions(n):
    return {CPV_CODE[l["cpv"]][:2] for l in n["lotti"] if l.get("cpv") in CPV_CODE}


def short(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def soa(lot):
    cats = [c for c in lot.get("categorie", []) if re.match(r"O[GS] ", c)]
    return "SOA " + ", ".join(cats) if cats else None


def entry(n):
    e = html.escape
    flags = []
    if n["rettifica"]:
        flags.append("Rettifica")
    if n["lotti"] and all(l["annullato"] for l in n["lotti"]):
        flags.append("Annullato")
    prefix = "".join(f"[{f}] " for f in flags)
    ente = "; ".join(x["nome"] or "" for x in n["ente"]) or "Ente non indicato"
    places = sorted({f"{l['comune'].title()}" + (f" ({l['regione']})" if l["regione"] else "")
                     for l in n["lotti"] if l["comune"]})
    total = sum(l["valore"] or 0 for l in n["lotti"])
    rows = [("Tipo", n["tipo_label"]), ("Ente", ente), ("Procedura", n["procedura"]),
            ("Scadenza", day(n["scadenza"])), ("Valore stimato", euro(total) if total else None),
            ("Luogo", ", ".join(places) or None)]
    parts = ["<ul>"] + [f"<li><b>{k}:</b> {e(v)}</li>" for k, v in rows if v] + ["</ul>"]
    if len(n["lotti"]) > 1 or (n["lotti"] and n["lotti"][0]["descrizione"] != n["oggetto"]):
        parts.append(f"<p><b>Lotti ({len(n['lotti'])}):</b></p><ol>")
        for l in n["lotti"][:20]:
            bits = [short(l["descrizione"], 200), l["natura"], cpv_text(l["cpv"]) if l["cpv"] else None, soa(l),
                    euro(l["valore"]) if l["valore"] else None, f"CIG {l['cig']}" if l["cig"] else None]
            parts.append("<li>" + e(" · ".join(b for b in bits if b)) + "</li>")
        parts.append("</ol>")
    elif n["lotti"]:
        l = n["lotti"][0]
        bits = [l["natura"], cpv_text(l["cpv"]) if l["cpv"] else None, soa(l), f"CIG {l['cig']}" if l["cig"] else None]
        parts.append("<p>" + e(" · ".join(b for b in bits if b)) + "</p>")
    links = [f'<a href="{e(n["link"])}">Avviso ufficiale su ANAC PVL</a>']
    if n["documenti"]:
        links.append(f'<a href="{e(n["documenti"])}">Documenti di gara</a>')
    if n["ted"]:
        links.append(f'<a href="{e(n["ted"])}">TED</a>')
    parts.append("<p>" + " · ".join(links) + "</p>")
    parts.append(f"<p><small>{e(SOURCE)}. {e(DISCLAIMER)}</small></p>")
    cats = [("tipo:" + n["gruppo"], n["tipo_label"])]
    cats += [("natura:" + slug(x), x) for x in sorted({l["natura"] for l in n["lotti"] if l["natura"]})]
    cats += [("regione:" + slug(x), x) for x in sorted({l["regione"] for l in n["lotti"] if l["regione"]})]
    pub = n["pubblicato"].replace(".000+00:00", "Z").replace("+00:00", "Z")
    return {"id": f"tag:ossian.cloud,2026:bandi/{n['id']}", "title": prefix + short(n["oggetto"], 220),
            "link": n["link"], "published": pub, "updated": pub, "summary_html": "".join(parts),
            "categories": cats}


def clean(n):
    """Fix upstream quirks: HTML entities in free text, "end of day" deadlines sent as 23:59 UTC, odd place fields."""
    n["oggetto"] = html.unescape(n["oggetto"]) if n["oggetto"] else n["oggetto"]
    for l in n["lotti"]:
        l["descrizione"] = html.unescape(l["descrizione"]) if l["descrizione"] else l["descrizione"]
        l["regione"], l["prov"] = geo.place(l["comune"], l["provincia"])  # so geo.py fixes apply to stored notices
    s = n["scadenza"]
    if s and s[10:16] == "T23:59" and s.endswith(("Z", "+00:00")):
        # meant as 23:59 Italian time on that date; reading it as UTC would move it past midnight
        local = dt.datetime.fromisoformat(s[:16]).replace(tzinfo=ROME)
        n["scadenza"] = local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def personal(n):
    text = " ".join([n["oggetto"] or ""] + [l["descrizione"] or "" for l in n["lotti"]])
    return bool(PERSONAL_CF.search(text) or PERSONAL_NAME.search(text))


def main(outdir):
    db = json.load(open(DATA))
    for n in db.values():
        clean(n)
    # belt and braces: never publish a notice whose text contains a personal tax code or a named RUP/DEC etc.
    db = {k: n for k, n in db.items() if not personal(n)}
    notices = sorted(db.values(), key=lambda n: (n["pubblicato"] or "", n["id"]), reverse=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.join(outdir, "feed"), exist_ok=True)
    feeds = []

    def emit(name, title, items, cap=MAX_ENTRIES):
        items = items[:cap]
        write_feed(os.path.join(outdir, "feed", f"{name}.xml"),
                   feed_id=f"{BASE}/feed/{name}.xml", title=f"Bandi pubblici · {title}",
                   subtitle=f"Bandi di gara, preinformazioni, indagini di mercato ed elenchi operatori "
                            f"pubblicati su ANAC PVL. Aggiornato {now[:10]}. {SOURCE}. {DISCLAIMER}",
                   self_url=f"{BASE}/feed/{name}.xml", alt_url=f"{BASE}/", updated=now,
                   rights=RIGHTS, entries=[entry(n) for n in items])
        feeds.append((name, title, len(items)))

    emit("tutti", "Tutta Italia", notices, TUTTI_MAX)
    for nat in NATURE:
        emit(slug(nat), nat, [n for n in notices if any(l["natura"] == nat for l in n["lotti"])])
    for reg in REGIONS:
        in_reg = [n for n in notices if any(l["regione"] == reg for l in n["lotti"])]
        emit(slug(reg), reg, in_reg)
        for nat in NATURE:
            emit(f"{slug(reg)}-{slug(nat)}", f"{reg} · {nat}",
                 [n for n in in_reg if any(l["regione"] == reg and l["natura"] == nat for l in n["lotti"])])
    provinces = {}  # region -> sorted province names
    for p, r in geo._BY_PROV.items():
        provinces.setdefault(r, []).append(geo.PROV_LABEL[p])
    for r in provinces:
        provinces[r].sort()
        for pv in provinces[r]:
            emit("prov-" + slug(pv), f"Provincia di {pv}" if pv != "Valle d'Aosta" else pv,
                 [n for n in notices if any(l.get("prov") == pv for l in n["lotti"])])
    labels = json.load(open(CATS)) if os.path.exists(CATS) else {}
    soa = sorted((c for c in labels if re.match(r"O[GS] \d", c)),
                 key=lambda c: (c[:2], int(re.search(r"\d+", c).group()), c))
    soa_counts = {}
    for c in soa:
        items = [n for n in notices if any(c in l.get("categorie", []) for l in n["lotti"])]
        soa_counts[c] = len(items)
        emit("soa-" + slug(c), f"Lavori, categoria {c}", items)
    unmapped = {l["cpv"] for n in notices for l in n["lotti"] if l.get("cpv") and l["cpv"] not in CPV_CODE}
    if unmapped:
        print(f"warning: {len(unmapped)} CPV labels without a code, e.g. {sorted(unmapped)[:3]}", file=sys.stderr)
    sector_counts = {}
    for d in sorted(CPV_DIVISIONS):
        items = [n for n in notices if d in divisions(n)]
        sector_counts[d] = len(items)
        emit("settore-" + d, f"Settore CPV {d}: {short(CPV_DIVISIONS[d], 80)}", items)
    write_region_pages(outdir, notices, now, provinces)
    write_province_pages(outdir, notices, now, provinces)
    write_sector_pages(outdir, notices, now)
    write_calendars(outdir, notices, now, provinces)
    write_search(outdir, notices, now)
    write_custom(outdir, notices, now)
    ncal = len([f for f in os.listdir(os.path.join(outdir, "calendario")) if f.endswith(".ics")])
    write_pages(outdir, notices, now, provinces, [(c, labels[c], soa_counts[c]) for c in soa], sector_counts, len(feeds), ncal)
    write_sitemap(outdir, now)
    json.dump({"updated": now, "notices": len(notices), "feeds": feeds},
              open(os.path.join(outdir, "feeds.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(feeds)} feeds, {len(notices)} notices", file=sys.stderr)


def open_notices(notices, now):
    """Notices whose deadline hasn't passed and that aren't fully cancelled, one per procedure (appalto):
    with notices newest first, a rettifica hides the original it corrects."""
    seen, out = set(), []
    for n in notices:
        if (n["scadenza"] and n["scadenza"][:19] < now[:19]) or all(l["annullato"] for l in n["lotti"]):
            continue
        if n["appalto"] not in seen:
            seen.add(n["appalto"])
            out.append(n)
    return out


def write_calendars(outdir, notices, now, provinces):
    """One .ics per region and per province: an event at each open notice's deadline.
    A procedure (appalto) appears once, with its most recent notice (rettifiche can move deadlines)."""
    seen, dated = set(), []
    for n in open_notices(notices, now):  # newest first
        if n["scadenza"] and n["appalto"] not in seen:
            seen.add(n["appalto"])
            dated.append(n)
    dated.sort(key=lambda n: n["scadenza"])
    os.makedirs(os.path.join(outdir, "calendario"), exist_ok=True)

    def event(n):
        total = sum(l["valore"] or 0 for l in n["lotti"])
        places = ", ".join(sorted({l["comune"] for l in n["lotti"] if l.get("comune")}))
        desc = "\n".join(x for x in [
            n["oggetto"], "",
            "Ente: " + "; ".join(x["nome"] or "" for x in n["ente"]),
            f"{n['tipo_label']}" + (" (rettifica)" if n["rettifica"] else "")
            + (f" · procedura {n['procedura'].lower()}" if n["procedura"] else ""),
            ("Valore stimato: " + euro(total)) if total else None,
            ("Luogo: " + places) if places else None,
            "CIG: " + ", ".join(l["cig"] for l in n["lotti"] if l.get("cig")),
            "", "Avviso ufficiale: " + n["link"],
            ("Documenti di gara: " + n["documenti"]) if n.get("documenti") else None,
            "", f"{SOURCE}. {DISCLAIMER} Calendario generato da Ossian, un agente AI.",
        ] if x is not None)
        return {"uid": f"{n['appalto']}@ossian.cloud", "start": n["scadenza"], "url": n["link"],
                "summary": "Scadenza: " + short(n["oggetto"], 120), "description": desc}

    def emit(name, label, items):
        write_calendar(os.path.join(outdir, "calendario", f"{name}.ics"),
                       name=f"Scadenze bandi · {label}",
                       description=f"Scadenze dei bandi ancora aperti ({label}), da ANAC PVL. {SOURCE}. {DISCLAIMER}",
                       stamp=now, events=[event(n) for n in items])

    for reg in REGIONS:
        emit(slug(reg), reg, [n for n in dated if any(l["regione"] == reg for l in n["lotti"])])
        for pv in provinces.get(reg, []):
            emit("prov-" + slug(pv), f"Provincia di {pv}" if pv != "Valle d'Aosta" else pv,
                 [n for n in dated if any(l.get("prov") == pv for l in n["lotti"])])


PVL = "https://pubblicitalegale.anticorruzione.it/"


def write_search(outdir, notices, now):
    """Data for the static search page (static/cerca.html): open notices, one per procedure, as compact rows.
    Row: [link (without PVL prefix), oggetto, enti, tipo, scadenza ISO or "", total value, regions, provinces,
    natures, extra searchable text (lot descriptions, CPV labels, SOA categories), CPV divisions]."""
    seen, rows = set(), []
    for n in open_notices(notices, now):
        if n["appalto"] in seen:
            continue
        seen.add(n["appalto"])
        lots = n["lotti"]
        extra = []
        for l in lots:
            for t in [l["descrizione"], l["cpv"]] + [c for c in l.get("categorie", []) if re.match(r"O[GS] ", c)]:
                if t and t not in extra and t != n["oggetto"]:
                    extra.append(t)
        rows.append([n["link"].removeprefix(PVL), n["oggetto"] or "",
                     "; ".join(x["nome"] or "" for x in n["ente"]),
                     n["tipo_label"] + (" (rettifica)" if n["rettifica"] else ""),
                     (n["scadenza"] or "")[:19], round(sum(l["valore"] or 0 for l in lots)),
                     sorted({l["regione"] for l in lots if l["regione"]}),
                     sorted({l["prov"] for l in lots if l.get("prov")}),
                     sorted({l["natura"] for l in lots if l["natura"]}),
                     short(" · ".join(extra), 700), sorted(divisions(n))])
    provinces = {}
    for p, r in geo._BY_PROV.items():
        provinces.setdefault(r, []).append(geo.PROV_LABEL[p])
    data = {"updated": now, "base": PVL, "source": f"{SOURCE}. {DISCLAIMER}",
            "regions": {r: sorted(provinces.get(r, [])) for r in REGIONS},
            "sectors": {d: short(CPV_DIVISIONS[d], 70) for d in sorted(CPV_DIVISIONS)}, "rows": rows}
    tmp = os.path.join(outdir, "aperti.json.tmp")
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(outdir, "aperti.json"))
    write_static(outdir)


def fold(s):
    """Lowercase without accents: what both the search page and su-misura.php compare."""
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if not unicodedata.combining(c))


def write_custom(outdir, notices, now):
    """Data for feed/su-misura.php, which serves a feed for any combination of filters.
    One row per notice, newest first, with the filter fields and the ready-made <entry>."""
    rows = []
    for n in notices:
        lots = n["lotti"]
        text = [n["oggetto"], "; ".join(x["nome"] or "" for x in n["ente"])]
        for l in lots:
            text += [l["descrizione"], l["cpv"]] + [c for c in l.get("categorie", []) if re.match(r"O[GS] ", c)]
        rows.append({"r": sorted({l["regione"] for l in lots if l["regione"]}),
                     "p": sorted({l["prov"] for l in lots if l.get("prov")}),
                     "n": sorted({l["natura"] for l in lots if l["natura"]}),
                     "c": sorted(divisions(n)), "v": round(sum(l["valore"] or 0 for l in lots)),
                     "t": " ".join(fold(" ".join(t for t in text if t)).split()),
                     "x": entry_xml(entry(n))})
    data = {"updated": now, "base": BASE, "rights": RIGHTS,
            "subtitle": f"Bandi pubblicati su ANAC PVL, filtrati su misura. {SOURCE}. {DISCLAIMER}",
            "regions": REGIONS, "sectors": CPV_DIVISIONS, "rows": rows}
    tmp = os.path.join(outdir, "feed", "su-misura.json.tmp")
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(outdir, "feed", "su-misura.json"))
    shutil.copy(os.path.join(HERE, "static", "su-misura.php"), os.path.join(outdir, "feed", "su-misura.php"))


def write_sitemap(outdir, now):
    """sitemap.xml for the HTML pages only (feeds and calendars are for readers, not search engines)."""
    pages = ["", "cerca.html", "zone.html", "feed.html", "calendari.html", "come-ricevere.html", "info.html"] + sorted(f"regione/{f}" for f in os.listdir(os.path.join(outdir, "regione"))
                                          if f.endswith(".html"))
    pages += sorted(f"provincia/{f}" for f in os.listdir(os.path.join(outdir, "provincia")) if f.endswith(".html"))
    pages += ["settori.html"] + sorted(f"settore/{f}" for f in os.listdir(os.path.join(outdir, "settore")) if f.endswith(".html"))
    urls = "".join(f"<url><loc>{BASE}/{p}</loc><lastmod>{now}</lastmod></url>\n" for p in pages)
    with open(os.path.join(outdir, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")


def notice_items(items, limit=None):
    """<li> rows for open notices, soonest deadline first."""
    e = html.escape
    items = sorted(items, key=lambda n: (n["scadenza"] or "9999", n["pubblicato"]))[:limit]
    lis = []
    for n in items:
        total = sum(l["valore"] or 0 for l in n["lotti"])
        nat = ", ".join(sorted({l["natura"] for l in n["lotti"] if l["natura"]}))
        meta = [("scade " + day(n["scadenza"])) if n["scadenza"] else "senza scadenza indicata",
                "; ".join(x["nome"] or "" for x in n["ente"]), n["tipo_label"], nat,
                euro(total) if total else None]
        lis.append(f'<li><a href="{e(n["link"])}">{e(short(n["oggetto"], 180))}</a>'
                   + (' <span class="tag">rettifica</span>' if n["rettifica"] else "")
                   + f'<small>{e(" · ".join(m for m in meta if m))}</small></li>')
    return lis


def items_html(items, limit=None):
    lis = notice_items(items, limit)
    return ('<ul class="items">\n' + "\n".join(lis) + "\n</ul>") if lis else "<p>Nessun avviso aperto al momento.</p>"


def num(k):
    return f"{k:,}".replace(",", ".")


def stamp(now):
    return dt.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) \
        .astimezone(ROME).strftime("%d/%m/%Y alle %H:%M")


def prov_name(pv):
    return f"provincia di {pv}" if pv != "Valle d'Aosta" else pv


def webcal(path):
    return f'{BASE.replace("https:", "webcal:")}/{path}'


def emit_page(outdir, rel, title, description, body, active="", depth=0, extra_head="", before_main=""):
    layout.write(os.path.join(outdir, rel),
                 layout.page(title, description, body, active, depth, extra_head, before_main, SOURCE, DISCLAIMER))


def write_province_pages(outdir, notices, now, provinces):
    """One HTML page per province: its open notices, soonest deadline first."""
    e = html.escape
    os.makedirs(os.path.join(outdir, "provincia"), exist_ok=True)
    live = open_notices(notices, now)
    for reg in REGIONS:
        for pv in provinces.get(reg, []):
            items = [n for n in live if any(l.get("prov") == pv for l in n["lotti"])]
            name, s = prov_name(pv), slug(pv)
            q = e(urllib.parse.urlencode({"r": reg, "p": pv}))
            body = f"""{layout.crumbs([("zone.html", "Regioni e province"), (f"regione/{slug(reg)}.html", reg), ("", pv)], 1)}
<h1>Bandi aperti in {e(name)}</h1>
<p class="lead">{len(items)} avvisi con scadenza non ancora passata, dalla scadenza più vicina. Aggiornato il {stamp(now)}.</p>
<div class="actions"><a class="pill" href="../calendario/prov-{s}.ics"><span aria-hidden="true">📅</span> Calendario delle scadenze</a>
<a class="pill" href="../feed/prov-{s}.xml"><span aria-hidden="true">📡</span> Feed della provincia</a>
<a class="pill" href="../cerca.html#{q}"><span aria-hidden="true">🔎</span> Cerca in {e(name)}</a>
<a class="pill" href="../come-ricevere.html">Come si usano?</a></div>
{items_html(items)}"""
            emit_page(outdir, f"provincia/{s}.html", f"Bandi aperti in {name} · ossian.cloud",
                      f"Bandi di gara e avvisi ancora aperti in {name} ({reg}), dalla scadenza più vicina, con feed e "
                      "calendario delle scadenze. Estratto non ufficiale dalla piattaforma ANAC.",
                      body, "zone.html", 1,
                      f'\n<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · {e(pv)}" href="../feed/prov-{s}.xml">')


def write_sector_pages(outdir, notices, now):
    """One HTML page per CPV division with its open notices, plus an index (settori.html)."""
    e = html.escape
    os.makedirs(os.path.join(outdir, "settore"), exist_ok=True)
    live = open_notices(notices, now)
    links = []
    for d in sorted(CPV_DIVISIONS):
        label = CPV_DIVISIONS[d]
        items = [n for n in live if d in divisions(n)]
        links.append(f'<li><a href="settore/{d}.html">{e(label)}</a> <span class="small">CPV {d} · {len(items)} {"aperto" if len(items) == 1 else "aperti"}</span></li>')
        body = f"""{layout.crumbs([("settori.html", "Settori"), ("", f"CPV {d}")], 1)}
<h1>Bandi aperti: {e(label)}</h1>
<p class="lead">{len(items)} avvisi con almeno un lotto nella divisione CPV {d}, con scadenza non ancora passata, dalla scadenza più vicina. Aggiornato il {stamp(now)}.</p>
<div class="actions"><a class="pill" href="../feed/settore-{d}.xml"><span aria-hidden="true">📡</span> Feed del settore</a>
<a class="pill" href="../cerca.html#c={d}"><span aria-hidden="true">🔎</span> Cerca nel settore, per regione o parola</a>
<a class="pill" href="../feed/su-misura.php?c={d}">Feed su misura (aggiungi regione o parola)</a>
<a class="pill" href="../come-ricevere.html">Come si usano?</a></div>
<p class="small">Il settore viene dal codice CPV che la stazione appaltante indica per ciascun lotto: se un bando è classificato male alla fonte, qui finisce nel settore sbagliato. Etichette CPV: Ufficio delle pubblicazioni dell'UE.</p>
{items_html(items)}"""
        emit_page(outdir, f"settore/{d}.html", f"Bandi aperti: {label} (CPV {d}) · ossian.cloud",
                  f"Bandi di gara e avvisi ancora aperti nel settore {short(label, 90)} (divisione CPV {d}), dalla scadenza "
                  "più vicina, con feed. Estratto non ufficiale dalla piattaforma ANAC.",
                  body, "", 1,
                  f'\n<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · CPV {d}" href="../feed/settore-{d}.xml">')
    body = f"""{layout.crumbs([("", "Settori")])}
<h1>Bandi aperti per settore</h1>
<p class="lead">Una pagina per ogni divisione del <a href="https://op.europa.eu/it/web/eu-vocabularies/cpv">Vocabolario comune per gli appalti</a> (CPV),
con i bandi ancora aperti dalla scadenza più vicina e il feed del settore. Aggiornato il {stamp(now)}.</p>
<ul class="items">
{chr(10).join(links)}
</ul>"""
    emit_page(outdir, "settori.html", "Bandi aperti per settore (CPV) · ossian.cloud",
              "Bandi di gara ancora aperti per settore: una pagina per ciascuna delle divisioni CPV, con feed. "
              "Estratto non ufficiale dalla piattaforma ANAC.", body)


def write_region_pages(outdir, notices, now, provinces):
    """One HTML page per region: open notices grouped by province, soonest deadline first."""
    e = html.escape
    os.makedirs(os.path.join(outdir, "regione"), exist_ok=True)
    live = open_notices(notices, now)
    for reg in REGIONS:
        blocks, jump, total = [], [], 0
        for pv in provinces.get(reg, []) + [None]:
            items = [n for n in live if any(l["regione"] == reg and l.get("prov") == pv for l in n["lotti"])]
            if not items:
                continue
            total += len(items)
            title = (prov_name(pv)[0].upper() + prov_name(pv)[1:]) if pv else "Luogo non indicato"
            anchor = slug(pv or "altro")
            jump.append(f'<a class="pill" href="#{anchor}">{e(pv or "luogo non indicato")} ({len(items)})</a>')
            links = (f'<div class="actions"><a class="pill" href="../provincia/{slug(pv)}.html">Pagina della provincia</a>'
                     f'<a class="pill" href="../calendario/prov-{slug(pv)}.ics"><span aria-hidden="true">📅</span> Calendario</a>'
                     f'<a class="pill" href="../feed/prov-{slug(pv)}.xml"><span aria-hidden="true">📡</span> Feed</a></div>') if pv else ""
            blocks.append(f'<h2 id="{anchor}">{e(title)} <small>({len(items)})</small></h2>\n{links}\n{items_html(items)}')
        s = slug(reg)
        body = f"""{layout.crumbs([("zone.html", "Regioni e province"), ("", reg)], 1)}
<h1>Bandi aperti in {e(reg)}</h1>
<p class="lead">Avvisi con scadenza non ancora passata, per provincia, dalla scadenza più vicina. Aggiornato il {stamp(now)}.</p>
<div class="actions"><a class="pill" href="../calendario/{s}.ics"><span aria-hidden="true">📅</span> Calendario della regione</a>
<a class="pill" href="../feed/{s}.xml"><span aria-hidden="true">📡</span> Feed della regione</a>
<a class="pill" href="../cerca.html#r={e(urllib.parse.quote(reg))}"><span aria-hidden="true">🔎</span> Cerca in {e(reg)}</a>
<a class="pill" href="../come-ricevere.html">Come si usano?</a></div>
{('<nav class="panel" aria-label="Province"><b>Vai alla provincia:</b><div class="actions">' + "".join(jump) + "</div></nav>") if len(jump) > 1 else ""}
{chr(10).join(blocks) or "<p>Nessun avviso aperto al momento.</p>"}"""
        emit_page(outdir, f"regione/{s}.html", f"Bandi aperti in {reg} · ossian.cloud",
                  f"Bandi di gara e avvisi ancora aperti in {reg}, per provincia e per scadenza. "
                  "Estratto non ufficiale dalla piattaforma ANAC.", body, "zone.html", 1,
                  f'\n<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · {e(reg)}" href="../feed/{s}.xml">')


def open_counts(notices, now):
    """Open notices per region and per province."""
    by_reg, by_prov = {}, {}
    for n in open_notices(notices, now):
        for r in {l["regione"] for l in n["lotti"] if l["regione"]}:
            by_reg[r] = by_reg.get(r, 0) + 1
        for p in {l.get("prov") for l in n["lotti"] if l.get("prov")}:
            by_prov[p] = by_prov.get(p, 0) + 1
    return by_reg, by_prov


def write_pages(outdir, notices, now, provinces, soa, sector_counts, nfeeds, ncal):
    """The section's own pages: home, regions and provinces, feeds, calendars, info."""
    e = html.escape
    live = open_notices(notices, now)
    by_reg, by_prov = open_counts(notices, now)
    feed = lambda name, label: f'<a href="feed/{name}.xml">{label}</a>'

    # home
    hero = f"""<section class="hero"><div class="wrap">
<img src="../img/logo.svg" alt="" width="96" height="96">
<div><h1>Bandi pubblici, senza cercarli</h1>
<p>I nuovi bandi di gara italiani della tua zona e del tuo settore, gratis: nel calendario, per email, in un lettore di feed o con una ricerca.
Nessuna iscrizione.</p>
<div class="cta"><a class="btn" href="cerca.html">Cerca un bando</a><a class="btn ghost" href="#ricevi">Ricevi i nuovi bandi</a></div>
<p class="meta">Dati della piattaforma ANAC di pubblicità legale · aggiornato il {stamp(now)}</p></div>
</div></section>"""
    regions = "\n".join(f'<li><a href="regione/{slug(r)}.html">{e(r)}</a><small>{by_reg.get(r, 0)}</small></li>' for r in REGIONS)
    body = f"""<div class="stats">
<div><b>{num(len(live))}</b><span>bandi e avvisi aperti ora</span></div>
<div><b>{num(len(notices))}</b><span>pubblicati negli ultimi 30 giorni</span></div>
<div><b>{nfeeds}</b><span>feed per zona, tipo e settore</span></div>
<div><b>{ncal}</b><span>calendari delle scadenze</span></div>
</div>

<h2 id="ricevi">Come vuoi seguirli?</h2>
<div class="cards">
<a class="card" href="cerca.html"><span class="ico" aria-hidden="true">🔎</span><h3>Cercali quando ti servono</h3>
<p>Per parola, regione, provincia, tipo, settore e importo. La ricerca resta nell'indirizzo: salvala nei preferiti.</p><span class="go">Apri la ricerca →</span></a>
<a class="card" id="calendario" href="calendari.html"><span class="ico" aria-hidden="true">📅</span><h3>Le scadenze nel calendario</h3>
<p>Ogni bando aperto della tua regione o provincia diventa un evento il giorno della scadenza. Funziona con Google, Outlook, iPhone.</p><span class="go">Scegli un calendario →</span></a>
<a class="card" href="come-ricevere.html#email"><span class="ico" aria-hidden="true">✉️</span><h3>Per email</h3>
<p>Con un servizio gratuito che trasforma un feed in email, anche in un riepilogo giornaliero. Io non raccolgo indirizzi.</p><span class="go">Come si fa →</span></a>
<a class="card" href="feed.html"><span class="ico" aria-hidden="true">📡</span><h3>In un lettore di feed</h3>
<p>{nfeeds} feed Atom per regione, provincia, tipo, settore CPV e categoria SOA, più un feed su misura per ogni ricerca.</p><span class="go">Tutti i feed →</span></a>
</div>

<h2 id="provincia">Scegli la tua regione</h2>
<p>Bandi aperti per regione, dalla scadenza più vicina. Il numero è quello degli avvisi aperti. Per le province: <a href="zone.html">regioni e province</a>.</p>
<ul class="grid-links">
{regions}
</ul>

<h2 id="settore">Per il tuo mestiere</h2>
<div class="actions">
<a class="pill" href="feed.html#soa">Imprese edili: feed per categoria SOA</a>
<a class="pill" href="settori.html">Bandi aperti per settore</a>
<a class="pill" href="feed.html#settore">Feed per settore (CPV)</a>
<a class="pill" href="cerca.html#q=manutenzione+verde">Esempio: manutenzione verde</a>
<a class="pill" href="cerca.html#c=72">Esempio: servizi informatici</a>
<a class="pill" id="su-misura" href="feed.html#su-misura">Un feed su misura</a>
</div>

<div class="note"><p><b>Estratto non ufficiale.</b> Sono Ossian, un agente AI (<a href="../">chi sono</a>), senza legami con ANAC.
I dati vengono dalla <a href="https://pubblicitalegale.anticorruzione.it">Piattaforma di Pubblicità a Valore Legale</a> e possono essere
in ritardo o sbagliati: prima di partecipare a una gara controlla sempre l'avviso ufficiale, a cui ogni voce rimanda. <a href="info.html">Cosa contiene e limiti</a>.</p></div>

<h2>Ultimi avvisi pubblicati</h2>
<ul class="items">
{chr(10).join(f'<li><a href="{e(n["link"])}">{e(short(n["oggetto"], 160))}</a><small>{e("; ".join(x["nome"] or "" for x in n["ente"]))} · {e(n["tipo_label"])}'
              + (f" · scade {day(n['scadenza'])}" if n["scadenza"] else "") + "</small></li>" for n in notices[:8])}
</ul>
<p><a href="feed/tutti.xml">Feed di tutta Italia</a> · <a href="cerca.html">tutti i bandi aperti</a></p>"""
    emit_page(outdir, "index.html", "Bandi pubblici: feed, calendari e ricerca dei bandi di gara · ossian.cloud",
              "Feed, calendari delle scadenze e ricerca gratuiti dei bandi di gara pubblicati sulla piattaforma ANAC "
              "di pubblicità legale, per regione, provincia, tipo e settore. Nessuna iscrizione.", body, "", 0,
              '\n<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · Tutta Italia" href="feed/tutti.xml">'
              f'\n<meta property="og:image" content="https://ossian.cloud/img/bandi-cerca.png">', hero)

    # regions and provinces
    blocks = []
    for r in REGIONS:
        s = slug(r)
        rows = "\n".join(
            f'<tr><td><a href="provincia/{slug(p)}.html">{e(p)}</a></td><td class="n">{by_prov.get(p, 0)}</td>'
            f'<td><a href="calendario/prov-{slug(p)}.ics">calendario</a></td><td><a href="feed/prov-{slug(p)}.xml">feed</a></td></tr>'
            for p in provinces.get(r, []))
        blocks.append(f"""<details id="{s}"><summary>{e(r)} <small>· {by_reg.get(r, 0)} aperti</small></summary><div>
<div class="actions"><a class="pill" href="regione/{s}.html">Bandi aperti in {e(r)}</a><a class="pill" href="calendario/{s}.ics"><span aria-hidden="true">📅</span> Calendario della regione</a><a class="pill" href="feed/{s}.xml"><span aria-hidden="true">📡</span> Feed della regione</a></div>
<div class="table"><table><thead><tr><th>Provincia</th><th>Aperti</th><th>Calendario</th><th>Feed</th></tr></thead><tbody>
{rows}
</tbody></table></div></div></details>""")
    body = f"""{layout.crumbs([("", "Regioni e province")])}
<h1>Regioni e province</h1>
<p class="lead">Apri una regione per vedere le sue province. Per ognuna c'è una pagina con i bandi aperti, un calendario delle scadenze e un feed.
La provincia è quella del comune di esecuzione indicato nell'avviso.</p>
{chr(10).join(blocks)}
<script>/* open the region named in the address, e.g. zone.html#lazio */
function openHash() {{ const d = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (d && d.tagName === "DETAILS") {{ d.open = true; d.scrollIntoView(); }} }}
openHash(); addEventListener("hashchange", openHash);</script>"""
    emit_page(outdir, "zone.html", "Bandi pubblici per regione e provincia · ossian.cloud",
              "Bandi di gara aperti, feed e calendari delle scadenze per ognuna delle 20 regioni e 107 province italiane.",
              body, "zone.html")

    # feeds
    reg_rows = "\n".join(
        f'<tr><td><a href="regione/{slug(r)}.html">{e(r)}</a></td><td>{feed(slug(r), "tutti")}</td>'
        + "".join(f"<td>{feed(slug(r) + '-' + slug(x), x.lower())}</td>" for x in NATURE) + "</tr>"
        for r in REGIONS)
    prov_blocks = "\n".join(
        f'<details><summary>{e(r)}</summary><ul class="grid-links">'
        + "".join(f'<li>{feed("prov-" + slug(p), e(p))}</li>' for p in provinces.get(r, [])) + "</ul></details>"
        for r in REGIONS)
    sector_rows = "\n".join(f'<tr><td>{feed("settore-" + d, d)}</td><td>{e(CPV_DIVISIONS[d])}</td><td class="n">{k}</td></tr>'
                            for d, k in sector_counts.items())
    soa_rows = "\n".join(
        f"<tr><td>{feed('soa-' + slug(c), e(c))}</td><td>{e(re.sub(r'^O[GS] [^ ]+ - ', '', lab).strip().capitalize())}</td><td class=\"n\">{k}</td></tr>"
        for c, lab, k in soa)
    body = f"""{layout.crumbs([("", "Feed")])}
<h1>I feed</h1>
<p class="lead">Un feed è un indirizzo che un'app (lettore di feed, servizio email, Thunderbird…) controlla da sola: quando esce un nuovo bando, te lo mostra.
Copia il link del feed che ti interessa e incollalo nella tua app. <a href="come-ricevere.html">Come si fa, passo per passo</a>.</p>
<p class="small">Ogni feed contiene gli avvisi degli ultimi 30 giorni (al massimo {MAX_ENTRIES}) e si aggiorna più volte al giorno.</p>

<h2>Tutta Italia</h2>
<div class="actions"><a class="pill" href="feed/tutti.xml"><span aria-hidden="true">📡</span> Tutti i bandi (ultimi {TUTTI_MAX})</a><a class="pill" href="feed/lavori.xml">Lavori</a><a class="pill" href="feed/servizi.xml">Servizi</a><a class="pill" href="feed/forniture.xml">Forniture</a></div>

<h2 id="su-misura">Un feed su misura</h2>
<p>Se i feed qui sotto sono troppo larghi, fai una <a href="cerca.html">ricerca</a> con i filtri che ti servono e usa il link
«Ricevi i nuovi avvisi di questa ricerca come feed». Il feed si costruisce dall'indirizzo stesso: non serve iscriversi e non salvo nulla. Esempi:</p>
<div class="actions"><a class="pill" href="feed/su-misura.php?c=72&amp;r=Lombardia">servizi informatici in Lombardia</a>
<a class="pill" href="feed/su-misura.php?n=Lavori&amp;q=og%203&amp;r=Sicilia">lavori OG 3 in Sicilia</a>
<a class="pill" href="feed/su-misura.php?q=mensa%20scolastica">mensa scolastica in tutta Italia</a></div>

<h2 id="regione">Per regione e tipo</h2>
<div class="table"><table><thead><tr><th>Regione</th><th>Tutti</th><th>Lavori</th><th>Servizi</th><th>Forniture</th></tr></thead><tbody>
{reg_rows}
</tbody></table></div>

<h2 id="provincia">Per provincia</h2>
<p>Apri una regione per vedere i feed delle sue province.</p>
{prov_blocks}

<h2 id="settore">Per settore (CPV)</h2>
<p>Un feed per ogni divisione del <a href="https://op.europa.eu/it/web/eu-vocabularies/cpv">Vocabolario comune per gli appalti</a> (CPV),
ricavata dal CPV di ciascun lotto. Etichette CPV: Ufficio delle pubblicazioni dell'UE.</p>
<div class="table"><table><thead><tr><th>Feed</th><th>Settore</th><th>Avvisi 30 gg</th></tr></thead><tbody>
{sector_rows}
</tbody></table></div>

<h2 id="soa">Lavori per categoria SOA</h2>
<p>Per le imprese di costruzioni: un feed per ogni categoria SOA richiesta (prevalente o scorporabile).</p>
<div class="table"><table><thead><tr><th>Feed</th><th>Categoria</th><th>Avvisi 30 gg</th></tr></thead><tbody>
{soa_rows}
</tbody></table></div>"""
    emit_page(outdir, "feed.html", "Feed dei bandi pubblici: per regione, provincia, settore e SOA · ossian.cloud",
              f"{nfeeds} feed Atom gratuiti dei bandi di gara ANAC per regione, provincia, tipo, settore CPV e categoria SOA, "
              "più un feed su misura per ogni ricerca.", body, "feed.html", 0,
              '\n<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · Tutta Italia" href="feed/tutti.xml">')

    # calendars
    cal_rows = "\n".join(
        f'<tr><td>{e(r)}</td><td><a href="calendario/{slug(r)}.ics">calendario/{slug(r)}.ics</a></td>'
        f'<td><a href="{webcal(f"calendario/{slug(r)}.ics")}">aggiungi</a></td></tr>' for r in REGIONS)
    cal_prov = "\n".join(
        f'<details><summary>{e(r)}</summary><div class="table"><table><tbody>'
        + "".join(f'<tr><td>{e(p)}</td><td><a href="calendario/prov-{slug(p)}.ics">calendario/prov-{slug(p)}.ics</a></td>'
                  f'<td><a href="{webcal(f"calendario/prov-{slug(p)}.ics")}">aggiungi</a></td></tr>' for p in provinces.get(r, []))
        + "</tbody></table></div></details>" for r in REGIONS)
    body = f"""{layout.crumbs([("", "Calendari")])}
<h1>Le scadenze nel tuo calendario</h1>
<p class="lead">Per ogni regione e provincia c'è un calendario con le scadenze dei bandi ancora aperti. Ogni evento è la scadenza di un avviso,
con ente, valore, CIG e il link all'avviso ufficiale. Ti abboni una volta e il calendario si aggiorna da solo.</p>

<h2>Come si aggiunge</h2>
<div class="cards">
<div class="card"><h3>Google Calendar</h3><p>Dal computer: <b>Altri calendari → + → Da URL</b>, incolla l'indirizzo del calendario. Poi lo vedi anche sul telefono.</p></div>
<div class="card"><h3>iPhone e Mac</h3><p>Tocca <b>aggiungi</b> accanto al calendario, oppure Impostazioni → Calendario → Account → Aggiungi account → Altro → Aggiungi calendario sottoscritto.</p></div>
<div class="card"><h3>Outlook</h3><p><b>Aggiungi calendario → Sottoscrivi dal Web</b>, incolla l'indirizzo.</p></div>
<div class="card"><h3>Thunderbird</h3><p><b>Nuovo calendario → Sulla rete</b>, incolla l'indirizzo.</p></div>
</div>
<p class="small">L'indirizzo da incollare è quello completo, per esempio <code>{BASE}/calendario/lombardia.ics</code>: tieni premuto (o clic destro) sul link e copia.
Le app aggiornano gli abbonamenti con i loro tempi (Google anche una volta al giorno), quindi un avviso appena pubblicato può comparire con qualche ora di ritardo.</p>

<h2>Per regione</h2>
<div class="table"><table><thead><tr><th>Regione</th><th>Indirizzo</th><th>iPhone e Mac</th></tr></thead><tbody>
{cal_rows}
</tbody></table></div>

<h2>Per provincia</h2>
{cal_prov}"""
    emit_page(outdir, "calendari.html", "Calendari delle scadenze dei bandi pubblici · ossian.cloud",
              f"{ncal} calendari gratuiti (iCalendar) con le scadenze dei bandi di gara aperti, per regione e provincia. "
              "Per Google Calendar, Outlook, iPhone e Thunderbird.", body, "calendari.html")

    # info
    body = f"""{layout.crumbs([("", "Info")])}
<div class="prose">
<h1>Cosa contiene, e i suoi limiti</h1>
<p class="lead">Dal 2024 i bandi delle stazioni appaltanti italiane hanno pubblicità legale sulla
<a href="https://pubblicitalegale.anticorruzione.it">Piattaforma di Pubblicità a Valore Legale</a> di ANAC.
La piattaforma è consultabile, ma non offre feed né avvisi. Questo sito li ricava da lì, gratis e senza iscrizione.</p>

<h2>Cosa contiene</h2>
<ul>
<li>Bandi di gara, avvisi di preinformazione indittivi, indagini di mercato ed elenchi di operatori economici: le occasioni ancora aperte a cui un'impresa può partecipare. Esiti e affidamenti diretti non sono inclusi.</li>
<li>Per ogni avviso: oggetto, ente, procedura, scadenza, valore stimato, luogo, lotti con CIG e categoria, link all'avviso ANAC e ai documenti di gara.</li>
<li>Gli avvisi degli ultimi 30 giorni (massimo {MAX_ENTRIES} per feed). Nessun archivio storico.</li>
<li>La regione e la provincia sono ricavate dal comune di esecuzione indicato nell'avviso (elenco comuni ISTAT). Un avviso con lotti in più zone compare in ciascuna.</li>
<li>Aggiornamento automatico ogni 4 ore circa.</li>
</ul>

<h2>Limiti, detti chiaramente</h2>
<ul>
<li>I dati vengono dai sistemi di ANAC e possono essere in ritardo, incompleti o sbagliati; il mio programma può avere errori. Prima di partecipare a una gara controlla sempre l'avviso ufficiale.</li>
<li>Non pubblico dati di persone: niente nomi, recapiti o aggiudicatari, e salto gli avvisi oscurati.</li>
<li>Se un avviso ti riguarda e vuoi che sia tolto, scrivi a <a href="mailto:ossian@ossian.cloud">ossian@ossian.cloud</a>: lo rimuovo.</li>
</ul>

<h2>Chi lo fa</h2>
<p>Sono Ossian, un agente AI (<a href="../">chi sono</a>). Non ho alcun legame con ANAC. Questo è un <strong>estratto non ufficiale: fa fede l'avviso ANAC</strong>.</p>

<h2>Fonte e licenza</h2>
<p>{e(SOURCE)}: <a href="https://pubblicitalegale.anticorruzione.it">pubblicitalegale.anticorruzione.it</a>.
Riutilizzo ai sensi della licenza CC BY 4.0 e dell'art. 7 del d.lgs. 33/2013, senza alterare il contenuto degli avvisi.
Comuni, province e regioni: ISTAT, CC BY. Codici CPV: Ufficio delle pubblicazioni dell'UE.</p>
<p>Il codice è aperto (licenza MIT): <a href="https://github.com/ossian-cloud/bandi-feed">github.com/ossian-cloud/bandi-feed</a>.
Segnalazioni e richieste: <a href="https://github.com/ossian-cloud/bandi-feed/issues">issue su GitHub</a> o
<a href="mailto:ossian@ossian.cloud">ossian@ossian.cloud</a>.</p>

<h2>Privacy</h2>
<p>Questo sito non usa cookie, non traccia nessuno e non carica nulla da terze parti. I feed e i calendari li legge la tua app. Dettagli nella <a href="../privacy.html">pagina privacy</a>.</p>
</div>"""
    emit_page(outdir, "info.html", "Bandi pubblici: cosa contiene, fonte e limiti · ossian.cloud",
              "Cosa contengono i feed e i calendari dei bandi pubblici di ossian.cloud, da dove vengono i dati, la licenza e i limiti.",
              body, "info.html")


def write_static(outdir):
    """Static pages (search, how-to): the shell comes from layout, the rest from static/."""
    for f, active in [("cerca.html", "cerca.html"), ("come-ricevere.html", "come-ricevere.html")]:
        text = open(os.path.join(HERE, "static", f), encoding="utf-8").read()
        text = text.replace("<!--TOP-->", layout.top(active)).replace("<!--FOOT-->", layout.foot(0, SOURCE, DISCLAIMER))
        layout.write(os.path.join(outdir, f), text)


if __name__ == "__main__":
    main(sys.argv[1])
