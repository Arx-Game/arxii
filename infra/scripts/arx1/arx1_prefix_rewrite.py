#!/usr/bin/env python3
"""Re-point the Arx I static export's root-relative links at a URL prefix.

#3320 / ADR-0232 moved the archive off its own subdomain onto a path on the Arx
II web vhost, so that Arx II's host-only session cookie reaches it. The export
was crawled from a site served at a host ROOT, and arx1_static_export.py leans
on that: "plain path links need no rewriting (the tree mirrors the URL space)".
Under a prefix that stops being true - every ``href="/lore/"`` would leave the
archive for the Arx II SPA, and every ``src="/static/..."`` would pull Arx II's
own collected static instead of Arx I's.

This walks the installed tree and rewrites those attributes in place. Run by
roles/arx1_archive's sync script after extraction, before the tree is swapped
into the web root.

Deliberately narrow:

* Only root-relative values are touched. Relative links already resolve
  correctly under a prefix, and absolute/protocol-relative ones point off-site.
* Already-prefixed values are left alone, so a re-run is a no-op. The sync is
  documented as safe to re-run, and a second pass must not double the prefix.

Usage:
    arx1_prefix_rewrite.py <tree> <prefix>
    arx1_prefix_rewrite.py --self-test
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

# Attributes whose values are URLs the browser resolves against the page.
# ``action`` is included for completeness even though a static export has no
# working forms - a form posting to "/" would otherwise hit the Arx II SPA.
_ATTR_RE = re.compile(r"""(?P<head>\b(?:href|src|action)\s*=\s*(?P<q>["']))/(?P<rest>[^"']*)""")

# url(/...) inside stylesheets and inline <style> blocks.
_CSS_URL_RE = re.compile(r"""(?P<head>url\(\s*(?P<q>["']?))/(?P<rest>(?![/"'])[^)"']*)""")

HTML_SUFFIXES = frozenset({".html", ".htm"})
CSS_SUFFIXES = frozenset({".css"})

# argv shapes: ["prog", SELF_TEST_FLAG] and ["prog", <tree>, <prefix>].
SELF_TEST_FLAG = "--self-test"
_SELF_TEST_ARGC = 2
_REWRITE_ARGC = 3


def rewrite(text: str, prefix: str) -> str:
    """Return ``text`` with root-relative URLs re-pointed under ``prefix``.

    ``prefix`` is an absolute path with no trailing slash, e.g. ``/arxmush-archive``.
    """
    prefix = "/" + prefix.strip("/")
    already = prefix.lstrip("/")

    def _sub(match: re.Match[str]) -> str:
        rest = match.group("rest")
        # "//host/path" is protocol-relative, i.e. off-site. Leave it.
        if rest.startswith("/"):
            return match.group(0)
        # Idempotence: "/arxmush-archive" and "/arxmush-archive/..." are done.
        if rest == already or rest.startswith(already + "/"):
            return match.group(0)
        return f"{match.group('head')}{prefix}/{rest}"

    return _CSS_URL_RE.sub(_sub, _ATTR_RE.sub(_sub, text))


def rewrite_tree(root: Path, prefix: str) -> int:
    """Rewrite every HTML and CSS file under ``root``. Returns the file count."""
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in HTML_SUFFIXES and suffix not in CSS_SUFFIXES:
            continue
        # The Arx I export is latin-1-safe at worst; never fail a whole sync
        # over one page's stray byte.
        original = path.read_text(encoding="utf-8", errors="surrogateescape")
        updated = rewrite(original, prefix)
        if updated != original:
            path.write_text(updated, encoding="utf-8", errors="surrogateescape")
            changed += 1
    return changed


class SelfTestFailure(Exception):
    """A self-test case did not hold."""


def _expect(got: str, expected: str, label: str) -> None:
    """Explicit raise rather than ``assert``: this runs as a script, not pytest."""
    if got != expected:
        msg = f"{label}: got {got!r}, expected {expected!r}"
        raise SelfTestFailure(msg)


def _self_test() -> None:
    """The contract this file carries, so CI can check it without a test harness."""
    p = "/arxmush-archive"
    cases = [
        # The three shapes arx1_static_export.py actually emits.
        ("<a href='/lore/'>x</a>", "<a href='/arxmush-archive/lore/'>x</a>"),
        ("<a href='/'>home</a>", "<a href='/arxmush-archive/'>home</a>"),
        ('<link href="/static/a.css">', '<link href="/arxmush-archive/static/a.css">'),
        ('<img src="/media/x.png">', '<img src="/arxmush-archive/media/x.png">'),
        # Relative links already resolve correctly; do not touch them.
        ('<a href="page-2/">next</a>', '<a href="page-2/">next</a>'),
        ('<a href="index__page=2.html">n</a>', '<a href="index__page=2.html">n</a>'),
        # Off-site links must survive untouched.
        ('<a href="https://example.com/">x</a>', '<a href="https://example.com/">x</a>'),
        ('<a href="//cdn.example/x.js">x</a>', '<a href="//cdn.example/x.js">x</a>'),
        # Fragment- and query-only links have no leading slash at all.
        ('<a href="?page=2">x</a>', '<a href="?page=2">x</a>'),
        ('<a href="#clue-3">x</a>', '<a href="#clue-3">x</a>'),
        # CSS url() forms.
        ("body{background:url(/img/bg.png)}", "body{background:url(/arxmush-archive/img/bg.png)}"),
        ('a{background:url("/i.png")}', 'a{background:url("/arxmush-archive/i.png")}'),
        ("a{background:url(//cdn/i.png)}", "a{background:url(//cdn/i.png)}"),
        # Forms, for completeness.
        ('<form action="/search/">', '<form action="/arxmush-archive/search/">'),
    ]
    for source, expected in cases:
        _expect(rewrite(source, p), expected, source)

    # Idempotence: the sync is documented as safe to re-run, so a second pass
    # must not stack a second prefix on.
    once = rewrite("<a href='/lore/'>x</a><a href='/'>h</a>", p)
    _expect(rewrite(once, p), once, "second pass must be a no-op")

    # A trailing slash on the prefix must not produce a doubled slash.
    _expect(
        rewrite("<a href='/lore/'>x</a>", "/arxmush-archive/"),
        "<a href='/arxmush-archive/lore/'>x</a>",
        "trailing slash on prefix",
    )
    print("arx1_prefix_rewrite self-test: OK")


def main(argv: list[str]) -> int:
    if len(argv) == _SELF_TEST_ARGC and argv[1] == SELF_TEST_FLAG:
        _self_test()
        return 0
    if len(argv) != _REWRITE_ARGC:
        print(__doc__, file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    changed = rewrite_tree(root, argv[2])
    print(f"arx1 archive: re-pointed root-relative links in {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
