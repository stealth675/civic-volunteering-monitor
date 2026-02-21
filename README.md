# civic-volunteering-monitor

Deterministisk crawler + endringsdeteksjon + LLM-annotering for kommunal/fylkeskommunal frivillighetspolitikk.

## Installasjon

```bash
pip install -e .
cp .env.example .env
```

## Kjøring

```bash
monitor ingest --excel data/input/Oversikt-kommuner-fylker.xlsx
monitor run --excel data/input/Oversikt-kommuner-fylker.xlsx --output data/output --max-concurrency 4
monitor report --run-id 1
monitor classify --run-id 1
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

Etter `monitor run` får du filer i `data/output/`:
- `coverage_run_<id>.csv`
- `coverage_run_<id>.xlsx`
- `findings_run_<id>.csv`
- `findings_run_<id>.xlsx`
