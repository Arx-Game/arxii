"""GM combat-encounter lifecycle actions (#1494).

These actions expose the same lifecycle seams as the web ``CombatEncounterViewSet``
(begin round, resolve round, add/remove participants/opponents, pause, end, and
preview opponent defaults). They are gated to the encounter's scene GM or staff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import (
    resolve_actor_or_error,
    resolve_character_sheet_in_room,
    resolve_model_by_pk_or_name,
)
from world.combat.constants import OpponentTier
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter, CombatParticipant
    from world.combat.scaling import OpponentStatBlock


# Encounter statuses that represent an ongoing (non-completed) combat.
_ACTIVE_ENCOUNTER_STATUSES: frozenset[str] = frozenset(
    {
        RoundStatus.DECLARING,
        RoundStatus.RESOLVING,
        RoundStatus.BETWEEN_ROUNDS,
    }
)

_NO_ACTIVE_ENCOUNTER = "There is no active encounter here."
_NO_GM_PERMISSION = "Only the scene's GM or staff can do that."


def _active_encounter_in_room(actor: ObjectDB) -> CombatEncounter | None:
    """Return the newest non-completed combat encounter in *actor*'s room."""
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    room = actor.location
    if room is None:
        return None
    return (
        CombatEncounter.objects.filter(
            room=room,
            status__in=_ACTIVE_ENCOUNTER_STATUSES,
        )
        .select_related("scene")
        .order_by("-created_at")
        .first()
    )


def _resolve_account(actor: ObjectDB) -> AccountDB | None:
    """Return the actor's controlling account, or None if there isn't one."""
    try:
        return resolve_actor_or_error(actor)
    except CommandError:
        return None


def _actor_may_gm_encounter(actor: ObjectDB, encounter: CombatEncounter) -> bool:
    """True when *actor* is staff or the GM of *encounter*'s scene."""
    account = _resolve_account(actor)
    if account is None:
        return False
    if account.is_staff:
        return True
    return encounter.scene.is_gm(account)


def _resolve_participant_in_encounter(
    encounter: CombatEncounter,
    value: str,
) -> CombatParticipant:
    """Resolve a participant by PK or by their character's display name."""
    from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist  # noqa: PLC0415

    from world.combat.models import CombatParticipant  # noqa: PLC0415

    queryset = CombatParticipant.objects.filter(encounter=encounter)
    not_found_msg = f"No participant named {value!r} in this encounter."

    try:
        if value.isdigit():
            participant = queryset.get(pk=value)
        else:
            participant = queryset.get(character_sheet__character__db_key__iexact=value)
    except (ObjectDoesNotExist, MultipleObjectsReturned) as exc:
        raise CommandError(not_found_msg) from exc

    return participant


def _permission_failure_result(encounter: CombatEncounter | None) -> ActionResult:
    """Return a consistent failure result when an actor lacks GM rights."""
    if encounter is None:
        return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
    return ActionResult(success=False, message=_NO_GM_PERMISSION)


@dataclass
class BeginEncounterRoundAction(Action):
    """Advance the active encounter from BETWEEN_ROUNDS to DECLARING."""

    key: str = "begin_encounter_round"
    name: str = "Begin Encounter Round"
    icon: str = "play-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import begin_declaration_phase  # noqa: PLC0415

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)

        try:
            begin_declaration_phase(encounter)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="Round begins.")


@dataclass
class ResolveEncounterRoundAction(Action):
    """Resolve the current round of the active encounter."""

    key: str = "resolve_encounter_round"
    name: str = "Resolve Encounter Round"
    icon: str = "fast-forward"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.errors import ActionDispatchError  # noqa: PLC0415
        from world.combat.services import resolve_round  # noqa: PLC0415

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)
        if encounter.status != RoundStatus.DECLARING:
            return ActionResult(
                success=False,
                message="The encounter is not gathering declarations.",
            )

        try:
            resolve_round(encounter)
        except (ValueError, ActionDispatchError) as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="The round resolves.")


@dataclass
class AddOpponentAction(Action):
    """Add an NPC opponent to the active encounter."""

    key: str = "add_opponent"
    name: str = "Add Opponent"
    icon: str = "skull"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.models import ThreatPool  # noqa: PLC0415
        from world.combat.services import add_opponent  # noqa: PLC0415

        result: ActionResult | None = None
        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            result = ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        elif not _actor_may_gm_encounter(actor, encounter):
            result = _permission_failure_result(encounter)

        name = kwargs.get("name")
        tier = kwargs.get("tier")
        threat_pool_id = kwargs.get("threat_pool_id")
        description = kwargs.get("description", "")

        if result is None and (not name or not tier or threat_pool_id is None):
            result = ActionResult(
                success=False,
                message="Name, tier, and threat pool are required.",
            )
        if result is None and tier not in OpponentTier.values:
            result = ActionResult(success=False, message="Invalid opponent tier.")

        if result is None:
            try:
                pool = resolve_model_by_pk_or_name(
                    ThreatPool,
                    str(threat_pool_id),
                    not_found_msg=f"No threat pool named {threat_pool_id!r} found.",
                )
            except CommandError as err:
                result = ActionResult(success=False, message=str(err))

        if result is None:
            try:
                opponent = add_opponent(
                    encounter,
                    name=name,
                    tier=tier,
                    threat_pool=pool,
                    description=description,
                )
            except ValueError as err:
                result = ActionResult(success=False, message=str(err))
            else:
                result = ActionResult(
                    success=True,
                    message=f"Opponent '{opponent.name}' added to the encounter.",
                )

        return result


@dataclass
class AddEncounterParticipantAction(Action):
    """Add a PC participant to the active encounter."""

    key: str = "add_encounter_participant"
    name: str = "Add Encounter Participant"
    icon: str = "user-plus"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        character_sheet_id: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import add_participant  # noqa: PLC0415

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)
        if character_sheet_id is None:
            return ActionResult(success=False, message="A character is required.")

        try:
            sheet = resolve_character_sheet_in_room(
                actor,
                str(character_sheet_id),
                room=encounter.room,
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            add_participant(encounter, sheet)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))

        return ActionResult(
            success=True,
            message=f"{sheet.character.db_key} added to the encounter.",
        )


@dataclass
class RemoveEncounterParticipantAction(Action):
    """Remove a PC participant from the active encounter."""

    key: str = "remove_encounter_participant"
    name: str = "Remove Encounter Participant"
    icon: str = "user-minus"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        participant_id: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import remove_participant  # noqa: PLC0415

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)
        if participant_id is None:
            return ActionResult(success=False, message="A participant is required.")

        try:
            participant = _resolve_participant_in_encounter(encounter, str(participant_id))
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            remove_participant(participant)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))

        return ActionResult(
            success=True,
            message=f"{participant.character_sheet.character.db_key} removed from the encounter.",
        )


@dataclass
class PauseEncounterAction(Action):
    """Pause or resume the active encounter's timer."""

    key: str = "pause_encounter"
    name: str = "Pause Encounter"
    icon: str = "pause-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)

        encounter.is_paused = not encounter.is_paused
        encounter.save(update_fields=["is_paused"])
        if encounter.is_paused:
            return ActionResult(success=True, message="Encounter paused.")
        return ActionResult(success=True, message="Encounter resumed.")


@dataclass
class EndEncounterAction(Action):
    """Force-end the active encounter as ABANDONED."""

    key: str = "end_encounter"
    name: str = "End Encounter"
    icon: str = "stop-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import end_encounter  # noqa: PLC0415

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)
        if encounter.status == RoundStatus.COMPLETED:
            return ActionResult(success=False, message="Encounter already completed.")

        try:
            end_encounter(encounter)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="Encounter ended.")


@dataclass
class PreviewOpponentDefaultsAction(Action):
    """Preview the scaling formula output for a tier without mutating state."""

    key: str = "preview_opponent_defaults"
    name: str = "Preview Opponent Defaults"
    icon: str = "eye"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def _tier_label(self, tier: str) -> str:
        return dict(OpponentTier.choices).get(tier, tier)

    def _format_preview(
        self,
        tier: str,
        block: OpponentStatBlock,
        stakes_ok: bool,
        stakes_message: str,
    ) -> str:
        lines = [
            f"Tier: {self._tier_label(tier)}",
            f"Max health: {block.max_health}",
            f"Soak: {block.soak_value}",
        ]
        if block.probing_threshold is not None:
            lines.append(f"Probing threshold: {block.probing_threshold}")
        if block.swarm_count is not None:
            lines.append(f"Swarm count: {block.swarm_count}")
        if block.body_toughness is not None:
            lines.append(f"Body toughness: {block.body_toughness}")
        if block.bodies_per_attack is not None:
            lines.append(f"Bodies per attack: {block.bodies_per_attack}")
        if block.barrier_strength is not None:
            lines.append(f"Barrier strength: {block.barrier_strength}")
        if block.phases:
            lines.append(f"Boss phases: {len(block.phases)}")
        if stakes_message:
            lines.append(f"Stakes gate: {stakes_message}")
        else:
            lines.append(f"Stakes gate: {'OK' if stakes_ok else 'Blocked'}")
        return "\n".join(lines)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        tier: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.models import OpponentTierTemplate  # noqa: PLC0415
        from world.combat.scaling import (  # noqa: PLC0415
            StakesRequirementError,
            compute_opponent_stat_block,
            validate_stakes_requirement,
        )

        encounter = _active_encounter_in_room(actor)
        if encounter is None:
            return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
        if not _actor_may_gm_encounter(actor, encounter):
            return _permission_failure_result(encounter)
        if tier is None or tier not in OpponentTier.values:
            return ActionResult(success=False, message="Invalid opponent tier.")

        try:
            block = compute_opponent_stat_block(tier, encounter)
        except OpponentTierTemplate.DoesNotExist:
            return ActionResult(
                success=False,
                message="Scaling template for that tier is not configured.",
            )

        account = _resolve_account(actor)
        stakes_ok = True
        stakes_message = ""
        if account is not None:
            try:
                validate_stakes_requirement(encounter, account)
            except StakesRequirementError as exc:
                stakes_ok = False
                stakes_message = exc.user_message

        message = self._format_preview(tier, block, stakes_ok, stakes_message)
        return ActionResult(success=True, message=message)
