#!/usr/bin/env bash
set -euo pipefail

EXCEL_PATH=${1:-data/input/Oversikt-kommuner-fylker.xlsx}
civic-monitor run --excel "$EXCEL_PATH" --output data/output --max-concurrency 4
