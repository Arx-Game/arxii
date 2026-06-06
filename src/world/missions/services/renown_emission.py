"""#735 — Mission terminal-route renown award emission.

Parallel to ``rewards.emit_terminal_rewards`` (the flat-reward emitter),
this module walks ``route.renown_awards`` (``MissionRenownAward`` rows)
and fires ``fire_renown_award`` for each award × recipient pair.

Recipient resolution mirrors the flat-reward side:

* ``contract_holder_only=True`` → exactly one fire, on the contract
  holder's persona. Prefer ``MissionInstance.accepted_as_persona`` when
  set (the persona the holder presented when accepting the mission);
  fall back to the holder character's PRIMARY persona.
* ``contract_holder_only=False`` → fire on every participant's PRIMARY
  persona. Same ALL_EQUAL distribution as the flat-reward path; BY_ROLE
  / BY_PARTICIPATION rules remain stub-sealed.

Renown awards are independent of flat-reward emission — failing one
does not block the other. They run inside the same atomic resolution
block in ``services.resolution``, so partial failures roll back together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.constants import RewardGroupRule
from world.missions.models import MissionRenownAward

if TYPE_CHECKING:
    from world.missions.models import (
        MissionDeedRecord,
        MissionInstance,
        MissionOptionRoute,
    )
    from world.scenes.models import Persona
    from world.societies.renown import RenownAwardResult


_ERR_UNIMPLEMENTED_RULE = (
    "reward_group_rule={rule!r} is not implemented for renown emission; "
    "missions authored against it must wait for the broader BY_ROLE / "
    "BY_PARTICIPATION support that the flat-reward path also stub-seals."
)


def emit_terminal_renown_awards(
    instance: MissionInstance,
    route: MissionOptionRoute,
    deed: MissionDeedRecord,  # noqa: ARG001 — kept for signature symmetry with emit_terminal_rewards.
) -> list[RenownAwardResult]:
    """Fire ``fire_renown_award`` for each MissionRenownAward on ``route``.

    Returns the list of ``RenownAwardResult`` objects, useful for tests
    and downstream notification.

    No-ops when the route has no authored renown awards.

    Raises ``NotImplementedError`` when a broadcast renown award is
    authored on an instance with BY_ROLE / BY_PARTICIPATION distribution
    (stub-sealed parallel to the flat-reward side).
    """
    from django.db.models import Prefetch  # noqa: PLC0415

    from world.societies.models import PhilosophicalArchetype  # noqa: PLC0415

    awards = list(
        route.renown_awards.prefetch_related(
            Prefetch(
                "archetypes",
                queryset=PhilosophicalArchetype.objects.all(),
                to_attr="prefetched_archetypes",
            )
        )
    )
    if not awards:
        return []

    from world.missions.services.rewards import _ordered_participants  # noqa: PLC0415

    rule = instance.template.reward_group_rule
    participants = _ordered_participants(instance)

    results: list[RenownAwardResult] = []
    holder_persona_cache: Persona | None = None
    for award in awards:
        archetypes = list(award.prefetched_archetypes)
        if award.contract_holder_only:
            holder_persona_cache = holder_persona_cache or _resolve_holder_persona(
                instance, participants
            )
            if holder_persona_cache is None:
                continue
            results.append(_fire_award(award, holder_persona_cache, archetypes))
            continue
        # Broadcast — distribute per reward_group_rule.
        if rule != RewardGroupRule.ALL_EQUAL:
            raise NotImplementedError(_ERR_UNIMPLEMENTED_RULE.format(rule=rule))
        results.extend(
            _fire_award(award, _resolve_participant_persona(participant), archetypes)
            for participant in participants
        )
    return results


def _fire_award(
    award: MissionRenownAward,
    persona: Persona,
    archetypes: list,
) -> RenownAwardResult:
    """Fire one award on one persona."""
    from world.societies.renown import fire_renown_award  # noqa: PLC0415

    return fire_renown_award(
        persona=persona,
        magnitude=award.magnitude or None,
        risk=award.risk or None,
        archetypes=archetypes,
        reach=award.reach_override or None,
        title=_award_title(award),
    )


def _award_title(award: MissionRenownAward) -> str:
    """Human-readable title for the LegendEntry this award produces."""
    template = award.route.option.node.template
    return f"Mission deed: {template.name}"


def _resolve_holder_persona(
    instance: MissionInstance,
    participants: list,
) -> Persona | None:
    """Pick the persona to credit for a contract_holder_only award.

    Prefer ``MissionInstance.accepted_as_persona`` when set; fall back
    to the contract-holding participant's character's PRIMARY persona.
    Returns None when neither path resolves a persona.
    """
    if instance.accepted_as_persona_id is not None:
        return instance.accepted_as_persona
    holder = next((p for p in participants if p.is_contract_holder), None)
    if holder is None:
        return None
    return holder.character.sheet_data.primary_persona


def _resolve_participant_persona(participant: object) -> Persona:
    """Each broadcast recipient credits their PRIMARY persona.

    Broadcast renown distribution doesn't carry per-participant persona
    choice the way ``accepted_as_persona`` does for the holder.
    """
    return participant.character.sheet_data.primary_persona
