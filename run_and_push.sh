#!/bin/bash
# Lancers Scout — run scraper and push results to GitHub Pages
set -e

cd /Users/shotainoue/Code/lancers-scout

# Load .env
export $(grep -v '^#' .env | xargs)

python3 main.py \
  --pages 2 \
  --detail \
  --propose \
  --propose-top 10 \
  --output docs/results.json

git add docs/results.json
git diff --cached --quiet || git commit -m "chore: update results $(date '+%Y-%m-%d %H:%M JST')"
git push
