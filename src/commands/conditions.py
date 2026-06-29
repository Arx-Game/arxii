"""Telnet commands for condition treatment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.conditions.constants import TARGET_EFFECT_CONDITION
from world.conditions.services import get_treatment_candidates
from world.scenes.action_services import create_action_request
from world.scenes.interaction_services import get_active_scene
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from world.scenes.models import Persona

_NO_ARGS_MSG = "Usage: treat <character> [number]"
_NO_SCENE_MSG = "You are not in an active scene."
_NO_IDENTITY_MSG = "You have no character identity."
_TARGET_NO_IDENTITY_MSG = "{} has no character identity."
_INVALID_CANDIDATE_MSG = "Invalid candidate number."
_NO_CANDIDATES_MSG = "There are no treatable conditions on that character in this scene."


class CmdTreatCondition(ArxCommand):
    """Offer to treat another character's condition or pending alteration.

    Usage:
        treat <character>
        treat <character> <number>

    The first form lists candidates. The second attempts the numbered candidate.
    """

    key = "treat"
    locks = "cmd:all()"
    action = None

    def _execute(self) -> None:
        caller = self.caller
        args = (self.args or "").strip().split()
        if not args:
            raise CommandError(_NO_ARGS_MSG)

        scene = get_active_scene(caller.location)
        if scene is None:
            raise CommandError(_NO_SCENE_MSG)

        helper_sheet = caller.sheet_data
        if helper_sheet is None:
            raise CommandError(_NO_IDENTITY_MSG)
        initiator_persona = active_persona_for_sheet(helper_sheet)

        target_name = args[0]
        target = self.search_or_raise(target_name)
        target_sheet = target.sheet_data
        if target_sheet is None:
            raise CommandError(_TARGET_NO_IDENTITY_MSG.format(target))
        target_persona = active_persona_for_sheet(target_sheet)

        candidates = get_treatment_candidates(helper_sheet, target_sheet, scene)
        if not candidates:
            self.msg(_NO_CANDIDATES_MSG)
            return

        if len(args) == 1:
            self._list_candidates(candidates, target_persona)
            return

        try:
            index = int(args[1]) - 1
            candidate = candidates[index]
        except (ValueError, IndexError):
            raise CommandError(_INVALID_CANDIDATE_MSG) from None

        treatment = candidate["treatment"]
        target_effect = candidate["target_effect"]
        bond_thread = candidate.get("bond_thread")

        request = create_action_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            action_key="treat_condition",
        )
        request.treatment = treatment
        if candidate["target_effect_type"] == TARGET_EFFECT_CONDITION:
            request.target_condition_instance = target_effect
        else:
            request.target_pending_alteration = target_effect
        request.thread_used = bond_thread
        request.save(
            update_fields=[
                "treatment",
                "target_condition_instance",
                "target_pending_alteration",
                "thread_used",
            ]
        )

        self.msg(
            f"You offer to treat {target_persona.name} for {target_effect} with {treatment.name}. "
            f"Awaiting their response (request #{request.pk})."
        )

    def _list_candidates(self, candidates: list[dict[str, Any]], target_persona: Persona) -> None:
        lines = [f"Treatable conditions on {target_persona.name}:"]
        for i, candidate in enumerate(candidates, start=1):
            treatment = candidate["treatment"]
            effect = candidate["target_effect"]
            bond_note = " (requires bond thread)" if treatment.requires_bond else ""
            lines.append(f"{i}. {treatment.name} on {effect}{bond_note}")
        self.msg("\n".join(lines))
