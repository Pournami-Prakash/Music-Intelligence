#!/bin/bash
# Long-running compute jobs meant to run unattended.
# Logs go to /tmp/overnight.log. Run from the project root.
set -e
cd "$(dirname "$0")"

echo "=== UMAP full projection ===" | tee -a /tmp/overnight.log
.venv/bin/python3 src/embeddings/project_umap.py >> /tmp/overnight.log 2>&1

echo "=== Rebuild artist_stats ===" | tee -a /tmp/overnight.log
.venv/bin/python3 src/compute/compute_artist_stats.py >> /tmp/overnight.log 2>&1

echo "=== Release dates ===" | tee -a /tmp/overnight.log
.venv/bin/python3 src/compute/compute_release_dates.py >> /tmp/overnight.log 2>&1

echo "=== ALL DONE ===" | tee -a /tmp/overnight.log
