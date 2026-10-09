"""Readable titles for notice pages. ANAC objects are often 150+ characters, half of them in capitals, and
open with procedural boilerplate ("Procedura aperta ai sensi dell'art. 71 del D.Lgs. 36/2023 per l'affidamento
del..."), so what a search result shows is the boilerplate. These helpers only reformat the official text:
they drop the boilerplate in front of the real object and fix the case. They never add words."""
import re

SMALL = {"di", "del", "della", "dei", "delle", "degli", "dello", "dell", "e", "ed", "per", "a", "al", "alla", "ai",
         "alle", "in", "da", "dal", "con", "su", "sul", "sulla", "nel", "nella", "il", "la", "lo", "le", "gli", "i", "un", "una", "d", "l"}
# Where the real object usually starts once the boilerplate is gone.
CORE = (r"servizi[oa]?|fornitur[ae]|lavori|accordo quadro|concession[ei]|noleggio|progettazione|manutenzione|"
        r"gestione|realizzazione|acquisto|acquisizione|polizz[ae]|copertur[ae] assicurativ[ae]|"
        r"intervent[oi]|opere|incaric[oh]i?|costruzione|ristrutturazione|riqualificazione|"
        r"locazione|vendita|alienazione|individuazione|istituzione|formazione|aggiornamento|trasporto")
OPENER = re.compile(r"^(procedura|gara|affidamento|bando|avviso|per\b|indagine|rdo|richiesta|appalto|"
                    r"accordo quadro\b.{0,40}\bper\b)", re.I)
LAW = re.compile(r"\s*[,(]?\s*(ai sensi|ex art|ex artt|ex\. art|sensi dell|di cui all|secondo quanto previsto)"
                 r"[^(]{0,160}?(d\.?\s?lgs\.?\s*(n\.?\s*)?\d+\s*(/|del)\s*[\d.]*\d{4}|codice( dei contratti)?)"
                 r"(\s*e\s*s\.?m\.?i\.?|\s*e\s*ss\.?\s*mm\.?\s*i*\.?\s*ii\.?)?\s*\)?,?", re.I)
TAIL = re.compile(r"\s*[-–—,.(]*\s*\b(CUP|CIG|CUI|CPV)\b\s*[:n.°]*\s*[A-Z0-9].*$")
CODE = re.compile(r"^(\(\s*[\w./-]+\s*\)|[A-Za-z]*\d[\w./-]*?|(bando|rda|rdo)\s+n?°?\s*[A-Z]*\d[\w./-]*\.?)[\s_:–-]+(?=\S)", re.I)


def upperish(s):
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) > 0.6 * len(letters)


def sentence_case(s):
    """Lower-case a shouting text, keeping things that look like codes or acronyms with dots (S.P.A., D.LGS.)."""
    if not upperish(s):
        return s[:1].upper() + s[1:]
    out = []
    for w in re.split(r"(\s+)", s):
        core = w.strip("“”\"'’(),;:.")
        keep = (any(c.isdigit() for c in core) and any(c.isalpha() for c in core)) or re.fullmatch(r"([A-Z]\.){2,}[A-Z]?\.?", core)
        out.append(w if keep else w.lower())
    s = "".join(out)
    i = next((i for i, c in enumerate(s) if c.isalpha()), 0)
    return s[:i] + s[i:i + 1].upper() + s[i + 1:]


def name_case(s):
    """'COMUNE DI SAN GREGORIO MAGNO' -> 'Comune di San Gregorio Magno'; mixed-case names are left alone."""
    if not upperish(s):
        return s
    words = re.split(r"(\s+|-|/|['’])", s)
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if not w.strip() or w in "-/'’":
            out.append(w)
        elif "." in w or (any(c.isdigit() for c in w)) or w in ("SPA", "SRL", "SCARL", "ASL", "ASP", "AOU", "ATS", "ASST", "INPS", "INAIL", "ANAS", "RFI", "ATER", "IPAB", "CUC", "SUA", "ARPA", "ACI", "AUSL", "ULSS", "ASM", "ACP"):
            out.append(w)
        elif lw in SMALL and i > 0:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return "".join(out)


def core_object(oggetto, ente=""):
    """The object without codes, the ente's own name, procedural boilerplate, legal references and CUP/CIG tails."""
    s = " ".join((oggetto or "").replace("`", "'").split()).strip(" -–")
    for _ in range(2):
        s = CODE.sub("", s, count=1).strip()
    if ente and s.upper().startswith(ente.upper()):
        s = s[len(ente):].lstrip(" -–:,.")
    s = LAW.sub(" ", s)
    s = TAIL.sub("", s)
    if not re.match(rf"({CORE})\b", s, re.I):
        o = OPENER.match(s) or re.search(r"\b(procedura|gara|affidamento)\b", s[:100], re.I)
        m = o and re.search(rf"\b({CORE})\b", s[o.start() + 1:], re.I)
        if m and m.start() < 260:
            s = s[o.start() + 1 + m.start():]
    s = " ".join(re.sub(r"[“”\"«»]", "", s).split()).strip(" -–,.;:")
    return s or " ".join((oggetto or "").split())


def cut(s, n):
    """At most n characters, at a word boundary, without a dangling preposition or punctuation."""
    if len(s) <= n:
        return s
    words = s[:n].split()[:-1] if not s[n:n + 1].isspace() else s[:n].split()
    while words and (words[-1].lower().strip("'’") in SMALL or words[-1] in "-–,"):
        words.pop()
    return " ".join(words).rstrip(",;:-–(") + "…"


def short_ente(ente):
    """A short, readable name of the contracting body for titles."""
    e = ente.split(";")[0].strip()
    if " - " in e and len(e) > 40:
        e = e.split(" - ")[0]
    e = re.sub(r"\s*(SOCIETA'|SOCIETÀ|società)\s+PER\s+AZIONI\b|\s+S\.?P\.?A\.?$|\s+S\.?R\.?L\.?$|\s+SCARL$", "", e, flags=re.I).strip(" ,-")
    return name_case(e)


BUYER = re.compile(r"^comune di ([^()\-–:.,]{2,40}?)\s*(\([A-Z]{2}\))?\s*[-–:.]\s*", re.I)


def notice_title(oggetto, ente, place="", limit=78):
    """'{object} - {ente}, {place}', within about limit characters; the object gives way first.
    A central purchasing body buying for a town usually starts the object with 'COMUNE DI X -': then the
    town is the more useful name."""
    who = short_ente(ente)
    place = place.split("/")[0]  # South Tyrol: 'Appiano Sulla Strada del Vino/Eppan An Der Weinstrasse'
    m = BUYER.match(core_object(oggetto, ente))
    if m and not who.lower().startswith("comune"):
        who, oggetto, ente = name_case("COMUNE DI " + m.group(1).upper()), core_object(oggetto, ente)[m.end():], ""
    place = place if place and place.lower() not in who.lower() else ""
    room = 40 if not place else max(22, 46 - len(place))
    if len(who) > room:
        who = cut(who, room)
    if place:
        who += ", " + place
    obj = sentence_case(core_object(oggetto, ente))
    room = max(40, limit - len(who) - 3)
    return f"{cut(obj, room)} - {who}"
