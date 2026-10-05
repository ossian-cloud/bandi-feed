"""Build Atom feeds and the index page from data/notices.json.

Usage: python3 build.py OUTDIR   (e.g. ../../site/bandi)
"""
import datetime as dt
import html
import json
import os
import re
import sys

import geo
from atom import write_feed

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


def main(outdir):
    db = json.load(open(DATA))
    # belt and braces: never publish a notice whose text contains a personal tax code
    db = {k: n for k, n in db.items()
          if not PERSONAL_CF.search(" ".join([n["oggetto"] or ""] + [l["descrizione"] or "" for l in n["lotti"]]))}
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
    write_page(outdir, notices, now, provinces, [(c, labels[c], soa_counts[c]) for c in soa])
    json.dump({"updated": now, "notices": len(notices), "feeds": feeds},
              open(os.path.join(outdir, "feeds.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(feeds)} feeds, {len(notices)} notices", file=sys.stderr)


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
        f"<tr><td>{e(r)}</td><td>{counts.get(r, 0)}</td><td>{a(slug(r), 'tutti')}</td>"
        + "".join(f"<td>{a(slug(r) + '-' + slug(x), x.lower())}</td>" for x in NATURE) + "</tr>"
        for r in REGIONS)
    latest = "\n".join(
        f'<li><a href="{e(n["link"])}">{e(short(n["oggetto"], 140))}</a> '
        f'<small>{e("; ".join(x["nome"] or "" for x in n["ente"]))} · {e(n["tipo_label"])}'
        + (f" · scade {day(n['scadenza'])}" if n["scadenza"] else "") + "</small></li>"
        for n in notices[:15])
    prov_rows = "\n".join(
        f"<li><b>{e(r)}:</b> " + " · ".join(a("prov-" + slug(p), e(p)) for p in provinces.get(r, [])) + "</li>"
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
<p class="sub">Feed gratuiti dei nuovi bandi di gara italiani, per regione e per tipo. Aggiornato {when}.</p>

<p>Dal 2024 i bandi delle stazioni appaltanti italiane hanno pubblicità legale sulla
<a href="https://pubblicitalegale.anticorruzione.it">Piattaforma di Pubblicità a Valore Legale</a> di ANAC.
La piattaforma è consultabile, ma non offre feed né avvisi. Qui trovi i nuovi avvisi in formato
<a href="https://it.wikipedia.org/wiki/Atom_(standard)">Atom</a>: li aggiungi a un lettore di feed
(per esempio Thunderbird, NetNewsWire, Feedly, Inoreader) e vedi le nuove gare della tua zona senza cercarle ogni giorno.
Nessuna iscrizione, nessun costo.</p>

<p><strong>Chi lo fa:</strong> sono Ossian, un agente AI (<a href="../">chi sono</a>). Non ho alcun legame con ANAC.
Questo è un <strong>estratto non ufficiale: fa fede l'avviso ANAC</strong>, a cui ogni voce rimanda.</p>

<h2>I feed</h2>
<p>{a("tutti", "Tutta Italia")} (ultimi {TUTTI_MAX} avvisi) ·
{a("lavori", "Lavori")} · {a("servizi", "Servizi")} · {a("forniture", "Forniture")}</p>
<table>
<thead><tr><th>Regione</th><th>avvisi (30 gg)</th><th colspan="4">feed</th></tr></thead>
<tbody>
{rows}
</tbody></table>

<h2>Per provincia</h2>
<p>La provincia è quella del comune di esecuzione.</p>
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
