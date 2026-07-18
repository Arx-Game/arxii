"""Public-reaction tidings feed (#1450) — the pull/browse vector of the public-reaction center.

Aggregates two domains that already track public awareness into one recency-ordered feed:

- **Deeds** — ``LegendEntry`` rows the scoping societies are aware of (``societies_aware``, the
  renown spread system).
- **Scandals** — ``Secret`` rows exposed to the scoping societies (``societies_exposed``, the
  reputation bridge, #1429).

There is **no feed model**: both sources own their own awareness M2M, so this service just queries
and merges them (per the contextual-centers principle — each center reads its own domains' data).
Two scopes share one core:

- ``public_feed_for(persona)`` — the viewer scope (web feed + telnet ``tidings``): the societies a
  persona hears tidings through.
- ``hub_feed_for_room(room)`` — the **civic-hub scope** (#1450 final slice): the local societies
  the #1464 ancestor walk resolves at a room — what the notice board carries, what the crier calls.

Items carry a ``category`` when the row's archetypes name a scandal category (the authored
"X Scandal" rows, #1806) — the player-legible type rendered as "A Treacherous Scandal: …".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from world.secrets.models import Secret
from world.societies.models import LegendEntry, OrganizationMembership, SocietyReputation
from world.tidings.constants import FeedItemKind

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

_DEFAULT_LIMIT = 30
_CATEGORY_SUFFIX = "Scandal"


@dataclass(frozen=True)
class PublicFeedItem:
    """One row of the public feed: a deed or a scandal the scoping societies are aware of."""

    kind: str
    headline: str
    subject: str
    occurred_at: datetime
    category: str | None = None


def _viewer_society_ids(persona: Persona) -> set[int]:
    """Societies a persona hears public tidings through: its reputations + its orgs' societies.

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


def _category_for(archetypes: Iterable) -> str | None:
    """The first authored scandal-category name among the row's archetypes, or None."""
    for archetype in archetypes:
        if archetype.name.endswith(_CATEGORY_SUFFIX):
            return archetype.name
    return None


def _deed_item(entry: LegendEntry) -> PublicFeedItem:
    return PublicFeedItem(
        kind=FeedItemKind.DEED,
        headline=entry.title,
        subject=entry.persona.name,
        occurred_at=entry.updated_at,
        category=_category_for(entry.archetypes.all()),
    )


def _scandal_item(secret: Secret) -> PublicFeedItem:
    return PublicFeedItem(
        kind=FeedItemKind.SCANDAL,
        headline=secret.content,
        subject=secret.subject_sheet.character.db_key,
        occurred_at=secret.updated_date,
        category=_category_for(secret.archetypes.all()),
    )


def public_feed_for_societies(
    society_ids: Iterable[int], *, limit: int = _DEFAULT_LIMIT
) -> list[PublicFeedItem]:
    """The core read: recent deeds + scandals known to ``society_ids``, newest first.

    Each source is capped at ``limit`` before the merge, so the merged feed never
    exceeds ``limit`` rows. Empty scope → empty feed.
    """
    society_ids = set(society_ids)
    if not society_ids:
        return []
    deeds = (
        LegendEntry.objects.filter(is_active=True, societies_aware__id__in=society_ids)
        .select_related("persona")
        .prefetch_related("archetypes")  # noqa: PREFETCH_STRING
        .order_by("-updated_at")
        .distinct()[:limit]
    )
    scandals = (
        Secret.objects.filter(societies_exposed__id__in=society_ids)
        .select_related("subject_sheet__character")
        .prefetch_related("archetypes")  # noqa: PREFETCH_STRING
        .order_by("-updated_date")
        .distinct()[:limit]
    )
    pardons = _pardon_items(society_ids, limit=limit)
    items = (
        [_deed_item(entry) for entry in deeds]
        + [_scandal_item(secret) for secret in scandals]
        + pardons
    )
    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items[:limit]


def _pardon_items(society_ids: set[int], *, limit: int) -> list[PublicFeedItem]:
    """A lord's pardons (#1826) — public acts, surfaced to the enforcing scope."""
    from world.justice.models import PardonGrant  # noqa: PLC0415

    grants = (
        PardonGrant.objects.filter(society_id__in=society_ids)
        .select_related("target_persona", "granter_persona", "area")
        .order_by("-created_date")[:limit]
    )
    return [
        PublicFeedItem(
            kind="pardon",
            headline=(
                f"{grant.granter_persona.name} pardons {grant.target_persona.name} "
                f"in {grant.area.name}"
            ),
            subject=grant.target_persona.name,
            occurred_at=grant.created_date,
            category="pardon",
        )
        for grant in grants
    ]


def public_feed_for(persona: Persona, *, limit: int = _DEFAULT_LIMIT) -> list[PublicFeedItem]:
    """Recent public events the persona's societies are aware of, newest first (viewer scope)."""
    return public_feed_for_societies(_viewer_society_ids(persona), limit=limit)


def hub_feed_for_room(
    room: ObjectDB | None, *, limit: int = _DEFAULT_LIMIT
) -> list[PublicFeedItem]:
    """The civic-hub scope (#1450): the local slice of awareness at ``room``.

    Resolves the room's local societies via the #1464 ancestor walk
    (``societies_for_area``) — a pure reader; whether the room actually carries a
    Notice Board / Town Crier feature is the *caller's* gate (the echo, the
    ``tidings local`` verb, and the room-state ``hub`` block all check it).
    """
    if room is None:
        return []
    from world.areas.services import get_room_profile, societies_for_area  # noqa: PLC0415

    profile = get_room_profile(room)
    societies = societies_for_area(profile.area)
    return public_feed_for_societies([society.pk for society in societies], limit=limit)


def house_feed_for(organization, *, limit: int = _DEFAULT_LIMIT) -> list[PublicFeedItem]:
    """The house feed (#1884): what the household hears about its own people.

    Replaces Arx 1's org informs with a pull feed. Scope is the org's active
    members' personas: their deeds (regardless of which societies know yet —
    the household always hears of its own) and revealed scandals about their
    characters. No feed model — same query-and-merge as the public feed.
    """
    member_persona_ids = OrganizationMembership.objects.filter(
        organization=organization,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).values("persona_id")
    deeds = (
        LegendEntry.objects.filter(persona_id__in=member_persona_ids, is_active=True)
        .select_related("persona")
        .prefetch_related("archetypes")  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel
        .order_by("-updated_at")[:limit]
    )
    sheet_ids = OrganizationMembership.objects.filter(
        organization=organization,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).values("persona__character_sheet_id")
    scandals = (
        Secret.objects.filter(subject_sheet_id__in=sheet_ids, societies_exposed__isnull=False)
        .select_related("subject_sheet__character")
        .prefetch_related("archetypes")  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel
        .order_by("-updated_date")
        .distinct()[:limit]
    )
    crises = _open_crisis_items(organization, limit=limit)
    items = (
        [_deed_item(entry) for entry in deeds]
        + [_scandal_item(secret) for secret in scandals]
        + crises
    )
    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items[:limit]


def _open_crisis_items(organization, *, limit: int) -> list[PublicFeedItem]:
    """Open crises on the org's domains (#2238) — the household hears its lands groan."""
    from world.societies.houses.models import DomainCrisis  # noqa: PLC0415

    crises = (
        DomainCrisis.objects.filter(domain__owner_org=organization, resolved_at__isnull=True)
        .select_related("domain", "crisis_type")
        .order_by("-opened_at")[:limit]
    )
    return [
        PublicFeedItem(
            kind="crisis",
            headline=(
                f"{crisis.crisis_type.name if crisis.crisis_type else 'Crisis'} "
                f"in {crisis.domain.name}"
            ),
            subject=crisis.domain.name,
            occurred_at=crisis.opened_at,
            category=crisis.severity,
        )
        for crisis in crises
    ]
