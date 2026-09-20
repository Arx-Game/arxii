#!/usr/bin/env python3
"""Check relative Markdown links in the ADR directory."""

from pathlib import Path
import re
import sys

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def main() -> int:
    """Return non-zero when an ADR contains a broken relative Markdown link."""
    root = Path("docs/adr")
    broken: list[tuple[Path, str]] = []
    adr_files = sorted(source for source in root.glob("*.md") if source.name != "README.md")
    for source in adr_files:
        for target in LINK_RE.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("#", "/", "http://", "https://", "mailto:")):
                continue
            target_path = (source.parent / target.split("#", 1)[0]).resolve()
            if not target_path.exists():
                broken.append((source, target))

    if broken:
        for source, target in broken:
            print(f"{source}: broken link: {target}", file=sys.stderr)
        return 1

    print(f"Checked {len(adr_files)} ADR files: all relative links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
