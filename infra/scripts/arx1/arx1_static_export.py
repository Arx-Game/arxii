#!/usr/bin/env python
"""arx1_static_export.py - render the Arx I website to a static HTML tree.

DRAFT - written blind against the arxcode repo; test it against the real
sqlite snapshot before trusting the output (docs/operations/arx1-archival.md
carries the how). Runs inside the Arx I Django environment (the old box, or
anywhere the resurrection kit + db snapshot have been restored):

    cd <arx1 game dir>
    <venv>/bin/python <path>/arx1_static_export.py --out ~/arx1-site

Approach: a breadth-first crawl of the site through Django's test Client -
no running webserver, no real HTTP - logged in as a staff account so
login-gated pages (events, rosters, character sheets, lore) render with
full content. Spoilers are fine (ruling 2026-08-21: anyone with archive
access may see anything); what keeps strangers out is the basic-auth gate
on the serving side, not redaction here. GM/OOC event logs are NOT part of
the website and are not touched by this script - they live only in the
private backup tarball.

The output tree is pure static files: <path>/index.html per page, ready for
`tar | zstd` and the arx1_archive role's sync (which expects index.html at
the tarball root - pack with `tar -C ~/arx1-site -cf - . | zstd -19
--long=27 -o arx1-site-export.tar.zst`).

Stdlib + Django only - no bs4, no requests - so it runs on the old box's
venv as-is.
"""

import argparse
from collections import deque
from html.parser import HTMLParser
import os
import re
import shutil
import sys
from urllib.parse import urldefrag, urljoin, urlsplit

# Paths never worth crawling: actions, auth churn, admin, and Django's
# logout would end the crawl session. Extend as the first real run reveals
# more (the summary prints every skipped-by-rule URL).
SKIP_PATTERNS = [
    r"^/admin\b",
    r"^/logout\b",
    r"^/accounts/logout\b",
    r"^/accounts/login\b",
    r"^/admindocs\b",
    r"/delete/",
    r"/edit/",
    r"/create/",
    r"\.(?:json|csv|ics)$",
]
SKIP_RE = re.compile("|".join(SKIP_PATTERNS))

# Seed URLs. "/" alone reaches most of the site by links; the extras cover
# index pages that may only be linked from within themselves. TODO(first
# real run): confirm these against arxcode's urls.py and add any islands
# (paginated archives whose page-1 is only reachable via redirect, etc.).
DEFAULT_SEEDS = [
    "/",
    "/dominion/events/",
    "/character/",
    "/help_topics/",
    "/news/",
    "/support/faq/",
]


class LinkExtractor(HTMLParser):
    """Collect href/src attribute values from an HTML document."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value and name in ("href", "src"):
                self.links.append(value)


def url_to_relpath(path, query):
    """Map a site URL to a file path inside the static tree.

    /dominion/events/    -> dominion/events/index.html
    /dominion/events/5   -> dominion/events/5/index.html   (file_server
    serves the extensionless dir with an implicit index lookup)
    /foo/?page=2         -> foo/index__page=2.html  (links rewritten to match)
    /static/css/site.css -> static/css/site.css     (kept verbatim)
    """
    path = path.strip("/")
    last = path.rsplit("/", 1)[-1]
    if path and "." in last:
        base = path
        if query:
            stem, ext = base.rsplit(".", 1)
            return "%s__%s.%s" % (stem, sanitize(query), ext)
        return base
    base = (path + "/" if path else "") + "index"
    if query:
        return "%s__%s.html" % (base, sanitize(query))
    return base + ".html"


def sanitize(query):
    return re.sub(r"[^A-Za-z0-9=_-]", "_", query)


def rewrite_links(html, mapping):
    """Point query-string links at their exported filenames.

    Plain path links need no rewriting (the tree mirrors the URL space);
    only ?query URLs get distinct filenames, so only they are rewritten.
    """
    for (path, query), relpath in mapping.items():
        if not query:
            continue
        original = "%s?%s" % (path, query)
        html = html.replace('href="%s"' % original, 'href="/%s"' % relpath)
        html = html.replace("href='%s'" % original, "href='/%s'" % relpath)
    return html


def copy_tree(src, dst):
    """shutil.copytree without dirs_exist_ok, which needs Python 3.8+ -
    the old box's venv may predate it."""
    for root_dir, _dirs, files in os.walk(src):
        rel = os.path.relpath(root_dir, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(root_dir, name), os.path.join(target_dir, name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory for the static tree")
    parser.add_argument(
        "--settings",
        default="server.conf.settings",
        help="DJANGO_SETTINGS_MODULE (default: %(default)s)",
    )
    parser.add_argument(
        "--username", default="", help="staff account to crawl as (default: first superuser)"
    )
    parser.add_argument("--seed", action="append", default=[], help="extra seed URL(s); repeatable")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=200000,
        help="hard stop against crawler traps (default: %(default)s)",
    )
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings)
    import django

    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client

    user_model = get_user_model()
    if args.username:
        user = user_model.objects.get(username=args.username)
    else:
        user = user_model.objects.filter(is_superuser=True).order_by("pk").first()
    if user is None:
        sys.exit("no superuser found - pass --username")
    print("crawling as %s" % user.username)

    client = Client()
    client.force_login(user)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    queue = deque((seed, "") for seed in DEFAULT_SEEDS + args.seed)
    seen = set(queue)
    mapping = {}  # (path, query) -> relpath
    html_pages = {}  # relpath -> body (rewritten + written at the end)
    skipped, errors = [], []

    while queue and len(mapping) < args.max_pages:
        path, query = queue.popleft()
        target = "%s?%s" % (path, query) if query else path
        try:
            response = client.get(target, follow=True)
        except Exception as exc:  # noqa: BLE001 - a page that 500s must not kill the crawl
            errors.append((target, repr(exc)))
            continue
        if response.status_code != 200:
            errors.append((target, "HTTP %s" % response.status_code))
            continue

        relpath = url_to_relpath(path, query)
        mapping[(path, query)] = relpath
        content_type = response.get("Content-Type", "")
        body = response.content

        if "text/html" in content_type:
            html = body.decode(response.charset or "utf-8", errors="replace")
            html_pages[relpath] = html
            extractor = LinkExtractor()
            extractor.feed(html)
            for link in extractor.links:
                link, _frag = urldefrag(urljoin(path if path.endswith("/") else path + "/", link))
                parts = urlsplit(link)
                if parts.scheme or parts.netloc:  # external
                    continue
                new_path, new_query = parts.path, parts.query
                if not new_path.startswith("/") or SKIP_RE.search(new_path):
                    skipped.append(link)
                    continue
                key = (new_path, new_query)
                if key not in seen:
                    seen.add(key)
                    queue.append(key)
        else:
            full = os.path.join(out, relpath)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(body)

        if len(mapping) % 500 == 0:
            print("  %d pages exported, %d queued" % (len(mapping), len(queue)))

    for relpath, html in html_pages.items():
        full = os.path.join(out, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(rewrite_links(html, mapping))

    # Static assets straight from disk - the crawl only picks up assets a
    # page referenced; this sweeps the rest (css url() references etc.).
    for setting_name, url_prefix in (("STATIC_ROOT", "static"), ("MEDIA_ROOT", "media")):
        root = getattr(settings, setting_name, "")
        if root and os.path.isdir(root):
            dest = os.path.join(out, url_prefix)
            print("copying %s -> %s" % (root, dest))
            copy_tree(root, dest)

    print("\nexported %d pages to %s" % (len(mapping), out))
    print("errors: %d (first 20 below)" % len(errors))
    for target, err in errors[:20]:
        print("  %s -> %s" % (target, err))
    print("skipped-by-rule (sample): %s" % sorted(set(skipped))[:20])
    if not os.path.exists(os.path.join(out, "index.html")):
        sys.exit("no top-level index.html was produced - the sync script will refuse this tree")


if __name__ == "__main__":
    main()
