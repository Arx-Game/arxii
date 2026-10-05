"""Standoff state: opening one, the groups in it, and breaking it into a fight."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial, wraps
from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.combat.constants import OpponentStatus
from world.standoffs.constants import StandoffGroupState
from world.standoffs.models import StandoffGroup

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatOpponent


def flush_standoff_cache(encounter: CombatEncounter) -> None:
    """Drop the encounter, its groups and its opponents from the identity map.

    A SharedMemoryModel instance mutated inside a transaction that then rolls back keeps
    its mutated attributes in the cache while the row reverts; flushing makes the next
    reader load what the database holds.
    """
    from world.combat.models import CombatEncounter, CombatOpponent  # noqa: PLC0415

    for model, owner_field in (
        (CombatOpponent, "encounter_id"),
        (StandoffGroup, "encounter_id"),
    ):
        for cached in model.get_all_cached_instances():
            if cached.__dict__.get(owner_field) == encounter.pk:
                cached.flush_from_cache(force=True)
    CombatEncounter.flush_cached_instance(encounter)


def flush_cache_on_error(
    encounter_of: Callable[..., CombatEncounter],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate an ``@transaction.atomic`` verb: on any exception flush what it touched.

    Apply OUTSIDE ``@transaction.atomic`` so the rollback has already happened. The
    exception is re-raised. ``encounter_of`` takes the verb's own arguments and returns
    its encounter.
    """

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            completed = False
            try:
                result = func(*args, **kwargs)
                completed = True
            finally:
                if not completed:
                    flush_standoff_cache(encounter_of(*args, **kwargs))
            return result

        return wrapper

    return decorate


def is_in_standoff(encounter: CombatEncounter) -> bool:
    """A standoff is the stretch before round one with a group still OPEN."""
    if encounter.round_number != 0:
        return False
    return StandoffGroup.objects.filter(encounter=encounter, state=StandoffGroupState.OPEN).exists()


def open_standoff(encounter: CombatEncounter) -> list[StandoffGroup]:
    """One OPEN group per creature template among the active opponents, then check causes."""
    template_ids = {
        opponent.creature_template_id
        for opponent in encounter.opponents.filter(status=OpponentStatus.ACTIVE)
        if opponent.creature_template_id is not None
    }
    groups = [
        StandoffGroup.objects.create(encounter=encounter, creature_template_id=template_id)
        for template_id in sorted(template_ids)
    ]
    if groups:
        from world.standoffs.services.force import evaluate_causes  # noqa: PLC0415

        evaluate_causes(encounter)
    return groups


def active_members(group: StandoffGroup) -> list[CombatOpponent]:
    """The group's opponents still in the fight."""
    return list(
        group.encounter.opponents.filter(
            creature_template_id=group.creature_template_id, status=OpponentStatus.ACTIVE
        )
    )


def settle_empty_groups(encounter: CombatEncounter) -> bool:
    """An OPEN group with nobody left standing is SETTLED. True when any group was settled."""
    settled_any = False
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN):
        if not active_members(group):
            group.state = StandoffGroupState.SETTLED
            group.save(update_fields=["state"])
            settled_any = True
    return settled_any


@flush_cache_on_error(lambda encounter, **_: encounter)
@transaction.atomic
def end_standoff_into_fight(
    encounter: CombatEncounter,
    *,
    initiated_by_pc_side: bool | None,
    attack_sink: list[str] | None = None,
) -> bool:
    """Every OPEN group goes to FIGHTING and round one begins.

    When the creatures start it, the "attack!" line goes out after commit, unless the caller
    passes ``attack_sink``: then the line is appended there instead and the caller sends it,
    so a verb's room lines read press, morale shift, attack.

    Locks the encounter row first and rechecks, so when two things break the standoff at
    once only the first writes; the second returns False and changes nothing.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415

    locked = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if not is_in_standoff(locked):
        return False
    attackers = []
    for group in encounter.standoff_groups.filter(state=StandoffGroupState.OPEN):
        group.state = StandoffGroupState.FIGHTING
        group.save(update_fields=["state"])
        attackers.append(group.creature_template.name)
    encounter.initiated_by_pc_side = initiated_by_pc_side
    encounter.save(update_fields=["initiated_by_pc_side"])
    begin_declaration_phase(encounter)
    if initiated_by_pc_side is False:
        if attack_sink is not None:
            attack_sink.append(attack_line(attackers))
        else:
            transaction.on_commit(partial(_announce_attack, encounter, attackers))
    return True


def attack_line(attackers: list[str]) -> str:
    return f"The {' and the '.join(attackers)} attack!"


def _announce_attack(encounter: CombatEncounter, attackers: list[str]) -> None:
    """Tell the room, live, that the creatures began the fight."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(
        encounter=encounter,
        narration=attack_line(attackers),
        deliver_telnet=True,
    )


def begin_round_or_break_standoff(
    encounter: CombatEncounter, *, initiated_by_pc_side: bool | None
) -> bool:
    """Start a round; if the encounter is still in its standoff, that breaks the standoff.

    True when a round began (or the standoff broke into one); False when the standoff had
    already ended by another hand and nothing was written.
    """
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415

    if is_in_standoff(encounter):
        return end_standoff_into_fight(encounter, initiated_by_pc_side=initiated_by_pc_side)
    begin_declaration_phase(encounter)
    return True
