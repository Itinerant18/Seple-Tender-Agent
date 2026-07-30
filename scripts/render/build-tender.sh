#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.custom.txt
python -m playwright install chromium
