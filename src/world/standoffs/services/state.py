"""Standoff state: opening one, the groups in it, and breaking it into a fight."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial, wraps
from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.combat.constants import OpponentStatus
from world.standoffs.constants import LIVE_GROUP_STATES, StandoffGroupState
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
    """A standoff is the stretch before round one with a group still live (OPEN or PROPOSED)."""
    if encounter.round_number != 0:
        return False
    return StandoffGroup.objects.filter(encounter=encounter, state__in=LIVE_GROUP_STATES).exists()


def open_standoff(encounter: CombatEncounter) -> list[StandoffGroup]:
    """One OPEN group per named NPC and per creature template among the active opponents.

    An opponent standing as a persona is its own group (#4373); the rest group by creature
    template. An opponent with neither is not part of the standoff. Then check causes.
    """
    persona_template: dict[int, int | None] = {}
    template_ids: set[int] = set()
    for opponent in encounter.opponents.filter(status=OpponentStatus.ACTIVE).order_by("pk"):
        if opponent.persona_id is not None:
            persona_template.setdefault(opponent.persona_id, opponent.creature_template_id)
        elif opponent.creature_template_id is not None:
            template_ids.add(opponent.creature_template_id)
    groups = [
        StandoffGroup.objects.create(encounter=encounter, creature_template_id=template_id)
        for template_id in sorted(template_ids)
    ]
    groups.extend(
        StandoffGroup.objects.create(
            encounter=encounter, creature_template_id=template_id, persona_id=persona_id
        )
        for persona_id, template_id in sorted(persona_template.items())
    )
    if groups:
        from world.standoffs.services.force import evaluate_causes  # noqa: PLC0415

        evaluate_causes(encounter)
    return groups


def member_filter(group: StandoffGroup) -> dict[str, int | None]:
    """The ``CombatOpponent`` lookup that picks a group's members.

    A named NPC's group is the opponents standing as that persona; a template group is the
    template's opponents that stand as nobody in particular.
    """
    if group.persona_id is not None:
        return {"persona_id": group.persona_id}
    return {"creature_template_id": group.creature_template_id, "persona__isnull": True}


def active_members(group: StandoffGroup) -> list[CombatOpponent]:
    """The group's opponents still in the fight."""
    return list(
        group.encounter.opponents.filter(**member_filter(group), status=OpponentStatus.ACTIVE)
    )


def settle_empty_groups(encounter: CombatEncounter) -> bool:
    """A live group with nobody left standing is SETTLED. True when any group was settled."""
    from world.standoffs.services.proposals import close_group_prompts  # noqa: PLC0415

    settled_any = False
    for group in encounter.standoff_groups.filter(state__in=LIVE_GROUP_STATES):
        if not active_members(group):
            group.state = StandoffGroupState.SETTLED
            group.save(update_fields=["state"])
            close_group_prompts(group, "Nobody is left in that group.")
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
    """Every live group goes to FIGHTING and round one begins.

    When the creatures start it, the "attack!" line goes out after commit, unless the caller
    passes ``attack_sink``: then the line is appended there instead and the caller sends it,
    so a verb's room lines read press, morale shift, attack.

    Locks the encounter row first and rechecks, so when two things break the standoff at
    once only the first writes; the second returns False and changes nothing.
    """
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415
    from world.standoffs.services.proposals import close_group_prompts  # noqa: PLC0415

    locked = CombatEncounter.objects.select_for_update().get(pk=encounter.pk)
    if not is_in_standoff(locked):
        return False
    attackers: list[StandoffGroup] = []
    for group in encounter.standoff_groups.filter(state__in=LIVE_GROUP_STATES):
        group.state = StandoffGroupState.FIGHTING
        group.save(update_fields=["state"])
        close_group_prompts(group, "The fight began.")
        attackers.append(group)
    encounter.initiated_by_pc_side = initiated_by_pc_side
    encounter.save(update_fields=["initiated_by_pc_side"])
    begin_declaration_phase(encounter)
    if initiated_by_pc_side is False:
        if attack_sink is not None:
            attack_sink.append(attack_line(attackers))
        else:
            transaction.on_commit(partial(_announce_attack, encounter, attackers))
    return True


def attack_line(attackers: list[StandoffGroup]) -> str:
    """The room line when groups start the fight: "The Sellswords and Maud Carrow attack!"."""
    referents = [group.referent for group in attackers]
    if not referents:
        return "They attack!"
    text = " and ".join(referents)
    verb = "attacks" if len(attackers) == 1 and attackers[0].persona_id is not None else "attack"
    return f"{text[0].upper()}{text[1:]} {verb}!"


def _announce_attack(encounter: CombatEncounter, attackers: list[StandoffGroup]) -> None:
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
