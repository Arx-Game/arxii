"""Combat implementation of the RoundContext seam.

Provides ``CombatRoundContext`` (wrapping a ``CombatParticipant`` and its
``CombatEncounter``) and ``resolve_combat_round_context`` (the resolver
consulted by ``actions.round_context.get_active_round_context``).

Character → participant resolution mirrors the canonical path already used
in ``world.combat.views.CombatEncounterViewSet._get_participant``:

    participant.character_sheet  →  CharacterSheet (the FK on CombatParticipant)

The resolver goes the reverse direction:

    CharacterSheet  →  CombatParticipant.objects.filter(
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
        encounter__status__in=<non-completed statuses>,
    )

The ``encounter__status`` exclusion of COMPLETED matches the project intent
that a COMPLETED encounter is no longer "active" — participants in it should
not be declaration-gated.

If somehow a character is an ACTIVE participant in multiple non-completed
encounters (should not happen with current service logic but is possible if
two encounters are created manually), the resolver picks the most recently
created encounter (``encounter__created_at`` descending) to be deterministic
rather than silently picking the first arbitrary DB row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.round_context import RoundContext
from world.character_sheets.models import CharacterSheet
from world.combat.constants import ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    RoundChallengeDeclaration,
)
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

# Encounter statuses that represent an ongoing (non-completed) combat.
_ACTIVE_ENCOUNTER_STATUSES: frozenset[str] = frozenset(
    {
        RoundStatus.DECLARING,
        RoundStatus.RESOLVING,
        RoundStatus.BETWEEN_ROUNDS,
    }
)


def resolve_focused_target_objectdb(
    encounter: CombatEncounter,
    kwargs: dict[str, Any],
) -> ObjectDB | None:
    """Resolve the live focused-target ``ObjectDB`` from raw declaration kwargs (#1831).

    Reads ``focused_opponent_target_id`` / ``focused_ally_target_id`` straight off
    *kwargs* (the same keys ``_resolve_focused_targets`` reads once the declaration
    itself is recorded), scoped to *encounter* so a forged/stale id from another
    encounter cannot resolve. The focused OPPONENT wins over the focused ALLY when
    both are somehow present — this only decides *which* live target feeds pull
    modulation; ``court_regard_modulation`` reads directionality off the effect
    row's ``RegardPolarity``, not off which kwarg fired.

    Shared by both combat-pull commit seams (``CastTechniqueAction._commit_combat_pull``
    and ``_dispatch_clash_contribution``'s cast-pull leg) so the resolution logic is
    not duplicated. Unlike ``_resolve_focused_targets``, an unresolvable id here
    silently returns ``None`` rather than raising — this call happens at pull-commit
    time, before the declaration's own id validation runs, and feeds a bonus
    modulation input rather than gating anything.

    Args:
        encounter: The encounter to scope target lookups to.
        kwargs: Raw declaration kwargs; only the two focused-target id keys are read.

    Returns:
        The resolved target's ``ObjectDB``, or ``None`` when neither kwarg is
        present, or the id does not resolve within *encounter*.
    """
    opponent_id = kwargs.get("focused_opponent_target_id")
    if opponent_id is not None:
        opponent = CombatOpponent.objects.filter(pk=opponent_id, encounter=encounter).first()
        if opponent is not None and opponent.objectdb is not None:
            return opponent.objectdb

    ally_id = kwargs.get("focused_ally_target_id")
    if ally_id is not None:
        ally = CombatParticipant.objects.filter(pk=ally_id, encounter=encounter).first()
        if ally is not None:
            return ally.character_sheet.character

    return None


# kwargs key for effort level — used as a guard and a lookup in _record_combat_declaration.
_EFFORT_LEVEL_KEY: str = "effort_level"


class CombatRoundContext(RoundContext):
    """``RoundContext`` backed by a live ``CombatParticipant`` + ``CombatEncounter``.

    Wraps the participant (which carries the encounter FK) so that
    ``round_id`` and ``is_declaration_open`` can be read without additional
    queries when the participant is already identity-mapped.
    """

    def __init__(self, participant: CombatParticipant) -> None:
        self._participant = participant
        # Cache the encounter on first access via the SharedMemoryModel
        # identity map — no second query if the encounter is already loaded.
        self._encounter = participant.encounter

    @property
    def participant(self) -> CombatParticipant:
        """Return the resolved ``CombatParticipant`` for this context."""
        return self._participant

    @property
    def round_id(self) -> tuple[int, int]:
        """Return ``(encounter_id, round_number)`` for this active round."""
        return (self._encounter.pk, self._encounter.round_number)

    @property
    def is_declaration_open(self) -> bool:
        """True when the encounter is in the DECLARING phase."""
        return self._encounter.status == RoundStatus.DECLARING

    def is_repeat_blocked(
        self,
        actor: CharacterSheet,  # noqa: ARG002
        action_ref: Any,  # noqa: ARG002
        target_persona: Any,  # noqa: ARG002
    ) -> bool:
        # STRICT: declaration window governs; immediate repeats are never allowed mid-round.
        return not self.is_declaration_open

    def record_declaration(
        self,
        character: CharacterSheet,  # noqa: ARG002
        # player_action: PlayerAction from actions.types
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Record a participant's declared action for the current round.

        Enforces mutual exclusion: COMBAT declarations delete any existing
        RoundChallengeDeclaration; CHALLENGE declarations delete any existing
        CombatRoundAction. Only one declared action type is permitted per
        (encounter, round, participant).

        Args:
            character: The CharacterSheet of the acting character (unused for
                lookup — ``self._participant`` is already resolved).
            player_action: A ``PlayerAction`` carrying backend + ref.
            kwargs: Extra dispatch kwargs forwarded to the backend handler
                (e.g. ``effort_level`` for COMBAT).

        Raises:
            ActionDispatchError: With ``ROUND_DECLARATION_CLOSED`` if the
                encounter is not in DECLARING status.
            ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if backend is
                REGISTRY (registry actions are not round-declared).
        """
        if not self.is_declaration_open:
            raise ActionDispatchError(ActionDispatchError.ROUND_DECLARATION_CLOSED)

        participant = self._participant
        backend: str = player_action.backend

        if backend == ActionBackend.COMBAT:
            self._record_combat_declaration(participant, player_action, kwargs)
        elif backend == ActionBackend.CHALLENGE:
            self._record_challenge_declaration(participant, player_action)
        else:
            # REGISTRY actions are immediate utility; they are never round-declared.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    def _merge_slot_into_existing(
        self,
        slot: str,
        technique: Any,
        existing: CombatRoundAction | None,
        kwargs: dict[str, Any],
    ) -> tuple[
        Any, Any, Any, Any, CombatOpponent | None, CombatParticipant | None, list, dict[str, Any]
    ]:
        """Apply the named slot's technique onto the existing CombatRoundAction's slots.

        Reads the existing row's slot values, overwrites only the slot this
        dispatch names, and returns the merged
        ``(focused, physical, social, mental, opponent_target, ally_target,
        aoe_opponents, cast_positions)``.

        ``aoe_opponents`` is the full ordered opponent list for AoE/FILTERED_GROUP
        dispatches (empty for SINGLE/SELF).  The caller writes
        ``CombatRoundActionTarget`` join rows from this list.

        ``cast_positions`` is the ``resolve_cast_position_params`` result dict
        (``cast_destination``/``cast_position_a``/``cast_position_b``). Like the
        opponent/ally targets, declared positions belong to the focused slot only
        and are preserved across passive-only merges.
        """
        from actions.constants import CombatActionSlot  # noqa: PLC0415
        from world.combat.constants import ActionCategory  # noqa: PLC0415

        focused = existing.focused_action if existing else None
        physical = existing.physical_passive if existing else None
        social = existing.social_passive if existing else None
        mental = existing.mental_passive if existing else None
        # Targets belong to the focused slot only. Preserve them across passive
        # merges; a FOCUSED dispatch re-supplies them from its own kwargs.
        opponent_target = existing.focused_opponent_target if existing else None
        ally_target = existing.focused_ally_target if existing else None
        aoe_opponents: list[CombatOpponent] = []
        cast_positions: dict[str, Any] = {
            "cast_destination": existing.cast_destination if existing else None,
            "cast_position_a": existing.cast_position_a if existing else None,
            "cast_position_b": existing.cast_position_b if existing else None,
        }

        if slot == CombatActionSlot.FOCUSED:
            focused = technique
            opponent_target, ally_target, aoe_opponents = self._resolve_focused_targets(kwargs)
            cast_positions = self._resolve_cast_positions(technique, kwargs)
            # XOR authority lives on the backend: the just-declared focused action
            # WINS over any previously-declared passive in the same category, so we
            # clear that colliding passive before declare_action validates. This
            # enforces the XOR regardless of dispatch arrival order (focused-first
            # OR passive-first).
            category = technique.action_category
            if category == ActionCategory.PHYSICAL:
                physical = None
            elif category == ActionCategory.SOCIAL:
                social = None
            elif category == ActionCategory.MENTAL:
                mental = None
        elif slot == CombatActionSlot.PASSIVE_PHYSICAL:
            physical = technique
        elif slot == CombatActionSlot.PASSIVE_SOCIAL:
            social = technique
        elif slot == CombatActionSlot.PASSIVE_MENTAL:
            mental = technique

        return (
            focused,
            physical,
            social,
            mental,
            opponent_target,
            ally_target,
            aoe_opponents,
            cast_positions,
        )

    def _resolve_cast_positions(
        self,
        technique: Any,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate+resolve ``kwargs["position_params"]`` into cast position FKs.

        Empty/absent ``position_params`` resolves to all-None (no positions
        declared). Raises ``ActionDispatchError`` on invalid input — same error
        path as ``_resolve_focused_targets`` for an unresolvable ally id (#2206).
        """
        position_params = kwargs.get("position_params")
        if not position_params:
            return {"cast_destination": None, "cast_position_a": None, "cast_position_b": None}

        from world.combat.services import resolve_cast_position_params  # noqa: PLC0415

        return resolve_cast_position_params(self._participant, technique, position_params)

    @transaction.atomic
    def _record_combat_declaration(
        self,
        participant: CombatParticipant,
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Upsert a CombatRoundAction and clear any competing challenge declaration."""
        from world.magic.models import Technique  # noqa: PLC0415

        if _EFFORT_LEVEL_KEY not in kwargs:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

        # Clear any prior challenge declaration for this (encounter, round, participant).
        RoundChallengeDeclaration.objects.filter(
            encounter=self._encounter,
            round_number=self._encounter.round_number,
            participant=participant,
        ).delete()

        try:
            technique = Technique.objects.get(pk=player_action.ref.technique_id)
        except Technique.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        from actions.constants import CombatActionSlot  # noqa: PLC0415
        from world.combat.services import declare_action  # noqa: PLC0415
        from world.fatigue.constants import EffortLevel  # noqa: PLC0415

        # The frontend dispatches the focused action and each passive as SEPARATE
        # /dispatch/ calls, every one routing through here. To land them all on a
        # single CombatRoundAction row we read the existing row, apply only the
        # slot this call names, and write the merged full row back through
        # declare_action (which itself does a full-row update_or_create).
        slot = player_action.ref.action_slot or CombatActionSlot.FOCUSED

        existing = CombatRoundAction.objects.filter(
            participant=participant,
            round_number=self._encounter.round_number,
        ).first()

        (
            focused,
            physical,
            social,
            mental,
            opponent_target,
            ally_target,
            aoe_opponents,
            cast_positions,
        ) = self._merge_slot_into_existing(slot, technique, existing, kwargs)

        effort = (
            kwargs.get(_EFFORT_LEVEL_KEY)
            or (existing.effort_level if existing else None)
            or EffortLevel.MEDIUM
        )

        confirm_soulfray_risk: bool = bool(kwargs.get("confirm_soulfray_risk", False))

        fury_commitment = None
        fury_commitment_id = kwargs.get("fury_commitment_id")
        if fury_commitment_id is not None:
            from world.magic.models import FuryTier  # noqa: PLC0415

            fury_commitment = FuryTier.objects.filter(pk=fury_commitment_id).first()

        fury_anchor = None
        fury_anchor_id = kwargs.get("fury_anchor_id")
        if fury_anchor_id is not None:
            from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

            fury_anchor = CharacterSheet.objects.filter(pk=fury_anchor_id).first()

        action = declare_action(
            participant,
            focused_action=focused,
            focused_category=None,
            effort_level=effort,
            focused_opponent_target=opponent_target,
            focused_ally_target=ally_target,
            physical_passive=physical,
            social_passive=social,
            mental_passive=mental,
            confirm_soulfray_risk=confirm_soulfray_risk,
            fury_commitment=fury_commitment,
            fury_anchor=fury_anchor,
            cast_destination=cast_positions["cast_destination"],
            cast_position_a=cast_positions["cast_position_a"],
            cast_position_b=cast_positions["cast_position_b"],
        )

        # AoE / FILTERED_GROUP: persist the full target set as join rows so the
        # resolver can iterate them without a round-trip to the declaration kwargs.
        # Always clear then re-insert so a re-declaration stays consistent.
        if aoe_opponents:
            action.extra_targets.all().delete()
            CombatRoundActionTarget.objects.bulk_create(
                [CombatRoundActionTarget(action=action, opponent=opp) for opp in aoe_opponents]
            )

    def _resolve_aoe_opponents(
        self,
        opponent_ids: list[int],
    ) -> list[CombatOpponent]:
        """Validate and order the AoE opponent id list against this encounter.

        Raises ActionDispatchError(UNKNOWN_ACTION_REF) if any id is not in this encounter.
        """
        resolved = list(
            CombatOpponent.objects.filter(pk__in=opponent_ids, encounter=self._encounter)
        )
        resolved_map = {o.pk: o for o in resolved}
        ordered: list[CombatOpponent] = []
        for oid in opponent_ids:
            if oid not in resolved_map:
                raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
            ordered.append(resolved_map[oid])
        return ordered

    def _resolve_single_opponent(self, opponent_id: int) -> CombatOpponent:
        """Resolve a single CombatOpponent PK scoped to this encounter.

        Raises ActionDispatchError(UNKNOWN_ACTION_REF) if the id is not found.
        """
        try:
            return CombatOpponent.objects.get(pk=opponent_id, encounter=self._encounter)
        except CombatOpponent.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

    def _resolve_focused_targets(
        self,
        kwargs: dict[str, Any],
    ) -> tuple[CombatOpponent | None, CombatParticipant | None, list[CombatOpponent]]:
        """Resolve the focused target ids supplied by the player dispatch.

        The frontend sends ``focused_opponent_target_id`` (a ``CombatOpponent`` PK)
        or ``focused_ally_target_id`` (a ``CombatParticipant`` PK) in the COMBAT
        dispatch kwargs.  Both are resolved **scoped to this context's encounter**
        so a forged/stale id from another encounter cannot be targeted.  Already-
        resolved instance kwargs (``focused_opponent_target`` /
        ``focused_ally_target``) take precedence when present, so direct callers
        can pass instances.

        For AoE / FILTERED_GROUP techniques the caller may supply
        ``focused_opponent_target_ids`` (a list of ``CombatOpponent`` PKs).  All
        ids are validated against this encounter.  The **first** resolved opponent
        is returned as the primary ``opponent`` (set on
        ``CombatRoundAction.focused_opponent_target``) for backward-compat; the
        full list is returned as the third element so the caller can persist join
        rows via ``CombatRoundActionTarget``.

        Returns:
            ``(primary_opponent, ally, extra_opponents)`` where ``extra_opponents``
            is the full ordered list for AoE (may be empty for SINGLE / SELF).

        Raises:
            ActionDispatchError: ``UNKNOWN_ACTION_REF`` if a supplied id does not
                resolve to an entity in this encounter.
        """
        opponent: CombatOpponent | None = kwargs.get("focused_opponent_target")
        opponent_ids: list[int] | None = kwargs.get("focused_opponent_target_ids")
        aoe_opponents: list[CombatOpponent] = []

        if opponent_ids:
            aoe_opponents = self._resolve_aoe_opponents(opponent_ids)
            if aoe_opponents and opponent is None:
                opponent = aoe_opponents[0]
        else:
            opponent_id = kwargs.get("focused_opponent_target_id")
            if opponent is None and opponent_id is not None:
                opponent = self._resolve_single_opponent(opponent_id)

        ally: CombatParticipant | None = kwargs.get("focused_ally_target")
        ally_id = kwargs.get("focused_ally_target_id")
        if ally is None and ally_id is not None:
            try:
                ally = CombatParticipant.objects.get(
                    pk=ally_id,
                    encounter=self._encounter,
                )
            except CombatParticipant.DoesNotExist as exc:
                raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        return opponent, ally, aoe_opponents

    @transaction.atomic
    def _record_challenge_declaration(
        self,
        participant: CombatParticipant,
        player_action: Any,
    ) -> None:
        """Upsert a RoundChallengeDeclaration and clear any competing round action."""
        from world.mechanics.models import ChallengeApproach, ChallengeInstance  # noqa: PLC0415

        # Clear any prior combat round action for this (participant, round).
        CombatRoundAction.objects.filter(
            participant=participant,
            round_number=self._encounter.round_number,
        ).delete()

        try:
            challenge_instance = ChallengeInstance.objects.get(
                pk=player_action.ref.challenge_instance_id
            )
        except ChallengeInstance.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        try:
            challenge_approach = ChallengeApproach.objects.get(pk=player_action.ref.approach_id)
        except ChallengeApproach.DoesNotExist as exc:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

        RoundChallengeDeclaration.objects.update_or_create(
            encounter=self._encounter,
            round_number=self._encounter.round_number,
            participant=participant,
            defaults={
                "challenge_instance": challenge_instance,
                "challenge_approach": challenge_approach,
            },
        )

    def get_cover_for(self, target: CharacterSheet, damage_type: Any) -> float:  # noqa: ARG002
        """Resolve (and cache) this round's Succor cover for *target* (#1744).

        Looks up the ``CombatRoundAction`` declaring ``SUCCOR`` for *target* this
        round. Resolves the succorer's capability challenge via ``dispatch_succor``
        on first call and caches the graded multiplier on
        ``CombatRoundAction.succor_resolution`` — subsequent calls for additional
        hazard rows the same round return the cached value without re-rolling or
        re-charging fatigue, per the approved spec's Decision 8.

        Returns ``1.0`` (no cover) whenever the encounter is not RESOLVING, the
        target has no ACTIVE participant, or no armed SUCCOR declaration names
        them this round.
        """
        from world.combat.constants import (  # noqa: PLC0415
            SUCCOR_BASE_FATIGUE_COST,
            ActionCategory,
            CombatManeuver,
        )
        from world.combat.services import dispatch_succor  # noqa: PLC0415
        from world.fatigue.services import apply_fatigue  # noqa: PLC0415

        if self._encounter.status != RoundStatus.RESOLVING:
            return 1.0

        target_participant = CombatParticipant.objects.filter(
            character_sheet=target,
            encounter=self._encounter,
            status=ParticipantStatus.ACTIVE,
        ).first()
        if target_participant is None:
            return 1.0

        action = (
            CombatRoundAction.objects.filter(
                participant__encounter=self._encounter,
                round_number=self._encounter.round_number,
                maneuver=CombatManeuver.SUCCOR,
                focused_ally_target=target_participant,
                participant__status=ParticipantStatus.ACTIVE,
            )
            .select_related("participant__character_sheet__character")
            .first()
        )
        if action is None:
            return 1.0

        if action.succor_resolution is not None:
            return action.succor_resolution

        succorer = action.participant.character_sheet.character
        protected = target_participant.character_sheet.character

        # Bond combat bonus (#2021): relationship-scaled protection.
        from world.relationships.services import bond_bonus  # noqa: PLC0415

        multiplier = dispatch_succor(
            succorer,
            protected,
            approach=None,
            extra_modifiers=bond_bonus(succorer, protected),
        )

        action.succor_resolution = multiplier
        action.save(update_fields=["succor_resolution"])

        if multiplier < 1.0:
            # Only charge fatigue when Succor actually produced some cover (clean
            # block or partial) — mirrors _try_interpose's "charge fatigue to the
            # interposer ONLY on fire" contract. The 1.0 sentinel means no active
            # challenge/approach was found, i.e. Succor accomplished nothing.
            fatigue_category = action.focused_category or ActionCategory.PHYSICAL
            apply_fatigue(
                action.participant.character_sheet,
                fatigue_category,
                SUCCOR_BASE_FATIGUE_COST,
                action.effort_level,
            )
        return multiplier


def resolve_combat_round_context(character: CharacterSheet) -> CombatRoundContext | None:
    """Find the character's current active ``CombatParticipant`` and return a context.

    Resolution path (canonical — mirrors ``views._get_participant`` in reverse):
        ``CharacterSheet`` → ``CombatParticipant`` (via ``character_sheet`` FK)

    Only ACTIVE participants in non-COMPLETED encounters are considered.  If
    multiple matches exist (edge case), the most recently started encounter is
    chosen deterministically.

    Args:
        character: The ``CharacterSheet`` for the acting character.

    Returns:
        A ``CombatRoundContext`` wrapping the active participant, or ``None``
        if the character has no active combat participation.
    """
    participant = (
        CombatParticipant.objects.filter(
            character_sheet=character,
            status=ParticipantStatus.ACTIVE,
            encounter__status__in=_ACTIVE_ENCOUNTER_STATUSES,
        )
        .select_related("encounter")
        .order_by("-encounter__created_at")
        .first()
    )
    if participant is None:
        return None
    return CombatRoundContext(participant)
