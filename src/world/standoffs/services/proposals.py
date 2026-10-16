"""GM-run standoffs: a firing cause becomes a proposal the GM decides (#4354).

A standoff is GM-run when its scene has a GM who has not muted standoff prompts
(``prompt_recipients`` for ``STANDOFF_CAUSE``), whether a story beat or a mission opened
it. Derived, never stored. There, a cause that fires does not start the fight: the group
goes PROPOSED and each such GM gets a ``STANDOFF_CAUSE`` prompt. The GM confirms (the
fight begins, NPC-initiated), holds for one action (the cause is tested again after the
next action) or overrides with a reason (not tested again until force moves or a botch
lands). Players keep acting while it is pending.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import CauseKind
from world.gm.constants import GMPromptKind, GMPromptStatus
from world.standoffs.constants import ProposalResolution, StandoffGroupState
from world.standoffs.services.state import end_standoff_into_fight, flush_cache_on_error

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.combat.models import CombatEncounter
    from world.gm.models import GMPrompt
    from world.standoffs.models import StandoffGroup

_MSG_NOT_STANDOFF = "That prompt is not a standoff proposal."
_MSG_CLOSED = "That prompt has already been dealt with."
_MSG_MOVED_ON = "That standoff has moved on; the proposal no longer stands."
_MSG_NEED_REASON = "Give a reason to override."
NOTE_MOVED_ON = "The standoff moved on before a decision."


@dataclass(frozen=True)
class ProposalOutcome:
    """What resolving a proposal did; ``success`` is False when it was refused."""

    success: bool
    message: str
    fight_started: bool = False


def standoff_is_gm_run(encounter: CombatEncounter) -> bool:
    """True when the encounter's scene has a GM who wants standoff prompts."""
    from world.gm.prompt_services import prompt_recipients  # noqa: PLC0415

    return bool(prompt_recipients(encounter.scene, GMPromptKind.STANDOFF_CAUSE))


def propose(group: StandoffGroup, reason: str) -> bool:
    """Route a STANDOFF_CAUSE prompt to the scene's GMs and mark the group PROPOSED.

    False when no GM took the prompt (nobody wants it after all), so the caller starts the
    fight as a mission would.
    """
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415

    prompts = route_narratable_event(
        NarratableEvent(
            kind=GMPromptKind.STANDOFF_CAUSE,
            scene=group.encounter.scene,
            character_sheet=None,
            standoff_group=group,
        )
    )
    if not prompts:
        return False
    group.state = StandoffGroupState.PROPOSED
    group.proposal_reason = reason
    group.save(update_fields=["state", "proposal_reason"])
    return True


def restate_proposal(group: StandoffGroup, reason: str) -> None:
    """A PROPOSED group's cause fired again: the prompt now states the latest reason."""
    if group.proposal_reason != reason:
        group.proposal_reason = reason
        group.save(update_fields=["proposal_reason"])


def pending_prompts(group: StandoffGroup) -> list[GMPrompt]:
    """The group's still-pending proposal prompts, one per addressed GM."""
    from world.gm.models import GMPrompt  # noqa: PLC0415

    return list(
        GMPrompt.objects.filter(
            standoff_group=group,
            kind=GMPromptKind.STANDOFF_CAUSE,
            status=GMPromptStatus.PENDING,
        )
    )


def _close_prompts(
    prompts: list[GMPrompt], *, status: str, note: str, resolver: AccountDB | None
) -> None:
    for prompt in prompts:
        prompt.status = status
        prompt.resolution_note = note
        prompt.resolved_by = resolver
        prompt.save(update_fields=["status", "resolution_note", "resolved_by"])


def close_group_prompts(group: StandoffGroup, note: str) -> None:
    """Close the group's pending proposals because the standoff moved on without the GM."""
    _close_prompts(
        pending_prompts(group), status=GMPromptStatus.DISMISSED, note=note, resolver=None
    )


def force_line(group: StandoffGroup) -> str:
    """The force on both sides as the GM reads it: party, group, and emboldening."""
    from world.standoffs.models import StandoffConfig  # noqa: PLC0415
    from world.standoffs.services.force import group_force, party_force  # noqa: PLC0415

    config = StandoffConfig.load()
    party = round(party_force(group.encounter, config), 1)
    theirs = round(group_force(group, config), 1)
    bands = group.emboldened_bands
    line = f"Force: party {party:g}, them {theirs:g}"
    if bands:
        line += f", emboldened {bands} band{'s' if bands != 1 else ''}"
    return f"{line}."


def last_decision(group: StandoffGroup) -> str:
    """The GM's most recent decision on this group's proposals, or ""."""
    from world.gm.models import GMPrompt  # noqa: PLC0415

    prompt = (
        GMPrompt.objects.filter(standoff_group=group, kind=GMPromptKind.STANDOFF_CAUSE)
        .exclude(status=GMPromptStatus.PENDING)
        .exclude(resolution_note="")
        .order_by("-created_at", "-pk")
        .first()
    )
    return prompt.resolution_note if prompt is not None else ""


def proposal_summary(group: StandoffGroup) -> str:
    """One line for the GM: the group, its cause, why it fired, and the force."""
    from world.standoffs.services.profile import group_cause  # noqa: PLC0415

    cause = CauseKind(group_cause(group)[0]).label
    reason = group.proposal_reason or "Its cause holds."
    return (
        f"{group.creature_template.name}: cause fires. Cause: {cause}. Reason: {reason} "
        f"{force_line(group)}"
    )


def _encounter_of_prompt(prompt: GMPrompt, *_: object, **__: object) -> CombatEncounter:
    group = prompt.standoff_group
    if group is None:  # pragma: no cover - guarded before any write
        msg = "proposal prompt has no group"
        raise ValueError(msg)
    return group.encounter


def resolve_proposal(
    prompt: GMPrompt,
    resolution: str,
    *,
    resolver: AccountDB | None,
    reason: str = "",
) -> ProposalOutcome:
    """Apply a GM's decision on a standoff proposal. Authorization is the caller's job.

    Confirm starts the fight as the NPCs' own act. Hold returns the group to OPEN; the next
    action tests the cause again. Override returns it to OPEN with ``reason`` recorded on
    the prompt and the current force noted, so the cause is not tested again until force
    moves or a botch lands. Every pending prompt for the group closes together (one per GM
    it was routed to). A proposal the standoff has already moved past closes with nothing
    else done.
    """
    if prompt.kind != GMPromptKind.STANDOFF_CAUSE or prompt.standoff_group_id is None:
        return ProposalOutcome(False, _MSG_NOT_STANDOFF)
    reason = reason.strip()
    if resolution == ProposalResolution.OVERRIDE and not reason:
        return ProposalOutcome(False, _MSG_NEED_REASON)
    return _resolve_locked(prompt, resolution, resolver=resolver, reason=reason)


@flush_cache_on_error(_encounter_of_prompt)
@transaction.atomic
def _resolve_locked(
    prompt: GMPrompt, resolution: str, *, resolver: AccountDB | None, reason: str
) -> ProposalOutcome:
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.gm.models import GMPrompt  # noqa: PLC0415
    from world.standoffs.models import StandoffGroup  # noqa: PLC0415

    group = prompt.standoff_group
    encounter = CombatEncounter.objects.select_for_update().get(pk=group.encounter_id)
    encounter.refresh_from_db()
    group = StandoffGroup.objects.select_for_update().get(pk=group.pk)
    group.refresh_from_db()
    locked_prompt = GMPrompt.objects.select_for_update().get(pk=prompt.pk)
    locked_prompt.refresh_from_db()
    if locked_prompt.status != GMPromptStatus.PENDING:
        return ProposalOutcome(False, _MSG_CLOSED)
    prompts = pending_prompts(group)
    if group.state != StandoffGroupState.PROPOSED or encounter.round_number != 0:
        _close_prompts(
            prompts, status=GMPromptStatus.DISMISSED, note=NOTE_MOVED_ON, resolver=resolver
        )
        return ProposalOutcome(False, _MSG_MOVED_ON)
    if resolution == ProposalResolution.CONFIRM:
        _close_prompts(
            prompts,
            status=GMPromptStatus.CONFIRMED,
            note="Confirmed: they attack.",
            resolver=resolver,
        )
        started = end_standoff_into_fight(encounter, initiated_by_pc_side=False)
        return ProposalOutcome(True, "They attack.", fight_started=started)
    group.state = StandoffGroupState.OPEN
    if resolution == ProposalResolution.HOLD:
        note = "Held for one action."
        group.save(update_fields=["state"])
    else:
        from world.standoffs.models import StandoffConfig  # noqa: PLC0415
        from world.standoffs.services.force import (  # noqa: PLC0415
            effective_party_force,
            group_force,
        )

        config = StandoffConfig.load()
        group.override_party_force = effective_party_force(encounter, group, config)
        group.override_group_force = group_force(group, config)
        group.save(update_fields=["state", "override_party_force", "override_group_force"])
        note = f"Overridden: {reason}"
    _close_prompts(prompts, status=GMPromptStatus.DISMISSED, note=note, resolver=resolver)
    return ProposalOutcome(True, note)
