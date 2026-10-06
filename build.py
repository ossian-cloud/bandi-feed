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

import geo
from atom import write_feed
from ics import write_calendar

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "notices.json")
CATS = os.path.join(HERE, "data", "categorie.json")
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
            bits = [short(l["descrizione"], 200), l["natura"], l["cpv"], soa(l),
                    euro(l["valore"]) if l["valore"] else None, f"CIG {l['cig']}" if l["cig"] else None]
            parts.append("<li>" + e(" · ".join(b for b in bits if b)) + "</li>")
        parts.append("</ol>")
    elif n["lotti"]:
        l = n["lotti"][0]
        bits = [l["natura"], l["cpv"], soa(l), f"CIG {l['cig']}" if l["cig"] else None]
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
    write_region_pages(outdir, notices, now, provinces)
    write_province_pages(outdir, notices, now, provinces)
    write_calendars(outdir, notices, now, provinces)
    write_search(outdir, notices, now)
    write_page(outdir, notices, now, provinces, [(c, labels[c], soa_counts[c]) for c in soa])
    write_sitemap(outdir, now)
    json.dump({"updated": now, "notices": len(notices), "feeds": feeds},
              open(os.path.join(outdir, "feeds.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(feeds)} feeds, {len(notices)} notices", file=sys.stderr)


def open_notices(notices, now):
    """Notices whose deadline hasn't passed and that aren't fully cancelled."""
    return [n for n in notices
            if (not n["scadenza"] or n["scadenza"][:19] >= now[:19])
            and not all(l["annullato"] for l in n["lotti"])]


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
    natures, extra searchable text (lot descriptions, CPV labels, SOA categories)]."""
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
                     short(" · ".join(extra), 700)])
    provinces = {}
    for p, r in geo._BY_PROV.items():
        provinces.setdefault(r, []).append(geo.PROV_LABEL[p])
    data = {"updated": now, "base": PVL, "source": f"{SOURCE}. {DISCLAIMER}",
            "regions": {r: sorted(provinces.get(r, [])) for r in REGIONS}, "rows": rows}
    tmp = os.path.join(outdir, "aperti.json.tmp")
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(outdir, "aperti.json"))
    shutil.copy(os.path.join(HERE, "static", "cerca.html"), os.path.join(outdir, "cerca.html"))


def write_sitemap(outdir, now):
    """sitemap.xml for the HTML pages only (feeds and calendars are for readers, not search engines)."""
    pages = [""] + ["cerca.html"] + sorted(f"regione/{f}" for f in os.listdir(os.path.join(outdir, "regione"))
                                          if f.endswith(".html"))
    pages += sorted(f"provincia/{f}" for f in os.listdir(os.path.join(outdir, "provincia")) if f.endswith(".html"))
    urls = "".join(f"<url><loc>{BASE}/{p}</loc><lastmod>{now}</lastmod></url>\n" for p in pages)
    with open(os.path.join(outdir, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")


def notice_items(items):
    """<li> rows for open notices, soonest deadline first."""
    e = html.escape
    items = sorted(items, key=lambda n: (n["scadenza"] or "9999", n["pubblicato"]))
    lis = []
    for n in items:
        total = sum(l["valore"] or 0 for l in n["lotti"])
        nat = ", ".join(sorted({l["natura"] for l in n["lotti"] if l["natura"]}))
        meta = [("scade " + day(n["scadenza"])) if n["scadenza"] else "senza scadenza indicata",
                "; ".join(x["nome"] or "" for x in n["ente"]), n["tipo_label"], nat,
                euro(total) if total else None]
        lis.append(f'<li><a href="{e(n["link"])}">{e(short(n["oggetto"], 180))}</a>'
                   + (" <small>[rettifica]</small>" if n["rettifica"] else "")
                   + f'<br><small>{e(" · ".join(m for m in meta if m))}</small></li>')
    return lis


def write_province_pages(outdir, notices, now, provinces):
    """One plain HTML page per province: its open notices, soonest deadline first."""
    e = html.escape
    when = dt.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M UTC")
    os.makedirs(os.path.join(outdir, "provincia"), exist_ok=True)
    live = open_notices(notices, now)
    for reg in REGIONS:
        for pv in provinces.get(reg, []):
            items = [n for n in live if any(l.get("prov") == pv for l in n["lotti"])]
            name = f"provincia di {pv}" if pv != "Valle d'Aosta" else pv
            s = slug(pv)
            page = f"""<!doctype html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandi aperti in {e(name)} · ossian.cloud</title>
<meta name="description" content="Bandi di gara e avvisi ancora aperti in {e(name)} ({e(reg)}), dalla scadenza più vicina, con feed e calendario delle scadenze. Estratto non ufficiale dalla piattaforma ANAC.">
<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · {e(pv)}" href="../feed/prov-{s}.xml">
<link rel="stylesheet" href="../../style.css"></head>
<body><main>
<p><small><a href="../">← Bandi pubblici in feed</a> · <a href="../regione/{slug(reg)}.html">{e(reg)}</a> · <a href="../cerca.html#{e(urllib.parse.urlencode({"r": reg, "p": pv}))}">cerca in {e(name)}</a></small></p>
<h1>Bandi aperti in {e(name)}</h1>
<p class="sub">{len(items)} avvisi pubblicati negli ultimi 30 giorni con scadenza non ancora passata, dalla scadenza più vicina. Aggiornato {when}.
<a href="../feed/prov-{s}.xml">Feed Atom della provincia</a> ·
<a href="../calendario/prov-{s}.ics">calendario delle scadenze</a> (<a href="../#calendario">come si usa</a>).</p>
<p><small>{e(SOURCE)}. {e(DISCLAIMER)} Pagina generata da Ossian, un agente AI, senza legami con ANAC.</small></p>
{("<ul>" + chr(10) + chr(10).join(notice_items(items)) + chr(10) + "</ul>") if items else "<p>Nessun avviso aperto al momento.</p>"}
<footer><a href="../">Bandi pubblici in feed</a> · <a href="../../privacy.html">privacy</a> · gestito da un agente AI</footer>
</main></body>
</html>
"""
            path = os.path.join(outdir, "provincia", f"{s}.html")
            open(path + ".tmp", "w", encoding="utf-8").write(page)
            os.replace(path + ".tmp", path)


def write_region_pages(outdir, notices, now, provinces):
    """One plain HTML page per region: open notices grouped by province, soonest deadline first."""
    e = html.escape
    when = dt.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M UTC")
    os.makedirs(os.path.join(outdir, "regione"), exist_ok=True)
    for reg in REGIONS:
        blocks = []
        for pv in provinces.get(reg, []) + [None]:
            items = [n for n in open_notices(notices, now)
                     if any(l["regione"] == reg and l.get("prov") == pv for l in n["lotti"])]
            if not items:
                continue
            lis = notice_items(items)
            title = f"Provincia di {pv}" if pv and pv != "Valle d'Aosta" else (pv or "Luogo non indicato")
            feed = (f' <small><a href="../provincia/{slug(pv)}.html">pagina</a> · '
                    f'<a href="../feed/prov-{slug(pv)}.xml">feed</a> · '
                    f'<a href="../calendario/prov-{slug(pv)}.ics">calendario</a></small>') if pv else ""
            blocks.append(f'<h2 id="{slug(pv or "altro")}">{e(title)} ({len(items)}){feed}</h2>\n<ul>\n'
                          + "\n".join(lis) + "\n</ul>")
        page = f"""<!doctype html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandi aperti in {e(reg)} · ossian.cloud</title>
<meta name="description" content="Bandi di gara e avvisi ancora aperti in {e(reg)}, per provincia e per scadenza. Estratto non ufficiale dalla piattaforma ANAC.">
<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · {e(reg)}" href="../feed/{slug(reg)}.xml">
<link rel="stylesheet" href="../../style.css"></head>
<body><main>
<p><small><a href="../">← Bandi pubblici in feed</a> · <a href="../cerca.html#r={e(reg)}">cerca in {e(reg)}</a></small></p>
<h1>Bandi aperti in {e(reg)}</h1>
<p class="sub">Avvisi pubblicati negli ultimi 30 giorni con scadenza non ancora passata, per provincia, dalla scadenza più vicina. Aggiornato {when}.
<a href="../feed/{slug(reg)}.xml">Feed Atom della regione</a> ·
<a href="../calendario/{slug(reg)}.ics">calendario delle scadenze</a> (<a href="../#calendario">come si usa</a>).</p>
<p><small>{e(SOURCE)}. {e(DISCLAIMER)} Pagina generata da Ossian, un agente AI, senza legami con ANAC.</small></p>
{chr(10).join(blocks) or "<p>Nessun avviso aperto al momento.</p>"}
<footer><a href="../">Bandi pubblici in feed</a> · <a href="../../privacy.html">privacy</a> · gestito da un agente AI</footer>
</main></body>
</html>
"""
        path = os.path.join(outdir, "regione", f"{slug(reg)}.html")
        open(path + ".tmp", "w", encoding="utf-8").write(page)
        os.replace(path + ".tmp", path)


def write_page(outdir, notices, now, provinces, soa):
    e = html.escape
    when = dt.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y %H:%M UTC")
    counts = {}
    for n in notices:
        for reg in {l["regione"] for l in n["lotti"] if l["regione"]}:
            counts[reg] = counts.get(reg, 0) + 1

    def a(name, label):
        return f'<a href="feed/{name}.xml">{label}</a>'

    rows = "\n".join(
        f"<tr><td><a href=\"regione/{slug(r)}.html\">{e(r)}</a></td><td>{counts.get(r, 0)}</td><td>{a(slug(r), 'tutti')}</td>"
        + "".join(f"<td>{a(slug(r) + '-' + slug(x), x.lower())}</td>" for x in NATURE)
        + f'<td><a href="calendario/{slug(r)}.ics">.ics</a> · <a href="{BASE.replace("https:", "webcal:")}/calendario/{slug(r)}.ics">webcal</a></td></tr>'
        for r in REGIONS)
    latest = "\n".join(
        f'<li><a href="{e(n["link"])}">{e(short(n["oggetto"], 140))}</a> '
        f'<small>{e("; ".join(x["nome"] or "" for x in n["ente"]))} · {e(n["tipo_label"])}'
        + (f" · scade {day(n['scadenza'])}" if n["scadenza"] else "") + "</small></li>"
        for n in notices[:15])
    prov_rows = "\n".join(
        f"<li><b>{e(r)}:</b> " + " · ".join(f'<a href="provincia/{slug(p)}.html">{e(p)}</a> <small>({a("prov-" + slug(p), "feed")})</small>'
                                    for p in provinces.get(r, [])) + "</li>"
        for r in REGIONS)
    soa_rows = "\n".join(
        f"<li>{a('soa-' + slug(c), e(c))} {e(re.sub(r'^O[GS] [^ ]+ - ', '', lab).strip().capitalize())} ({k})</li>"
        for c, lab, k in soa)
    page = f"""<!doctype html>
<html lang="it">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandi pubblici in feed · ossian.cloud</title>
<meta name="description" content="Feed Atom gratuiti dei bandi di gara pubblicati sulla piattaforma ANAC di pubblicità legale, per regione e per tipo (lavori, servizi, forniture).">
<link rel="alternate" type="application/atom+xml" title="Bandi pubblici · Tutta Italia" href="feed/tutti.xml">
<link rel="stylesheet" href="../style.css"></head>
<body><main>
<h1>Bandi pubblici in feed</h1>
<p class="sub">Feed e calendari gratuiti dei nuovi bandi di gara italiani, per regione, provincia e tipo. Aggiornato {when}.</p>

<p>Dal 2024 i bandi delle stazioni appaltanti italiane hanno pubblicità legale sulla
<a href="https://pubblicitalegale.anticorruzione.it">Piattaforma di Pubblicità a Valore Legale</a> di ANAC.
La piattaforma è consultabile, ma non offre feed né avvisi. Qui trovi i nuovi avvisi in formato
<a href="https://it.wikipedia.org/wiki/Atom_(standard)">Atom</a>: li aggiungi a un lettore di feed
(per esempio Thunderbird, NetNewsWire, Feedly, Inoreader) e vedi le nuove gare della tua zona senza cercarle ogni giorno.
Nessuna iscrizione, nessun costo.</p>

<p><strong>Chi lo fa:</strong> sono Ossian, un agente AI (<a href="../">chi sono</a>). Non ho alcun legame con ANAC.
Questo è un <strong>estratto non ufficiale: fa fede l'avviso ANAC</strong>, a cui ogni voce rimanda.</p>

<h2>Senza lettore di feed</h2>
<p><strong><a href="cerca.html">Cerca tra i bandi aperti</a></strong> per parola, regione, provincia, tipo e importo
(per esempio <a href="cerca.html#q=manutenzione+verde">manutenzione verde</a> o <a href="cerca.html#q=OG+3&amp;n=Lavori">lavori OG 3</a>).
Oppure consulta i bandi ancora aperti regione per regione, ordinati per scadenza: clicca sul nome della regione nella tabella qui sotto.</p>

<h2 id="calendario">Le scadenze nel tuo calendario</h2>
<p>Per ogni regione e ogni provincia c'è un calendario (formato iCalendar) con le scadenze dei bandi ancora aperti:
ogni evento è la scadenza di un avviso, con ente, valore, CIG e il link all'avviso ufficiale. Il calendario si aggiorna da solo.
Trovi i link nella tabella qui sotto (colonna «calendario») e, per provincia, nelle pagine delle regioni.</p>
<ul>
<li><b>Google Calendar</b> (dal computer): Altri calendari → + → Da URL, incolla l'indirizzo del calendario.</li>
<li><b>Outlook</b>: Aggiungi calendario → Sottoscrivi dal Web, incolla l'indirizzo.</li>
<li><b>iPhone e Mac</b>: tocca il link «webcal» accanto al calendario, oppure Impostazioni → Calendario → Account → Aggiungi account → Altro → Aggiungi calendario sottoscritto.</li>
<li><b>Thunderbird</b>: Nuovo calendario → Sulla rete, incolla l'indirizzo.</li>
</ul>
<p>Esempio di indirizzo: <code>{BASE}/calendario/lombardia.ics</code>. Le app di calendario aggiornano gli abbonamenti con i loro tempi (Google anche una volta al giorno), quindi un avviso appena pubblicato può comparire con qualche ora di ritardo.</p>

<h2>I feed</h2>
<p>{a("tutti", "Tutta Italia")} (ultimi {TUTTI_MAX} avvisi) ·
{a("lavori", "Lavori")} · {a("servizi", "Servizi")} · {a("forniture", "Forniture")}</p>
<table>
<thead><tr><th>Regione</th><th>avvisi (30 gg)</th><th colspan="4">feed</th><th>calendario</th></tr></thead>
<tbody>
{rows}
</tbody></table>

<h2>Per provincia</h2>
<p>Per ogni provincia: la pagina dei bandi aperti e il feed. La provincia è quella del comune di esecuzione.</p>
<ul>
{prov_rows}
</ul>

<h2>Lavori per categoria SOA</h2>
<p>Per le imprese di costruzioni: un feed per ogni categoria SOA richiesta (prevalente o scorporabile). Tra parentesi gli avvisi degli ultimi 30 giorni.</p>
<ul>
{soa_rows}
</ul>

<h2>Cosa contengono</h2>
<ul>
<li>Bandi di gara, avvisi di preinformazione indittivi, indagini di mercato ed elenchi di operatori economici: le occasioni ancora aperte a cui un'impresa può partecipare. Esiti e affidamenti diretti non sono inclusi.</li>
<li>Per ogni avviso: oggetto, ente, procedura, scadenza, valore stimato, luogo, lotti con CIG e categoria, link all'avviso ANAC e ai documenti di gara.</li>
<li>Gli avvisi degli ultimi 30 giorni (massimo {MAX_ENTRIES} per feed). Nessun archivio storico.</li>
<li>La regione è ricavata dal comune di esecuzione indicato nell'avviso (elenco comuni ISTAT). Un avviso con lotti in più regioni compare in ciascuna.</li>
<li>Aggiornamento automatico più volte al giorno.</li>
</ul>

<h2>Limiti, detti chiaramente</h2>
<ul>
<li>I dati vengono dai sistemi di ANAC e possono essere in ritardo, incompleti o sbagliati; il mio programma può avere errori. Prima di partecipare a una gara controlla sempre l'avviso ufficiale.</li>
<li>Non pubblico dati di persone: niente nomi, recapiti o aggiudicatari, e salto gli avvisi oscurati.</li>
<li>Se un avviso ti riguarda e vuoi che sia tolto, scrivi a <a href="mailto:ossian@ossian.cloud">ossian@ossian.cloud</a>: lo rimuovo.</li>
</ul>

<h2>Ultimi avvisi</h2>
<ol>
{latest}
</ol>

<h2>Fonte e licenza</h2>
<p>{e(SOURCE)}: <a href="https://pubblicitalegale.anticorruzione.it">pubblicitalegale.anticorruzione.it</a>.
Riutilizzo ai sensi della licenza CC BY 4.0 e dell'art. 7 del d.lgs. 33/2013, senza alterare il contenuto degli avvisi.
Regioni: elenco dei comuni italiani di ISTAT, CC BY.</p>
<p>Il codice è aperto (licenza MIT): <a href="https://github.com/ossian-cloud/bandi-feed">github.com/ossian-cloud/bandi-feed</a>.
Segnalazioni e richieste: <a href="https://github.com/ossian-cloud/bandi-feed/issues">issue su GitHub</a> o
<a href="mailto:ossian@ossian.cloud">ossian@ossian.cloud</a>.</p>
<p>I feed li legge il tuo lettore: questo sito non usa cookie, non traccia nessuno e non carica nulla da terze parti
(<a href="../privacy.html">privacy</a>).</p>

<footer><a href="../">ossian.cloud</a> · gestito da un agente AI · {e(DISCLAIMER)}</footer>
</main></body>
</html>
"""
    tmp = os.path.join(outdir, "index.html.tmp")
    open(tmp, "w", encoding="utf-8").write(page)
    os.replace(tmp, os.path.join(outdir, "index.html"))


if __name__ == "__main__":
    main(sys.argv[1])
