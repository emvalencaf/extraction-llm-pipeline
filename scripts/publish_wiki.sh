#!/usr/bin/env bash
# Publish the OKF wiki in .wiki/:
#   1. validate it strictly (wiki-okf-validate);
#   2. render a self-contained HTML graph to site/wiki/index.html;
#   3. flatten it into GitHub Wiki pages in site/github-wiki/;
#   4. with --push, commit and push those pages to the repo's GitHub Wiki.
# The GitHub Wiki must be enabled and have one page (create it once in the UI).
# Usage: scripts/publish_wiki.sh [--push]
set -euo pipefail

push=0
case "${1:-}" in
  "") ;;
  --push) push=1 ;;
  *) echo "usage: $0 [--push]" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills="$root/.agents/skills"
html="$root/site/wiki"
pages="$root/site/github-wiki"

[ -d "$root/.wiki" ] || { echo "error: $root/.wiki not found" >&2; exit 1; }

echo "Validating .wiki ..."
uv run "$skills/wiki-okf-validate/scripts/okf_validate.py" "$root/.wiki" --strict

echo "Rendering HTML ..."
mkdir -p "$html"
uv run "$skills/wiki-okf-visualize/scripts/okf_visualize.py" "$root/.wiki" \
  --title "Invoice extraction pipeline" -o "$html/index.html"

echo "Building GitHub Wiki pages ..."
uv run "$root/scripts/okf_to_github_wiki.py" "$root/.wiki" "$pages"

if [ "$push" -eq 0 ]; then
  echo "Built $pages (dry run). Re-run with --push to publish to the GitHub Wiki."
  exit 0
fi

url="$(git -C "$root" remote get-url origin)"
url="${url%.git}.wiki.git"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git clone --quiet "$url" "$tmp" || {
  echo "error: cannot clone $url; enable the Wiki in Settings and create its first page" >&2
  exit 1
}
find "$tmp" -maxdepth 1 -name '*.md' -delete
cp "$pages"/*.md "$tmp"/
git -C "$tmp" add -A
if git -C "$tmp" diff --cached --quiet; then
  echo "GitHub Wiki already up to date."
  exit 0
fi
git -C "$tmp" commit --quiet -m "Sync wiki from $(git -C "$root" rev-parse --short HEAD)"
git -C "$tmp" push --quiet
echo "Pushed to $url"
