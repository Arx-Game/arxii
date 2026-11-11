"""Her dodge settings: which technique answers, Soulfray, and the defensive pull (#5066).

The dodge itself is automatic (``world.combat.services.reactions``); the round's landing is
the ``combat_dodge`` plan. These are the standing answers that sit beside it:

- ``technique_id``: the technique that answers her automatic dodges in this fight (blank
  clears it, back to her saved default, else her strongest source). With ``save_default``
  true it also becomes her saved default for every fight (``CharacterTechnique
  .default_dodge``), which she may also set outside a fight.
- ``into_soulfray``: keep dodging when a dodge's cast would overspend into Soulfray. The
  Soulfray check-in on her turn writes this.
- ``auto_pull``: pull threads for defense the first time she is attacked in a round, with
  ``pull_tier`` naming the saved tier. It pulls every related thread of any resonance, each
  paid from its own resonance (maintainer ruling 2026-11-11).

Dispatch: REGISTRY ``registry_key="dodge_settings"``. Telnet: ``combat dodgewith``,
``combat dodgedefault`` and ``combat autopull`` (``commands/combat_maneuvers.py``); the
Soulfray answer is ``accept|decline dodgesoulfray`` (``world.combat.services.dodge_check_in``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatParticipant

TECHNIQUE_KWARG = "technique_id"
SAVE_DEFAULT_KWARG = "save_default"
INTO_SOULFRAY_KWARG = "into_soulfray"
AUTO_PULL_KWARG = "auto_pull"
PULL_TIER_KWARG = "pull_tier"

_NO_SUCH_TECHNIQUE = "None of your techniques that dodge is that one."
_NOT_IN_FIGHT = "You are not in a fight; only a saved default can be set."
_NOTHING_SET = "Say which dodge setting to change."
_BAD_PULL = "Pick a tier from 1 to 3 for the defensive pull."
_TIERS = (1, 2, 3)


def _dodging_technique_ids(actor: ObjectDB) -> list[int]:  # noqa: OBJECTDB_PARAM
    """Her techniques that match a dodging application, strongest first."""
    from world.areas.positioning.traversal import matched_movement  # noqa: PLC0415

    ids: list[int] = []
    for ms in matched_movement(actor):
        if ms.application.dodges and ms.technique_id is not None and ms.technique_id not in ids:
            ids.append(ms.technique_id)
    return ids


def _save_default(sheet_id: int, technique_id: int | None) -> None:
    """Make ``technique_id`` her one saved default dodge (None clears it)."""
    from django.db import transaction  # noqa: PLC0415

    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    with transaction.atomic():
        for hold in CharacterTechnique.objects.filter(character_id=sheet_id, default_dodge=True):
            hold.default_dodge = False
            hold.save(update_fields=["default_dodge"])
        if technique_id is not None:
            hold = CharacterTechnique.objects.get(character_id=sheet_id, technique_id=technique_id)
            hold.default_dodge = True
            hold.save(update_fields=["default_dodge"])


@dataclass
class DodgeSettingsAction(Action):
    """Set which technique answers her dodges, Soulfray, and the defensive pull (#5066)."""

    key: str = "dodge_settings"
    name: str = "Dodge settings"
    icon: str = "wind"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.definitions.combat_maneuvers import (  # noqa: PLC0415
            _active_combat_participant,
            _sheet,
        )
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        sheet = _sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_NOT_IN_FIGHT)
        participant = _active_combat_participant(
            actor, {RoundStatus.DECLARING, RoundStatus.RESOLVING}
        )
        messages: list[str] = []
        if TECHNIQUE_KWARG in kwargs:
            refusal = self._set_technique(actor, sheet.pk, participant, kwargs, messages)
            if refusal is not None:
                return ActionResult(success=False, message=refusal)
        in_fight_keys = (INTO_SOULFRAY_KWARG, AUTO_PULL_KWARG)
        if any(key in kwargs for key in in_fight_keys):
            if participant is None:
                return ActionResult(success=False, message=_NOT_IN_FIGHT)
            refusal = self._set_fight_answers(participant, kwargs, messages)
            if refusal is not None:
                return ActionResult(success=False, message=refusal)
        if not messages:
            return ActionResult(success=False, message=_NOTHING_SET)
        return ActionResult(success=True, message=" ".join(messages))

    @staticmethod
    def _set_technique(
        actor: ObjectDB,  # noqa: OBJECTDB_PARAM
        sheet_id: int,
        participant: CombatParticipant | None,
        kwargs: dict[str, Any],
        messages: list[str],
    ) -> str | None:
        from actions.kwarg_parsing import truthy_kwarg  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415

        raw = kwargs.get(TECHNIQUE_KWARG)
        technique = None
        if raw not in (None, ""):
            try:
                technique_id = int(raw)
            except (TypeError, ValueError):
                return _NO_SUCH_TECHNIQUE
            if technique_id not in _dodging_technique_ids(actor):
                return _NO_SUCH_TECHNIQUE
            technique = Technique.objects.get(pk=technique_id)
        save_default = truthy_kwarg(kwargs.get(SAVE_DEFAULT_KWARG, False))
        if participant is None and not save_default:
            return _NOT_IN_FIGHT
        if participant is not None:
            participant.dodge_technique = technique
            participant.save(update_fields=["dodge_technique"])
            messages.append(
                f"You'll dodge with {technique.name}."
                if technique is not None
                else "You'll dodge with your default."
            )
        if save_default:
            _save_default(sheet_id, technique.pk if technique is not None else None)
            messages.append(
                f"{technique.name} is your default dodge."
                if technique is not None
                else "You have no default dodge."
            )
        return None

    @staticmethod
    def _set_fight_answers(
        participant: CombatParticipant,
        kwargs: dict[str, Any],
        messages: list[str],
    ) -> str | None:
        from actions.kwarg_parsing import truthy_kwarg  # noqa: PLC0415

        fields: list[str] = []
        if INTO_SOULFRAY_KWARG in kwargs:
            participant.dodge_into_soulfray = truthy_kwarg(kwargs[INTO_SOULFRAY_KWARG])
            fields.append("dodge_into_soulfray")
            messages.append(
                "You'll keep dodging into Soulfray."
                if participant.dodge_into_soulfray
                else "You won't dodge when it would cost you Soulfray."
            )
        if AUTO_PULL_KWARG in kwargs:
            on = truthy_kwarg(kwargs[AUTO_PULL_KWARG])
            if on:
                refusal = _set_defense_pull(participant, kwargs, fields)
                if refusal is not None:
                    return refusal
            participant.auto_pull_defense = on
            fields.append("auto_pull_defense")
            messages.append(
                "You'll pull threads for defense when attacked."
                if on
                else "You won't pull threads for defense on your own."
            )
        participant.save(update_fields=fields)
        return None


def _set_defense_pull(
    participant: CombatParticipant,
    kwargs: dict[str, Any],
    fields: list[str],
) -> str | None:
    """Read the saved defensive pull's tier from ``kwargs``; keep the saved one when absent."""
    tier = kwargs.get(PULL_TIER_KWARG, participant.defense_pull_tier)
    try:
        tier = int(tier)
    except (TypeError, ValueError):
        return _BAD_PULL
    if tier not in _TIERS:
        return _BAD_PULL
    participant.defense_pull_tier = tier
    fields.append("defense_pull_tier")
    return None
