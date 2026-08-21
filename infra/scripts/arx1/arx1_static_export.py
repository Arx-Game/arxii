#!/usr/bin/env python
"""arx1_static_export.py - render the Arx I website to a static HTML tree.

DRAFT - seeds and skip rules were written against arxcode's actual urls.py
files (web/urls.py, web/character/urls.py, world/msgs/urls.py,
world/dominion/urls.py as of 2026-08), but test a run against the real
sqlite snapshot before trusting the output. Runs inside the Arx I Django
environment (the old box, or anywhere the resurrection kit + db snapshot
have been restored):

    cd <arx1 game dir>
    <venv>/bin/python <path>/arx1_static_export.py --out ~/arx1-site

Approach: a breadth-first crawl of the site through Django's test Client -
no running webserver, no real HTTP - logged in as a chosen account so
login-gated pages render. Coverage includes the big lore surfaces:

  - rosters + character sheets (/character/active/ ... /character/gone/),
    and for EVERY discovered sheet the exporter force-enqueues the
    known sub-pages (story, actions/, clues/, gallery, scenes) rather than
    trusting the sheet template to link them all
  - actions: /character/sheet/<id>/actions/ list + per-action detail pages
  - journals: /comms/journals/list/ (paginated, 20/entry pages; entries
    render inline in the list - there is no per-journal detail URL)
  - events (/dom/cal/list/ + display pages), crises, boards
    (/comms/boards/), help topics, news

Crawl as a STAFF account (the default: first superuser). Ruled 2026-08-21:
everything written with the intent of being read by staff belongs in the
archive - black journals, secrets, clues, GM notes included (all were
always staff-viewable and known to be). The staff journal list contains
every black journal because a fresh account has read nothing, so its
"unread" list IS the full permitted set. The privacy boundary - messengers,
player-to-player IC mail staff was never meant to read - cannot leak in:
messengers have no web view in arxcode (model + telnet handler + Django
admin only, and /admin is skipped).

Runtime expectation for ~6 years of data: tens of thousands to ~150k pages
at roughly 100-500ms each through the test client = several hours to
overnight, single-threaded. The exporter therefore streams every page to
disk immediately (constant memory) and supports --resume, which re-parses
already-saved files for links instead of re-rendering them, so a crash or
interrupt costs minutes, not the run.

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

# Paths never worth crawling: mutating/form endpoints, auth churn, admin,
# the webclient, per-user read/unread bookkeeping, and JSON APIs. Django's
# logout link would end the crawl session. Extend as the first real run
# reveals more (the summary prints a sample of skipped URLs).
SKIP_PATTERNS = [
    r"^/admin\b",
    r"^/logout\b",
    r"^/accounts/log",
    r"^/webclient\b",
    r"/delete",
    r"/edit",
    r"/create",
    r"/comment$",
    r"/upload",
    r"/select_portrait$",
    r"/api/",
    r"/journals/list/read/",
    r"/boards/unread$",
    r"/view/unread$",
    r"\.(?:json|csv|ics)$",
]
SKIP_RE = re.compile("|".join(SKIP_PATTERNS))

# Seed URLs, checked against arxcode's urls.py (prefixes: /character/,
# /comms/ for msgs, /dom/ for dominion, /topics/ for help). Rosters cover
# every state so departed characters' sheets are reached too.
DEFAULT_SEEDS = [
    "/",
    "/character/active/",
    "/character/available/",
    "/character/incomplete/",
    "/character/unavailable/",
    "/character/inactive/",
    "/character/gone/",
    "/character/story/",
    "/dom/cal/list/",
    "/comms/journals/list/",
    "/comms/boards/",
    "/topics/",
    "/news/",
    "/support/",
]

# For every character sheet the crawl discovers, force-enqueue these
# sub-pages (relative to /character/sheet/<id>/). Deliberately explicit
# instead of trusting the sheet template's tab links: actions and journals
# are exactly the lore people will come looking for.
SHEET_RE = re.compile(r"^/character/sheet/(\d+)/$")
SHEET_SUBPAGES = ["story", "actions/", "clues/", "gallery", "scenes"]

STATUS_OK = 200


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

    /dom/cal/list/       -> dom/cal/list/index.html
    /character/sheet/5/  -> character/sheet/5/index.html  (file_server
    serves the extensionless dir with an implicit index lookup)
    /foo/?page=2         -> foo/index__page=2.html  (links rewritten to match)
    /static/css/site.css -> static/css/site.css     (kept verbatim)

    Deterministic on the URL alone - link rewriting and resume both rely on
    that (no crawl-order state involved).
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


# [^"']* (not +) before the '?': Django pagination emits bare href="?page=2"
# links with nothing before the query at all.
HREF_RE = re.compile(r"""(href=["'])([^"']*\?[^"']+)(["'])""")


def rewrite_query_links(html, base_path):
    """Point query-string hrefs at their exported filenames.

    Plain path links need no rewriting (the tree mirrors the URL space);
    only ?query URLs get distinct filenames. url_to_relpath is
    deterministic, so this needs no global crawl state and each page can be
    rewritten and written to disk the moment it is fetched.
    """

    def repl(match):
        link, _frag = urldefrag(match.group(2))
        parts = urlsplit(urljoin(base_path if base_path.endswith("/") else base_path + "/", link))
        if parts.scheme or parts.netloc or not parts.query:
            return match.group(0)
        return match.group(1) + "/" + url_to_relpath(parts.path, parts.query) + match.group(3)

    return HREF_RE.sub(repl, html)


def copy_tree(src, dst):
    """shutil.copytree without dirs_exist_ok, which needs Python 3.8+ -
    the old box's venv may predate it."""
    for root_dir, _dirs, files in os.walk(src):
        rel = os.path.relpath(root_dir, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(root_dir, name), os.path.join(target_dir, name))


def extract_links(html, base_path, seen, queue, skipped):
    """Feed a page's links into the crawl frontier (sheet sub-pages too)."""
    extractor = LinkExtractor()
    extractor.feed(html)
    for raw in extractor.links:
        link, _frag = urldefrag(
            urljoin(base_path if base_path.endswith("/") else base_path + "/", raw)
        )
        parts = urlsplit(link)
        if parts.scheme or parts.netloc:  # external
            continue
        new_path, new_query = parts.path, parts.query
        if not new_path.startswith("/") or SKIP_RE.search(new_path):
            skipped.append(link)
            continue
        enqueue = [(new_path, new_query)]
        sheet = SHEET_RE.match(new_path)
        if sheet:
            enqueue.extend((new_path + sub, "") for sub in SHEET_SUBPAGES)
        for key in enqueue:
            if key not in seen:
                seen.add(key)
                queue.append(key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory for the static tree")
    parser.add_argument(
        "--settings",
        default="server.conf.settings",
        help="DJANGO_SETTINGS_MODULE (default: %(default)s)",
    )
    parser.add_argument(
        "--username",
        default="",
        help="account to crawl as (default: first superuser). STAFF sees "
        "secrets/clues AND all black journals; a fresh non-staff account "
        "sees neither - see the module docstring",
    )
    parser.add_argument("--seed", action="append", default=[], help="extra seed URL(s); repeatable")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip re-rendering pages whose output file already exists; "
        "their saved HTML is re-parsed for links so the frontier still "
        "grows past them (restarts cost minutes, not the run)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=300000,
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
    print("crawling as %s (staff=%s)" % (user.username, user.is_staff or user.is_superuser))

    client = Client()
    client.force_login(user)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    queue = deque((seed, "") for seed in DEFAULT_SEEDS + args.seed)
    seen = set(queue)
    exported = resumed = 0
    skipped, errors = [], []

    while queue and exported + resumed < args.max_pages:
        path, query = queue.popleft()
        relpath = url_to_relpath(path, query)
        full = os.path.join(out, relpath)

        if args.resume and os.path.exists(full):
            resumed += 1
            if full.endswith(".html"):
                with open(full, encoding="utf-8", errors="replace") as fh:
                    extract_links(fh.read(), path, seen, queue, skipped)
            continue

        target = "%s?%s" % (path, query) if query else path
        try:
            response = client.get(target, follow=True)
        except Exception as exc:  # noqa: BLE001 - a page that 500s must not kill the crawl
            errors.append((target, repr(exc)))
            continue
        if response.status_code != STATUS_OK:
            errors.append((target, "HTTP %s" % response.status_code))
            continue

        content_type = response.get("Content-Type", "")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if "text/html" in content_type:
            html = response.content.decode(response.charset or "utf-8", errors="replace")
            extract_links(html, path, seen, queue, skipped)
            # Stream to disk NOW - link rewriting is deterministic, so
            # nothing needs to wait for the crawl to finish, and memory
            # stays flat no matter how many pages six years produced.
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(rewrite_query_links(html, path))
        else:
            with open(full, "wb") as fh:
                fh.write(response.content)
        exported += 1

        if exported % 500 == 0:
            print("  %d exported (%d resumed), %d queued" % (exported, resumed, len(queue)))

    # Static assets straight from disk - the crawl only picks up assets a
    # page referenced; this sweeps the rest (css url() references etc.).
    for setting_name, url_prefix in (("STATIC_ROOT", "static"), ("MEDIA_ROOT", "media")):
        root = getattr(settings, setting_name, "")
        if root and os.path.isdir(root):
            dest = os.path.join(out, url_prefix)
            print("copying %s -> %s" % (root, dest))
            copy_tree(root, dest)

    print("\nexported %d pages (+%d resumed) to %s" % (exported, resumed, out))
    print("errors: %d (first 20 below)" % len(errors))
    for target, err in errors[:20]:
        print("  %s -> %s" % (target, err))
    print("skipped-by-rule (sample): %s" % sorted(set(skipped))[:20])
    if not os.path.exists(os.path.join(out, "index.html")):
        sys.exit("no top-level index.html was produced - the sync script will refuse this tree")


if __name__ == "__main__":
    main()
