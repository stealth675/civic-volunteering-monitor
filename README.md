# civic-volunteering-monitor

Deterministisk crawler + endringsdeteksjon + LLM-annotering for kommunal/fylkeskommunal frivillighetspolitikk.

## Installasjon

```bash
pip install -e .
cp .env.example .env
```

## Kjøring

```bash
civic-monitor ingest --excel data/input/Oversikt-kommuner-fylker.xlsx
civic-monitor run --excel data/input/Oversikt-kommuner-fylker.xlsx --output data/output --max-concurrency 4
civic-monitor report --run-id 1
civic-monitor classify --run-id 1

# fallback uten entrypoint-konflikter:
python -m monitor ingest --excel data/input/Oversikt-kommuner-fylker.xlsx
```

## Hva systemet gjør

- Leser Excel med jurisdiksjoner og validerer/normaliserer URL.
- Forsøker **alle** jurisdiksjoner i hver kjøring og lager statuslinje per jurisdiksjon.
- Crawler deterministisk via robots/sitemap + faste heuristiske stier.
- Lagrer dokumenter **og relevante HTML-artikler** som snapshots med hash-basert versjonering.
- Kjør LLM kun på nye/endrede kandidater med høy relevansscore (bokmål + nynorsk søkeord).
- Genererer deknings- og funnrapporter (CSV + XLSX).

## Struktur

Se `src/monitor/` for moduler:
- `ingest`: excel + URL-normalisering
- `crawl`: fetch, sitemap, heuristikk, HTML-lenker
- `store`: sqlite-modeller, dedupe, blob-lagring
- `classify`: LLM-klient + prompt + klassifisering
- `report`: deknings- og funnrapport

## Eksempel output

Etter `civic-monitor run` får du filer i `data/output/`:
- `coverage_run_<id>.csv`
- `coverage_run_<id>.xlsx`
- `findings_run_<id>.csv`
- `findings_run_<id>.xlsx`

## How to debug empty jurisdictions

Hvis en kommune ender med `pages_fetched=0`, sjekk `coverage_run_<id>.csv` og loggene for:
- Seed-status: `base_fetch_status`, `base_fetch_error`, `base_final_url`, `robots_status`, `sitemap_status`.
- Discovery-volum: `sitemap_urls_found`, `sitemap_sitemaps_found`, `enqueued_urls_total`.
- Tidlige dropp: `dropped_before_fetch_count`, `hard_deny_dropped_count`, `drop_reasons_top3`.
- Nettverksmønster: `first_http_error_code`, `http_403_count`, `http_429_count`, `http_5xx_count`.

I logger ser du eksplisitte seed-linjer (`FETCH base_url`, `FETCH robots`, `FETCH sitemap`, `ENQUEUE ...`) og eventuelt `JURISDICTION_EMPTY reason=...` for direkte årsak.


## Time budget per domain og recency-prioritering

Crawleren bruker nå tidsbudsjett per domene (env: `DOMAIN_TIME_BUDGET_SECONDS`, default 45 sek) i stedet for hard cap på antall kandidater.
Kandidater prioriteres deterministisk med rekkefølge:
1. Recency bucket (`<=7 dager`, `<=30 dager`, `<=365 dager`, `eldre/ukjent`)
2. Relevansscore
3. URL (alfabetisk tie-breaker)

Dato-kilde for recency beregnes fra `sitemap lastmod`, HTML-meta (`article:published_time`/`datePublished`/`<time datetime>`), `Last-Modified` header, URL-datomønster, eller arvet fra parent-side for dokumentlenker.
