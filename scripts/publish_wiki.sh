#!/usr/bin/env bash
# Publish the OKF wiki: validate .wiki/ strictly, then render it to a single
# self-contained HTML page under site/wiki/, ready to serve (e.g. GitHub Pages).
# Usage: scripts/publish_wiki.sh [output-dir]   (default: site/wiki)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$root/site/wiki}"
skills="$root/.agents/skills"

if [ ! -d "$root/.wiki" ]; then
  echo "error: $root/.wiki not found" >&2
  exit 1
fi

echo "Validating .wiki ..."
uv run "$skills/wiki-okf-validate/scripts/okf_validate.py" "$root/.wiki" --strict

echo "Rendering ..."
mkdir -p "$out"
uv run "$skills/wiki-okf-visualize/scripts/okf_visualize.py" "$root/.wiki" \
  --title "Invoice extraction pipeline" -o "$out/index.html"

echo "Published to $out/index.html"
