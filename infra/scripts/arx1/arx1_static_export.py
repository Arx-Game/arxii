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
  - a synthetic /lore/ appendix rendered straight from the DB: all
    mysteries, revelations, and clues (never-discovered ones included,
    gm_notes included) - none of which had a crawlable surface in Arx I

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
    r"^/admin",  # /admin/ AND /admintools/ (staff search tool - no archive value)
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

    Plain path links need no rewriting HERE (the tree mirrors the URL space);
    only ?query URLs get distinct filenames. url_to_relpath is
    deterministic, so this needs no global crawl state and each page can be
    rewritten and written to disk the moment it is fetched.

    The tree is emitted ROOT-RELATIVE on purpose even though the archive is
    now served under a path prefix (#3320, ADR-0232). Re-pointing those links
    is arx1_prefix_rewrite.py's job, run by roles/arx1_archive at install
    time: this script only ever ran on the Arx I box, which is retired, so
    doing it here would leave the tarball already in the bucket unfixable
    without reviving that box. One implementation, applied on the way in.
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


LORE_CSS = (
    "<style>body{max-width:60em;margin:2em auto;padding:0 1em;"
    "font-family:Georgia,serif;line-height:1.5;background:#f8f6f0;color:#222}"
    "h1,h2,h3{font-family:Palatino,Georgia,serif}article{border-bottom:1px solid #ccc;"
    "margin-bottom:1.5em;padding-bottom:1em}.meta{color:#666;font-size:.9em}"
    ".herring{color:#a00}.gm{background:#fff3d6;padding:.5em;margin:.5em 0}"
    ".undiscovered{color:#666;font-style:italic}</style>"
)
CLUES_PER_PAGE = 100


def write_page(out, relpath, title, body_html):
    full = os.path.join(out, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(
            "<!doctype html><html><head><meta charset='utf-8'><title>%s</title>%s"
            "</head><body><p><a href='/lore/'>Lore appendix</a> | <a href='/'>Archive home</a>"
            "</p>%s</body></html>" % (title, LORE_CSS, body_html)
        )


def export_lore_appendix(out):
    """Render mysteries/revelations/clues straight from the DB under /lore/.

    Revelations and mysteries never had a web surface in Arx I (telnet
    investigation commands + Django admin only), and clues only appeared on
    the sheets of characters who discovered them - so this appendix is the
    only place never-discovered lore becomes readable without standing the
    game back up. Ruled in scope 2026-08-21: all of it was staff-intended
    (gm_notes included). Pages land under /lore/, a prefix arxcode never
    used, so nothing collides with the crawled tree.
    """
    from html import escape

    from web.character.models import Clue, Mystery, Revelation

    def revelation_html(rev):
        clues = list(rev.clues.all().order_by("rating", "name"))
        clue_links = ", ".join(
            "<a href='/lore/clues/#clue-%d'>%s</a>" % (c.id, escape(c.name or "Clue #%d" % c.id))
            for c in clues
        )
        finders = ", ".join(sorted(str(e) for e in rev.characters.all())) or (
            "<span class='undiscovered'>never discovered</span>"
        )
        parts = [
            "<article id='rev-%d'><h3>%s%s</h3>"
            % (
                rev.id,
                escape(rev.name or "Revelation #%d" % rev.id),
                " <span class='herring'>(red herring)</span>" if rev.red_herring else "",
            ),
            "<div>%s</div>" % escape(rev.desc).replace("\n", "<br>"),
        ]
        if rev.gm_notes:
            parts.append(
                "<div class='gm'><b>GM notes:</b> %s</div>"
                % escape(rev.gm_notes).replace("\n", "<br>")
            )
        parts.append("<p class='meta'>Clues: %s</p>" % (clue_links or "none"))
        parts.append("<p class='meta'>Discovered by: %s</p></article>" % finders)
        return "".join(parts)

    def clue_html(clue):
        revs = ", ".join(
            "<a href='/lore/mysteries/#rev-%d'>%s</a>"
            % (r.id, escape(r.name or "Revelation #%d" % r.id))
            for r in clue.revelations.all()
        )
        finders = ", ".join(sorted(str(e) for e in clue.characters.all())) or (
            "<span class='undiscovered'>never discovered</span>"
        )
        parts = [
            "<article id='clue-%d'><h3>%s%s</h3>"
            % (
                clue.id,
                escape(clue.name or "Clue #%d" % clue.id),
                " <span class='herring'>(red herring)</span>" if clue.red_herring else "",
            ),
            "<p class='meta'>%s | rating %s</p>" % (clue.get_clue_type_display(), clue.rating),
            "<div>%s</div>" % escape(clue.desc).replace("\n", "<br>"),
        ]
        if clue.gm_notes:
            parts.append(
                "<div class='gm'><b>GM notes:</b> %s</div>"
                % escape(clue.gm_notes).replace("\n", "<br>")
            )
        parts.append("<p class='meta'>Revelations: %s</p>" % (revs or "none"))
        parts.append("<p class='meta'>Discovered by: %s</p></article>" % finders)
        return "".join(parts)

    # One page for all mysteries + their revelations (there are far fewer of
    # these than clues), with mystery-less revelations appended at the end.
    revs_seen = set()
    sections = []
    for mystery in Mystery.objects.all().order_by("category", "name"):
        revs = list(mystery.revelations.all().order_by("name"))
        revs_seen.update(r.id for r in revs)
        sections.append(
            "<section><h2>%s</h2><p class='meta'>%s</p><div>%s</div>%s</section>"
            % (
                escape(mystery.name),
                escape(mystery.category or ""),
                escape(mystery.desc).replace("\n", "<br>"),
                "".join(revelation_html(r) for r in revs),
            )
        )
    orphans = Revelation.objects.exclude(id__in=revs_seen).order_by("name")
    if orphans:
        sections.append(
            "<section><h2>Revelations outside any mystery</h2>%s</section>"
            % "".join(revelation_html(r) for r in orphans)
        )
    write_page(
        out,
        "lore/mysteries/index.html",
        "Mysteries and Revelations",
        "<h1>Mysteries and Revelations</h1>" + "".join(sections),
    )

    # Clues, paginated by hand (six years of them will not fit one page).
    # Bare-string prefetch on purpose: this runs against ARX I's Django, not
    # this repo's - arxcode has no Prefetch-object convention to honor, and
    # plain M2M prefetches are exactly right for a one-shot full dump.
    clues = list(
        Clue.objects.all().order_by("name", "id").prefetch_related("revelations", "characters")  # noqa: PREFETCH_STRING
    )
    total_pages = max(1, (len(clues) + CLUES_PER_PAGE - 1) // CLUES_PER_PAGE)
    for page in range(total_pages):
        chunk = clues[page * CLUES_PER_PAGE : (page + 1) * CLUES_PER_PAGE]
        nav = " | ".join(
            "<b>%d</b>" % (n + 1)
            if n == page
            else "<a href='/lore/clues/%s'>%d</a>" % ("" if n == 0 else "page-%d/" % (n + 1), n + 1)
            for n in range(total_pages)
        )
        relpath = (
            "lore/clues/index.html" if page == 0 else "lore/clues/page-%d/index.html" % (page + 1)
        )
        write_page(
            out,
            relpath,
            "Clues (page %d)" % (page + 1),
            "<h1>All Clues</h1><p class='meta'>Pages: %s</p>%s<p class='meta'>Pages: %s</p>"
            % (nav, "".join(clue_html(c) for c in chunk), nav),
        )

    undiscovered = sum(1 for c in clues if not c.characters.all())
    write_page(
        out,
        "lore/index.html",
        "Lore Appendix",
        "<h1>Lore Appendix</h1><p>Rendered straight from the game database - "
        "including lore no player ever found.</p><ul>"
        "<li><a href='/lore/mysteries/'>Mysteries and revelations</a> (%d mysteries, "
        "%d revelations)</li>"
        "<li><a href='/lore/clues/'>All clues</a> (%d clues, %d never discovered, "
        "%d pages)</li></ul>"
        % (
            Mystery.objects.count(),
            Revelation.objects.count(),
            len(clues),
            undiscovered,
            total_pages,
        ),
    )
    print(
        "lore appendix: %d mysteries, %d revelations, %d clues (%d never discovered)"
        % (Mystery.objects.count(), Revelation.objects.count(), len(clues), undiscovered)
    )


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
    parser.add_argument(
        "--skip-lore-appendix",
        action="store_true",
        help="skip the /lore/ appendix (mysteries/revelations/all-clues "
        "rendered straight from the DB - on by default because that lore "
        "has no crawlable surface)",
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

    if not args.skip_lore_appendix:
        export_lore_appendix(out)

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
