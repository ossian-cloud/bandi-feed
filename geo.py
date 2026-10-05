"""Municipality / province name -> Italian region, from ISTAT's list of municipalities (CC BY)."""
import csv
import os
import unicodedata

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref", "comuni.csv")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("'", " ").replace("-", " ").split())


def _load():
    by_comune, by_prov = {}, {}
    with open(REF, encoding="latin-1", newline="") as f:
        rows = csv.reader(f, delimiter=";")
        next(rows)
        for r in rows:
            if len(r) < 12:
                continue
            region, prov = r[10].strip(), r[11].strip()
            # region names like "Trentino-Alto Adige/Südtirol": keep the Italian part
            region = region.split("/")[0]
            for name in {r[6], r[5]}:
                by_comune.setdefault(norm(name), set()).add((region, norm(prov)))
            by_prov[norm(prov)] = region
    return by_comune, by_prov


_BY_COMUNE, _BY_PROV = _load()
# PVL uses some historical/short province names
_PROV_ALIAS = {"BOLZANO": "BOLZANO/BOZEN", "AOSTA": "VALLE D AOSTA/VALLEE D AOSTE",
               "MONZA E BRIANZA": "MONZA E DELLA BRIANZA", "REGGIO EMILIA": "REGGIO NELL EMILIA", "MASSA CARRARA": "MASSA CARRARA",
               "FORLI CESENA": "FORLI CESENA", "PESARO E URBINO": "PESARO E URBINO",
               "CARBONIA IGLESIAS": "SUD SARDEGNA", "MEDIO CAMPIDANO": "SUD SARDEGNA",
               "OGLIASTRA": "NUORO", "OLBIA TEMPIO": "SASSARI"}


def region(comune, provincia):
    p = norm(provincia)
    p = _PROV_ALIAS.get(p, p)
    hits = _BY_COMUNE.get(norm(comune), set())
    if len(hits) == 1:
        return next(iter(hits))[0]
    if len(hits) > 1 and p:
        regions = {r for r, pr in hits if pr == p or pr.startswith(p)}
        if len(regions) == 1:
            return regions.pop()
    if p in _BY_PROV:
        return _BY_PROV[p]
    return None
