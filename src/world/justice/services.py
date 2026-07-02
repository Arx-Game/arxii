"""Justice services — law cascade, jurisdiction, heat accrual/read/decay (#1765).

Feudal shape (ADR: heat jurisdiction): laws live on the ``areas.Area`` tree and
resolve most-specific-wins; criminality is judged once, at the commit/allegation
location; the winning law's nearest ``dominant_society`` is the enforcing
society, and heat only ever mints where that society is dominant. Falloff is
emergent from knowledge locality — no distance math by design.

Area chains are walked via ``parent`` FKs directly (≤ 9 levels, identity-map
cached) — deliberately NOT the ``AreaClosure`` materialized view, so every read
works identically on the SQLite fast tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest

from world.justice.constants import HEAT_DECAY_PER_DAY, tier_for_value
from world.justice.models import AreaLaw, CrimeKind, DeedCrimeTag, HeatSource, PersonaHeat
from world.justice.types import HeatReading

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.areas.models import Area
    from world.scenes.models import Persona
    from world.societies.models import LegendEntry, Society


def _chain(area: Area | None) -> list[Area]:
    """Self-first ancestor chain via parent FKs (cycle-safe)."""
    chain: list[Area] = []
    seen: set[int] = set()
    node = area
    while node is not None and node.pk not in seen:
        chain.append(node)
        seen.add(node.pk)
        node = node.parent
    return chain


def _area_for_room(room: ObjectDB) -> Area | None:
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    return profile.area if profile is not None else None


def law_for(area: Area | None, crime_kind: CrimeKind) -> AreaLaw | None:
    """The law governing ``crime_kind`` at ``area`` — most-specific-wins.

    Walks self→ancestors; the first row found wins (a barony row beats the
    kingdom default). An ``exempts`` row means "explicitly legal here" and
    short-circuits to None. No row anywhere → None (not a crime here).
    """
    chain = _chain(area)
    if not chain:
        return None
    laws_by_area = {
        law.area_id: law
        for law in AreaLaw.objects.filter(area_id__in=[a.pk for a in chain], crime_kind=crime_kind)
    }
    for node in chain:
        law = laws_by_area.get(node.pk)
        if law is None:
            continue
        return None if law.exempts else law
    return None


def enforcing_society_for(area: Area | None) -> Society | None:
    """Nearest ``dominant_society`` walking up from ``area`` (self first)."""
    for node in _chain(area):
        if node.dominant_society_id is not None:
            return node.dominant_society
    return None


def tag_deed_crimes(deed: LegendEntry, crime_kinds: Iterable[CrimeKind]) -> int:
    """Idempotently mark ``deed`` as an instance of each crime kind; returns rows created."""
    created = 0
    for kind in crime_kinds:
        _, was_created = DeedCrimeTag.objects.get_or_create(deed=deed, crime_kind=kind)
        created += int(was_created)
    return created


def accrue_heat(
    *,
    persona: Persona,
    crime_kind: CrimeKind,
    area: Area | None,
    deed: LegendEntry | None = None,
    scale: int = 1,
) -> PersonaHeat | None:
    """Mint pursuit heat for ``persona`` at ``area``, if the act is criminal there.

    ``area`` is where the knowledge/allegation landed. The law resolves at that
    spot (most-specific-wins); the enforcing society is the nearest dominant
    society of the *winning law's* area; and the knowledge location must itself
    fall inside that society's dominion, else no warrant reaches it (no
    extradition). Returns the touched row, or None when nothing mints.

    ``deed`` is the *alleged* deed — recorded on the provenance row and never
    verified against actorship (false accusations are first-class, #1765).
    """
    if scale <= 0:
        return None
    law = law_for(area, crime_kind)
    if law is None:
        return None
    society = enforcing_society_for(law.area)
    if society is None or enforcing_society_for(area) != society:
        return None
    amount = law.heat_weight * scale
    if amount <= 0:
        return None
    with transaction.atomic():
        row, _ = PersonaHeat.objects.get_or_create(persona=persona, area=area, society=society)
        # Plain add (not F()): identity-mapped instances must never hold a
        # CombinedExpression, and the enclosing transaction covers the race.
        row.value = row.value + amount
        row.save(update_fields=["value", "updated_date"])
        HeatSource.objects.create(heat=row, deed=deed, amount=amount)
    return row


def accrue_for_deed_knowledge(*, deed: LegendEntry, room: ObjectDB, new_knower_count: int) -> None:
    """The deed-knowledge accrual writer: word landed at ``room`` for ``new_knower_count`` ears.

    For each crime kind the deed is tagged with, heat mints against the deed's
    own persona at the room's area (scaled by how many newly learned of it).
    Untagged deeds are the common case and cost one indexed query.
    """
    if new_knower_count <= 0 or deed.persona_id is None:
        return
    kinds = [tag.crime_kind for tag in deed.crime_tags.all()]
    if not kinds:
        return
    area = _area_for_room(room)
    if area is None:
        return
    for kind in kinds:
        accrue_heat(
            persona=deed.persona,
            crime_kind=kind,
            area=area,
            deed=deed,
            scale=new_knower_count,
        )


def heat_for(persona: Persona, room: ObjectDB, *, include_sources: bool = False) -> HeatReading:
    """The pursuit picture for ``persona`` standing in ``room`` — the one read seam.

    Sums this persona's heat rows whose area lies on the room's ancestor chain
    AND whose warrant society is the room's own nearest dominant society.
    Sanctuary (a guild hall whose building-level area declares a different
    dominant society) and cross-border immunity are the same mismatch.
    """
    area = _area_for_room(room)
    local_society = enforcing_society_for(area)
    if area is None or local_society is None:
        return HeatReading(value=0, tier=tier_for_value(0))
    rows = PersonaHeat.objects.filter(
        persona=persona,
        area_id__in=[a.pk for a in _chain(area)],
        society=local_society,
    )
    total = sum(row.value for row in rows)
    sources: list[HeatSource] = []
    if include_sources and total:
        sources = list(
            HeatSource.objects.filter(heat__in=rows).select_related("deed", "heat__area")
        )
    return HeatReading(value=total, tier=tier_for_value(total), sources=sources)


def associate_heat(*, from_persona: Persona, to_persona: Persona) -> int:
    """Re-apply one persona's heat onto another — the outing/identification seam.

    The first caller is the mission-report association chance (a masked deed
    reported barefaced); the #1334 secrets-outing writer calls the same seam
    later. Copies (adds) each warrant row; the mask keeps its own heat. Returns
    rows touched.
    """
    touched = 0
    for source_row in PersonaHeat.objects.filter(persona=from_persona, value__gt=0):
        with transaction.atomic():
            row, _ = PersonaHeat.objects.get_or_create(
                persona=to_persona, area=source_row.area, society=source_row.society
            )
            row.value = row.value + source_row.value
            row.save(update_fields=["value", "updated_date"])
            HeatSource.objects.create(heat=row, deed=None, amount=source_row.value)
        touched += 1
    return touched


def heat_decay_tick() -> int:
    """Daily tick: decay every heat row toward zero and drop the cold ones.

    Registered as a ``game_clock`` CronDefinition (clone of the gossip decay
    shape). Returns rows touched. Decay magnitude is PLACEHOLDER.
    """
    touched = PersonaHeat.objects.filter(value__gt=0).update(
        value=Greatest(F("value") - HEAT_DECAY_PER_DAY, 0)
    )
    PersonaHeat.objects.filter(value=0).delete()
    return touched
