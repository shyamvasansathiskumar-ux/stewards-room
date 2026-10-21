#!/usr/bin/env bash
# Fetch the latest FIA documents for one season, read the decisions, rebuild the site data.
# Usage: bash scripts/update.sh 2026
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m sr.fetch --season "${1:-2026}" --pdfs
python3 -m sr.build
