"""Public-reaction news feed (#1450) — the pull/browse vector of the public-reaction center.

Aggregates two domains that already track public awareness into one recency-ordered feed scoped
to what a viewer's persona would plausibly have heard:

- **Deeds** — ``LegendEntry`` rows the viewer's societies are aware of (``societies_aware``, the
  renown spread system).
- **Scandals** — ``Secret`` rows exposed to the viewer's societies (``societies_exposed``, the
  reputation bridge, #1429).

There is **no feed model**: both sources own their own awareness M2M, so this service just queries
and merges them (per the contextual-centers principle — each center reads its own domains' data).
This is the buildable-now slice of the public-reaction epic (#1450); the echo (push) and in-world
hub (place) vectors, and a first-class ``reach`` taxonomy, are later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from world.news.constants import FeedItemKind
from world.secrets.models import Secret
from world.societies.models import LegendEntry, OrganizationMembership, SocietyReputation

if TYPE_CHECKING:
    from world.scenes.models import Persona

_DEFAULT_LIMIT = 30


@dataclass(frozen=True)
class PublicFeedItem:
    """One row of the public feed: a deed or a scandal the viewer's societies are aware of."""

    kind: str
    headline: str
    subject: str
    occurred_at: datetime


def _viewer_society_ids(persona: Persona) -> set[int]:
    """Societies a persona hears public news through: its reputations + its orgs' societies.

    Union of the societies the persona has standing with (``SocietyReputation``) and the societies
    of the organizations it belongs to (``OrganizationMembership`` → ``Organization.society``).
    Standalone orgs (no society) contribute nothing.
    """
    society_ids = set(
        SocietyReputation.objects.filter(persona=persona).values_list("society_id", flat=True)
    )
    society_ids.update(
        OrganizationMembership.objects.filter(persona=persona)
        .exclude(organization__society__isnull=True)
        .values_list("organization__society_id", flat=True)
    )
    return society_ids


def _deed_item(entry: LegendEntry) -> PublicFeedItem:
    return PublicFeedItem(
        kind=FeedItemKind.DEED,
        headline=entry.title,
        subject=entry.persona.name,
        occurred_at=entry.updated_at,
    )


def _scandal_item(secret: Secret) -> PublicFeedItem:
    return PublicFeedItem(
        kind=FeedItemKind.SCANDAL,
        headline=secret.content,
        subject=secret.subject_sheet.character.db_key,
        occurred_at=secret.updated_date,
    )


def public_feed_for(persona: Persona, *, limit: int = _DEFAULT_LIMIT) -> list[PublicFeedItem]:
    """Recent public events (deeds + scandals) the persona's societies are aware of, newest first.

    Scoped to the societies the persona hears news through (``_viewer_society_ids``). Returns an
    empty list when the persona has no society awareness. Each source is capped at ``limit`` before
    the merge, so the merged feed never exceeds ``limit`` rows.
    """
    society_ids = _viewer_society_ids(persona)
    if not society_ids:
        return []
    deeds = (
        LegendEntry.objects.filter(is_active=True, societies_aware__id__in=society_ids)
        .select_related("persona")
        .order_by("-updated_at")
        .distinct()[:limit]
    )
    scandals = (
        Secret.objects.filter(societies_exposed__id__in=society_ids)
        .select_related("subject_sheet__character")
        .order_by("-updated_date")
        .distinct()[:limit]
    )
    items = [_deed_item(entry) for entry in deeds] + [_scandal_item(secret) for secret in scandals]
    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items[:limit]
