#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Flatten an OKF bundle into GitHub Wiki pages.

GitHub wikis are a flat git repo of Markdown files whose names are the page
names. This maps every concept to one page (`decisions/0001-x.md` becomes
`decisions-0001-x`), rewrites bundle links to page links, drops the YAML
frontmatter, and writes `Home.md` and `_Sidebar.md` from the root index.

Usage: okf_to_github_wiki.py <bundle> <out-dir>
"""

from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path

LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+?\.md)(#[^)]*)?\)")
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def page_name(rel: str) -> str:
    """Return the wiki page name for a bundle-relative path like `a/b.md`."""
    if rel == "index.md":
        return "Home"
    stem = rel[:-3]
    if stem.endswith("/index"):
        stem = stem[: -len("/index")] + "-index"
    return stem.replace("/", "-")


def rewrite(text: str, rel: str, pages: set[str]) -> str:
    """Point bundle links at wiki pages; leave unknown links untouched."""

    def sub(m: re.Match[str]) -> str:
        label, target, anchor = m.group(1), m.group(2), m.group(3) or ""
        if "://" in target:
            return m.group(0)
        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
        if resolved not in pages:
            return label
        return f"[{label}]({page_name(resolved)}{anchor})"

    return LINK.sub(sub, text)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    bundle, out = Path(argv[1]), Path(argv[2])
    if not bundle.is_dir():
        print(f"error: {bundle} is not a directory", file=sys.stderr)
        return 1
    files = sorted(p for p in bundle.rglob("*.md") if p.name != "log.md")
    rels = {p.relative_to(bundle).as_posix(): p for p in files}
    pages = set(rels)

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()

    for rel, path in rels.items():
        text = path.read_text(encoding="utf-8")
        m = FRONT.match(text)
        title = None
        if m:
            t = re.search(r'^title:\s*"?(.*?)"?\s*$', m.group(1), re.M)
            title = t.group(1) if t else None
            text = text[m.end() :].lstrip("\n")
        body = rewrite(text, rel, pages)
        if rel != "index.md" and not body.startswith("# ") and title:
            body = f"# {title}\n\n{body}"
        (out / f"{page_name(rel)}.md").write_text(body, encoding="utf-8")

    home = (out / "Home.md").read_text(encoding="utf-8")
    links = re.findall(r"^\* \[[^\]]+\]\([^)]+\)", home, re.M)
    (out / "_Sidebar.md").write_text(
        "**Project knowledge**\n\n" + "\n".join(links) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rels)} pages to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
