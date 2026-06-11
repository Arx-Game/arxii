"""Per-persona deed knowledge (#902).

Four vectors decide which deeds a persona knows of:

- **Doer** — it's their deed (implicit, ``LegendEntry.persona``).
- **Witnessed** — on the scene list when the deed was created (mission-born
  deeds grant the party instead; bystanders in the final room keep the
  assumption of ignorance).
- **Heard the tale told** — on the scene list at a successful telling.
- **Common knowledge** — total legend ≥ ``COMMON_KNOWLEDGE_MULTIPLIER`` ×
  base (computed, never stored).

Plus the existing society-awareness channel (``LegendEntry.societies_aware``
∩ the persona's org memberships), which stays as the NPC/social-fabric
vector. ``known_deed_ids`` is the single union gate consumed by the spread
picker and the foreign renown card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import F, QuerySet, Sum
from django.db.models.functions import Coalesce

from world.societies.constants import COMMON_KNOWLEDGE_MULTIPLIER, DeedKnowledgeSource
from world.societies.models import LegendEntry, OrganizationMembership, PersonaDeedKnowledge

if TYPE_CHECKING:
    from world.scenes.models import Persona, Scene


def grant_deed_knowledge(
    *,
    deed: LegendEntry,
    personas: list[Persona],
    source: str,
) -> int:
    """Idempotently grant knowledge of ``deed`` to ``personas``.

    The deed's own persona is skipped (the doer needs no row). Existing rows
    win (first vector to arrive keeps its provenance). Returns the number of
    rows created.
    """
    candidate_ids = {p.pk for p in personas if p.pk != deed.persona_id}
    if not candidate_ids:
        return 0
    # Pre-filter known pairs for an honest count (bulk_create with
    # ignore_conflicts returns the full input list either way); keep
    # ignore_conflicts as the concurrent-grant race guard.
    existing = set(
        PersonaDeedKnowledge.objects.filter(deed=deed, persona_id__in=candidate_ids).values_list(
            "persona_id", flat=True
        )
    )
    rows = [
        PersonaDeedKnowledge(persona_id=pk, deed=deed, source=source)
        for pk in candidate_ids - existing
    ]
    if not rows:
        return 0
    created = PersonaDeedKnowledge.objects.bulk_create(rows, ignore_conflicts=True)
    return len(created)


def scene_witness_personas(scene: Scene) -> list[Persona]:
    """Everyone "on the scene list" as personas (generous by design, #902).

    Union of: distinct personas that have interacted in the scene (the face
    actually worn) and the primary personas of participating accounts with
    no interactions yet (silent watchers, dropped connections). Review note:
    a silent masked watcher resolves to their primary persona — adjust here
    if masquerade-strictness should win over inclusion.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import Interaction, Persona  # noqa: PLC0415

    interacted = list(
        Persona.objects.filter(pk__in=Interaction.objects.filter(scene=scene).values("persona_id"))
    )
    covered_sheet_ids = {p.character_sheet_id for p in interacted}

    silent: list[Persona] = []
    for participation in scene.participations.select_related("account"):
        for entry in RosterEntry.objects.for_account(participation.account):
            sheet = entry.character_sheet
            if sheet.pk in covered_sheet_ids:
                continue
            primary = sheet.primary_persona
            if primary is not None:
                silent.append(primary)
                covered_sheet_ids.add(sheet.pk)
    return interacted + silent


def known_deed_ids(persona: Persona) -> QuerySet:
    """Id-queryset of every active deed ``persona`` knows of (#902 union).

    Society awareness ∪ doer ∪ knowledge rows ∪ common knowledge. Shaped as
    a values("pk") union for cheap ``pk__in`` composition (mirrors the
    interaction-feed pattern).
    """
    society_ids = OrganizationMembership.objects.filter(persona=persona).values_list(
        "organization__society_id", flat=True
    )
    base = LegendEntry.objects.filter(is_active=True)
    return (
        base.filter(societies_aware__in=society_ids)
        .values("pk")
        .union(
            base.filter(persona=persona).values("pk"),
            base.filter(knowledge_rows__persona=persona).values("pk"),
            base.annotate(spread_total=Coalesce(Sum("spreads__value_added"), 0))
            .filter(
                base_value__gt=0,
                spread_total__gte=(COMMON_KNOWLEDGE_MULTIPLIER - 1) * F("base_value"),
            )
            .values("pk"),
        )
    )


__all__ = [
    "DeedKnowledgeSource",
    "grant_deed_knowledge",
    "known_deed_ids",
    "scene_witness_personas",
]
