"""Municipality / province name -> Italian region, from ISTAT's list of municipalities (CC BY)."""
import csv
import os
import unicodedata

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref", "comuni.csv")


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").replace("ß", "ss")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("'", " ").replace("-", " ").split())


PROV_LABEL = {}  # normalized ISTAT province name -> display name


def _load():
    by_comune, by_prov, by_code = {}, {}, {}
    with open(REF, encoding="latin-1", newline="") as f:
        rows = csv.reader(f, delimiter=";")
        next(rows)
        for r in rows:
            if len(r) < 12:
                continue
            region, prov = r[10].strip(), r[11].strip()
            # names like "Trentino-Alto Adige/Südtirol": keep the Italian part
            region, label = region.split("/")[0], prov.split("/")[0]
            for name in {r[6], r[5]}:
                by_comune.setdefault(norm(name), set()).add((region, norm(prov)))
            by_code[r[4].strip()] = norm(r[6])
            by_prov[norm(prov)] = region
            PROV_LABEL[norm(prov)] = label
    return by_comune, by_prov, by_code


_BY_COMUNE, _BY_PROV, _BY_CODE = _load()
_REGIONS = {norm(r): r for r in _BY_PROV.values()}
# PVL uses some historical/short province names
_PROV_ALIAS = {"BOLZANO": "BOLZANO/BOZEN", "AOSTA": "VALLE D AOSTA/VALLEE D AOSTE",
               "MONZA E BRIANZA": "MONZA E DELLA BRIANZA", "REGGIO EMILIA": "REGGIO NELL EMILIA", "MASSA CARRARA": "MASSA CARRARA",
               "FORLI CESENA": "FORLI CESENA", "PESARO E URBINO": "PESARO E URBINO",
               "CARBONIA IGLESIAS": "SUD SARDEGNA", "MEDIO CAMPIDANO": "SUD SARDEGNA",
               "OGLIASTRA": "NUORO", "OLBIA TEMPIO": "SASSARI"}


def place(comune, provincia):
    """-> (region, province display name), either may be None.
    PVL's "provincia" is sometimes a region name (it's a NUTS label), and its "comune" is sometimes
    an ISTAT code or a bilingual "Italiano/Deutsch" name."""
    p = norm(provincia)
    p = _PROV_ALIAS.get(p, p)
    c = (comune or "").strip()
    if c.isdigit():
        c = _BY_CODE.get(c[-6:].zfill(6), c)
    hits = _BY_COMUNE.get(norm(c), set())
    for part in c.split("/") if not hits else []:
        hits = hits or _BY_COMUNE.get(norm(part), set())
    if p in _REGIONS:
        in_reg = {h for h in hits if h[0] == _REGIONS[p]}
        if len(in_reg) == 1:
            r, pr = next(iter(in_reg))
            return r, PROV_LABEL[pr]
        return _REGIONS[p], None
    if len(hits) > 1 and p:
        hits = {h for h in hits if h[1] == p or h[1].startswith(p)} or hits
    if len(hits) == 1:
        r, pr = next(iter(hits))
        return r, PROV_LABEL[pr]
    if p in _BY_PROV:
        return _BY_PROV[p], PROV_LABEL[p]
    regions = {r for r, _ in hits}
    return (regions.pop() if len(regions) == 1 else None), None


def region(comune, provincia):
    return place(comune, provincia)[0]
