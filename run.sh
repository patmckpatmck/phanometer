#!/bin/bash
# Phan-o-meter daily run — mirrors HR Scout pattern.
# Usage: ./run.sh

set -e

# Load env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Run the daily job
python phanometer.py

# Commit + push (triggers Vercel redeploy)
git add data/
if git diff --staged --quiet; then
  echo "No data changes — skipping commit."
else
  git commit -m "Daily Phan-o-meter update $(date +%Y-%m-%d)"
  git push
fi
