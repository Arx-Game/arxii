"""Derived-on-read NPC allegiance (#1590, #4091; ADR-0059 as amended by ADR-4091).

Allegiance is never stored for a charm: it is derived from the bearer's active
conditions whose ``ConditionTemplate.sets_allegiance`` is set, read by that field and
never by a condition's name. ``CombatOpponent.allegiance`` stays the stored side
(summons and companions are ALLY); no condition ever writes it (D4).

Precedence when one NPC carries several: charm, then turned, then calm (Decision 5).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.combat.constants import CombatAllegiance
from world.conditions.constants import Allegiance
from world.conditions.models import ConditionInstance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatOpponent

ALLEGIANCE_PRECEDENCE: tuple[Allegiance, ...] = (
    Allegiance.ALLY_OF_CASTER,
    Allegiance.TURNED,
    Allegiance.NEUTRAL,
)
_RANK = {value: index for index, value in enumerate(ALLEGIANCE_PRECEDENCE)}

# PLACEHOLDER system labels for narration and the digest (#4091).
_WON_OVER_VERBS = {
    Allegiance.ALLY_OF_CASTER: "charmed",
    Allegiance.TURNED: "turned",
    Allegiance.NEUTRAL: "calmed",
}


def won_over_verb(allegiance: str) -> str:
    """The past-tense verb naming how an NPC was won over."""
    return _WON_OVER_VERBS[Allegiance(allegiance)]


def designating_instance(instances: Iterable[ConditionInstance]) -> ConditionInstance | None:
    """Highest-precedence allegiance instance; ties go to the lowest pk."""
    flagged = [i for i in instances if i.condition.sets_allegiance in _RANK]
    if not flagged:
        return None
    return min(flagged, key=lambda i: (_RANK[i.condition.sets_allegiance], i.pk))


def _active_q() -> Q:
    # Same predicate as ConditionHandler._canonical_active_qs / get_active_conditions.
    return Q(is_suppressed=False) | Q(
        suppressed_until__isnull=False, suppressed_until__lt=timezone.now()
    )


def allegiance_instances_for(
    target_ids: Iterable[int], *, applied_since: datetime | None = None
) -> dict[int, list[ConditionInstance]]:
    """Active allegiance instances for many targets in one query, keyed by target_id."""
    ids = [pk for pk in target_ids if pk is not None]
    result: dict[int, list[ConditionInstance]] = defaultdict(list)
    if not ids:
        return result
    qs = (
        ConditionInstance.objects.filter(_active_q(), target_id__in=ids)
        .exclude(condition__sets_allegiance="")
        .select_related("condition", "current_stage")
    )
    if applied_since is not None:
        qs = qs.filter(applied_at__gte=applied_since)
    for instance in qs:
        result[instance.target_id].append(instance)
    return result


def effective_allegiance(
    opponent: CombatOpponent, instances: list[ConditionInstance]
) -> Allegiance:
    """Compose the stored side with the opponent's allegiance instances (pure)."""
    if opponent.allegiance == CombatAllegiance.ALLY:
        return Allegiance.ALLY_OF_CASTER
    instance = designating_instance(instances)
    if instance is None:
        return Allegiance.ENEMY
    return Allegiance(instance.condition.sets_allegiance)


def effective_allegiances(
    opponents: Iterable[CombatOpponent], *, applied_since: datetime | None = None
) -> dict[int, Allegiance]:
    """Effective allegiance for every opponent, keyed by opponent pk. One query."""
    opponents = list(opponents)
    by_target = allegiance_instances_for(
        (o.objectdb_id for o in opponents), applied_since=applied_since
    )
    return {o.pk: effective_allegiance(o, by_target.get(o.objectdb_id, [])) for o in opponents}


def derive_allegiance(
    opponent: CombatOpponent,
    encounter: CombatEncounter,  # noqa: ARG001 - kept for caller compatibility
) -> Allegiance:
    """One opponent's effective allegiance."""
    return effective_allegiances([opponent])[opponent.pk]


def allegiance_instance_on(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - ephemeral CombatNPCs have no sheet or persona
) -> ConditionInstance | None:
    """The designating allegiance instance on one target (runs lazy IC-time expiry)."""
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    return designating_instance(
        get_active_conditions(target).exclude(condition__sets_allegiance="")
    )


def allegiance_sourced_by(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - ephemeral CombatNPCs have no sheet or persona
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - ConditionInstance.source_character is ObjectDB
    *,
    kinds: frozenset[str],
) -> ConditionInstance | None:
    """An active allegiance instance of one of ``kinds`` that ``character`` applied."""
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    return (
        get_active_conditions(target)
        .filter(condition__sets_allegiance__in=kinds, source_character_id=character.pk)
        .order_by("pk")
        .first()
    )
