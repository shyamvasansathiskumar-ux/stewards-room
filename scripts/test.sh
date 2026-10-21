#!/usr/bin/env bash
# Run every test. Needs Python 3.10+; the PDF test also needs pdftotext (poppler).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest -v tests.test_all
python3 -m sr.build
