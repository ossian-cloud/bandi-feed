# Reading ANAC's Pubblicità Legale (PVL) platform: field notes

These are my notes on how the PVL web application at https://pubblicitalegale.anticorruzione.it fetches its data,
written so that others who want the daily notices don't have to work it out again.

**This is not an official API.** ANAC doesn't document or announce it. I worked it out from the platform's own
web application in October 2026, and it may change without notice. There is no real robots.txt (the path returns
the application shell). Be polite: one request every few seconds, an honest User-Agent with a contact, and stop
on 401/403/429. `fetch.py` in this repository does exactly that and is the reference for what works today.
Licence: the PVL states none of its own. ANAC's site-wide copyright notice (https://www.anticorruzione.it/copyright)
says its data are CC BY 4.0, with the source and, where possible, the page URL cited.

## Endpoints

Base `https://pubblicitalegale.anticorruzione.it/api/v0`. All GET, JSON, no authentication. Dates are `dd/MM/yyyy`.

| endpoint | what it gives |
|---|---|
| `/date` | the latest publication days, newest first (weekends and holidays are absent) |
| `/map` | `templateSchedeMapping`: notice code (`codiceScheda`) to template number and category |
| `/avvisi` | notices of a day range, plain paging (`page`, `size`, response has `totalPages`, `totalElements`, `content`) |
| `/avvisi/{idAvviso}` | one notice |
| `/avvisi-full-text-specializzata` | the "ricerca specializzata" search: `cpv`, `sa` (body's tax code, digits only), token paging |

**The route I use** (`fetch.py`): `/avvisi?dataPubblicazioneStart=D&dataPubblicazioneEnd=D&codiceScheda=2,4,5a,5b,6&page=N&size=200`.
`codiceScheda` here takes **template numbers**, comma-separated. On the search endpoint, `page=N` is unreliable
(page 1 returned almost the same items as page 0): use `tokenPaginazione` with `direzionePaginazione=AVANTI`,
or one large `pageSize` (5000 returned a whole weekday, ~13 MB). There, `codiceScheda` and `tipologia` are
silently ignored.

## Volume

About 4,500 notices on a weekday (2 Oct 2026: 4,510). 3,633 of them were direct awards under threshold (`AD3`),
132 were calls for tender (templates 2 and 4). Notices carry `dataPubblicazione` at 06:00 UTC of their day.

## Templates (from `/map`)

| template | category | type |
|---|---|---|
| 1 | ALTRI_AVVISI | pre-information, informative |
| 2 | BANDI_DI_GARA | pre-information that opens a competition |
| 3 | ALTRI_AVVISI | qualification systems |
| 4 | BANDI_DI_GARA | calls for tender |
| 5a / 5b | ALTRI_AVVISI | market surveys (above / below threshold) |
| 6 | ALTRI_AVVISI | supplier lists |
| 7 | ESITI_DI_GARA | results |
| 8a | ESITI_DI_GARA | direct awards below threshold (`AD3`, `ABI`) |
| 8b | ALTRI_AVVISI | in-house awards |
| 9 | ESITI_DI_GARA | notices of intended direct award |
| 10 | ALTRI_AVVISI | contract modifications |

The category also picks the public page: `/bandi/{idAvviso}`, `/esiti/{idAvviso}` or `/avvisi/{idAvviso}`.

## Shape of a notice

Top level: `idAvviso` (UUID, the key), `idAppalto` (groups the notices of one procurement: call, correction, result),
`codiceScheda`, `dataPubblicazione`, `dataScadenza` (deadline, calls only; sometimes null while the lots in SEZ. C carry
`termine_ricezione` or `termine_invito`, either a bare date with offset like `2026-11-12+01:00` or a date-time), `tipo` (`avviso` or `rettifica`),
`attivo`, `oscurato`, `templates[]`.

`T = templates[0].template` always has three sections; find them by name rather than position:
- `SEZ. A - Committente`: `fields.soggetti_sa[]` with `codice_fiscale` and `denominazione_amministrazione`.
- `SEZ. B - Dati Generali`: `tipo_procedura_aggiudicazione`, `documenti_di_gara_link` (the body's e-procurement portal).
- `SEZ. C - Oggetto`: `items[]`, one per lot (iterate: 11,870 items for 4,510 notices). Each has `cig`, `descrizione`,
  `natura_principale`, `cpv` (an **Italian text label, not the code**: map it with a label table such as `ref/cpv_it.json`),
  `valore_complessivo_stimato` (calls) / `valore_offerta_vincente` (results) / `valore_affidamento` (direct awards),
  `luogo_istat` (municipality name in capitals), `categorie[]` (SOA classes), `termine_ricezione`.

`T.metadata.descrizione` is the object; `T.metadata.link_eform_ted` links TED for EU-level calls.

## Things that bit me

- **Notices change after publication.** ANAC deactivates or obscures some days later (`attivo: false`, `oscurato: true`).
  A full re-check of 30 days on 16 Oct 2026 removed 74 of 3,287 stored notices. Re-fetch recent days, not only today.
- Corrections (`tipo: rettifica`) are separate notices with the same `idAppalto`: keep the newest notice per procurement.
- Sometimes the object is only a pointer ("Si veda documentazione di gara"); the title (`T.metadata.titolo`) may be better.
- An empty answer for a day you already hold notices of is more likely a glitch than a mass withdrawal: don't delete on it.
- **Personal data.** In results and direct awards, winners (`aggiudicatari[]`, `aggiudicatari_ad[]`) include sole
  traders and professionals: a 16-character personal tax code and a full name. Leave them out unless you have a lawful
  reason to republish them. Contracting bodies' 11-digit tax codes are fine.
- Procedures without a published call (e.g. negotiated without a call) never appear as calls; direct awards appear
  only as award notices.
