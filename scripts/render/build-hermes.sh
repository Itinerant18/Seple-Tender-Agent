#!/usr/bin/env bash
set -euo pipefail

python -m pip install -e .
npm install --prefer-offline --no-audit
npm run build --workspace web
