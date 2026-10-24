"""Link-preview meta tags for pages shared outside the site.

Discord and other unfurlers read the static HTML and never run the React app, so
the title and description of a shared link have to be in the page the server
sends. ``FrontendAppView`` asks this module for the preview matching the
requested path and swaps it into ``index.html``. Only rows an anonymous visitor
can already read are used, so a preview never says more than the page does.
"""

from dataclasses import dataclass
import html
import re

from world.codex.models import CodexEntry
from world.realms.services import realm_by_slug

DEFAULT_DESCRIPTION = "A text-based collaborative storytelling and roleplaying game."

# Longest description kept; Discord clips long ones itself, this keeps the tag tidy.
MAX_DESCRIPTION_LENGTH = 200

_REALM_PATH = re.compile(r"^/realms/(?P<slug>[-a-z0-9]+)/?$")
_CODEX_PATH = "/codex"
_CODEX_ENTRY_PARAM = "entry"
# Lore text marks line breaks and tabs with Evennia's %r / %t / %b codes.
_LORE_BREAK = re.compile(r"%r|\r?\n")
_LORE_SPACE = re.compile(r"%t|%b|\s+")
_PARAGRAPH_BREAK = re.compile(r"(?:%r|\r?\n)\s*(?:%r|\r?\n)")

# Every tag the preview replaces, wherever index.html spells it.
_REPLACED_TAGS = re.compile(
    r"<meta\s[^>]*?(?:name=\"description\"|property=\"og:(?:title|description|type|url)\")"
    r"[^>]*?/>\s*",
    re.DOTALL,
)
_TITLE_TAG = re.compile(r"<title>.*?</title>", re.DOTALL)


@dataclass(frozen=True)
class LinkPreview:
    """What a shared link shows: a title and a one-paragraph description."""

    title: str
    description: str


DEFAULT_PREVIEW = LinkPreview(title="Arx", description=DEFAULT_DESCRIPTION)


def first_paragraph(text: str) -> str:
    """Return the first paragraph of authored prose, flattened and clipped to length."""
    paragraph = _PARAGRAPH_BREAK.split(text.strip(), maxsplit=1)[0]
    flat = _LORE_SPACE.sub(" ", _LORE_BREAK.sub(" ", paragraph)).strip()
    if len(flat) <= MAX_DESCRIPTION_LENGTH:
        return flat
    clipped = flat[: MAX_DESCRIPTION_LENGTH - 1].rsplit(" ", 1)[0].rstrip(",;:.- ")
    return f"{clipped}…"


def _realm_preview(slug: str) -> LinkPreview | None:
    realm = realm_by_slug(slug)
    if realm is None:
        return None
    opening = realm.testament_sections.order_by("sort_order").first()
    source = opening.body if opening is not None else realm.description
    return LinkPreview(
        title=f"{realm.name} · Arx",
        description=first_paragraph(source) or DEFAULT_DESCRIPTION,
    )


def _codex_preview(entry_id: str) -> LinkPreview | None:
    if not entry_id.isdigit():
        return None
    entry = CodexEntry.objects.filter(pk=int(entry_id), is_public=True).first()
    if entry is None:
        return None
    return LinkPreview(
        title=f"{entry.name} · Codex · Arx",
        description=first_paragraph(entry.lore_content) or entry.summary or DEFAULT_DESCRIPTION,
    )


def preview_for(path: str, query: dict[str, str]) -> LinkPreview:
    """Pick the preview for a requested path, falling back to the site default."""
    realm_match = _REALM_PATH.match(path)
    if realm_match is not None:
        return _realm_preview(realm_match["slug"]) or DEFAULT_PREVIEW
    if path.rstrip("/") == _CODEX_PATH and _CODEX_ENTRY_PARAM in query:
        return _codex_preview(query[_CODEX_ENTRY_PARAM]) or DEFAULT_PREVIEW
    return DEFAULT_PREVIEW


def apply_preview(page: str, preview: LinkPreview, url: str) -> str:
    """Swap the preview's title and description tags into the served index.html."""
    title = html.escape(preview.title, quote=True)
    description = html.escape(preview.description, quote=True)
    tags = (
        f'<meta name="description" content="{description}" />\n'
        f'    <meta property="og:title" content="{title}" />\n'
        f'    <meta property="og:description" content="{description}" />\n'
        f'    <meta property="og:type" content="website" />\n'
        f'    <meta property="og:url" content="{html.escape(url, quote=True)}" />\n'
    )
    page = _REPLACED_TAGS.sub("", page)
    page = _TITLE_TAG.sub(lambda _match: f"<title>{html.escape(preview.title)}</title>", page, 1)
    return page.replace("</head>", f"    {tags}  </head>", 1)
