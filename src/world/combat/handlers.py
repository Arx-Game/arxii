"""Combat handlers.

- ``CharacterCombatPullHandler`` — per-character active CombatPull rows (Spec A §3.7).
- ``EncounterCombatHandler`` — per-encounter combat state for the resolution loop
  (Phase 2 of the combat-resolution-loop PR). Single cached queryset + list-comp
  subsets per the design spec.

Pattern: one underlying ``cached_property`` per handler that prefetches the
scope's full state in a single query plan; regular methods do list-comp subsets
from that cache. Explicit ``invalidate()`` is called by mutation services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import F, Prefetch
from django.utils.functional import cached_property

from world.combat.constants import ClashStatus
from world.combat.models import (
    Clash,
    ClashContribution,
    ClashContributionDeclaration,
    CombatOpponentAction,
    CombatParticipant,
    CombatPull,
    CombatPullResolvedEffect,
    CombatRoundAction,
)
from world.magic.constants import EffectKind

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter


class CharacterCombatPullHandler:
    """Handler for a character's currently-active CombatPull rows."""

    def __init__(self, character: Character) -> None:
        self.character = character

    @cached_property
    def _active(self) -> list[CombatPull]:
        sheet = self.character.sheet_data
        return list(
            CombatPull.objects.filter(
                participant__character_sheet=sheet,
                round_number=F("encounter__round_number"),
            )
            .select_related("encounter", "participant", "resonance")
            .prefetch_related(
                Prefetch(
                    "resolved_effects",
                    queryset=CombatPullResolvedEffect.objects.select_related(
                        "source_thread",
                        "granted_capability",
                    ),
                    to_attr="resolved_effects_cached",
                ),
            )
        )

    def active(self) -> list[CombatPull]:
        """Return all currently-active pulls across all encounters."""
        return self._active

    def active_for_encounter(self, encounter: CombatEncounter) -> list[CombatPull]:
        """Narrow the active set to a specific encounter."""
        return [p for p in self._active if p.encounter_id == encounter.pk]

    def active_pull_vital_bonuses(self, vital_target: str) -> int:
        """Sum scaled VITAL_BONUS values across active pulls for one target.

        Used by ``recompute_max_health_with_threads`` and
        ``apply_damage_reduction_from_threads`` (both Phase 13). Filters by
        both effect kind and ``vital_target`` so MAX_HEALTH and
        DAMAGE_TAKEN_REDUCTION rows stay independent.
        """
        total = 0
        for pull in self._active:
            for eff in pull.resolved_effects_cached:
                if (
                    eff.kind == EffectKind.VITAL_BONUS
                    and eff.vital_target == vital_target
                    and eff.scaled_value
                ):
                    total += eff.scaled_value
        return total

    def invalidate(self) -> None:
        """Clear the cached active-pull list. Called by mutation services."""
        self.__dict__.pop("_active", None)


@dataclass(frozen=True)
class EncounterCombatState:
    """Snapshot of an encounter's combat state.

    Frozen by design — the handler's cache is invalidated, not mutated.
    Every list is a complete prefetched collection; subset methods on the
    handler do list-comps over these.
    """

    participants: list[CombatParticipant]
    clashes: list[Clash]
    pc_actions: list[CombatRoundAction]
    npc_actions: list[CombatOpponentAction]
    clash_declarations: list[ClashContributionDeclaration]


class EncounterCombatHandler:
    """Encounter-scoped combat state with one prefetched cache.

    Replaces scattered ``.objects.filter(encounter=...)`` calls in
    ``_detect_clash_flavor``, ``_resolve_pc_action``, ``_clash_contribution_actions``,
    and ``resolve_round``. Service-function bodies in the resolution loop run
    zero raw queries — all reads go through this handler's list-comp methods.

    Mutation contract: every service that creates or mutates a Clash, ClashRound,
    ClashContribution, CombatRoundAction, CombatOpponentAction, or
    ClashContributionDeclaration row in this encounter must call
    ``handler.invalidate()`` afterwards.
    """

    def __init__(self, encounter: CombatEncounter) -> None:
        self.encounter = encounter

    @cached_property
    def _state(self) -> EncounterCombatState:
        """ONE prefetched snapshot of the encounter's combat state."""
        participants = list(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
            ).select_related("character_sheet", "covenant_role")
        )
        # ClashRound and ClashContribution chains need separate Prefetches
        # so each one carries a to_attr (project convention).
        from world.combat.models import ClashRound  # noqa: PLC0415

        clashes = list(
            Clash.objects.filter(encounter=self.encounter)
            .select_related("npc_opponent", "triggering_threat_entry")
            .prefetch_related(
                Prefetch(
                    "rounds",
                    queryset=ClashRound.objects.prefetch_related(
                        Prefetch(
                            "contributions",
                            queryset=ClashContribution.objects.select_related(
                                "character",
                                "technique",
                                "check_outcome",
                            ),
                            to_attr="cached_contributions",
                        ),
                    ),
                    to_attr="cached_rounds",
                ),
            )
        )
        pc_actions = list(
            CombatRoundAction.objects.filter(
                participant__encounter=self.encounter,
            ).select_related(
                "participant",
                "participant__character_sheet",
                "focused_action",
                "focused_action__effect_type",
                "focused_action__action_template",
                "focused_action__action_template__check_type",
                "focused_opponent_target",
                "focused_ally_target",
                "combo_upgrade",
                "interaction",
            )
        )
        # to_attr matches the existing `cached_targets` consumer convention in
        # combat/services.py (e.g. _resolve_npc_action reads npc_action.cached_targets).
        npc_actions = list(
            CombatOpponentAction.objects.filter(
                opponent__encounter=self.encounter,
            )
            .select_related("opponent", "threat_entry")
            .prefetch_related(
                Prefetch(
                    "targets",
                    queryset=CombatParticipant.objects.select_related("character_sheet"),
                    to_attr="cached_targets",
                ),
            )
        )
        clash_declarations = list(
            ClashContributionDeclaration.objects.filter(
                encounter=self.encounter,
            ).select_related("participant", "clash", "technique")
        )
        return EncounterCombatState(
            participants=participants,
            clashes=clashes,
            pc_actions=pc_actions,
            npc_actions=npc_actions,
            clash_declarations=clash_declarations,
        )

    # ------------------------------------------------------------------
    # Subset methods — all list-comps over self._state.
    # ------------------------------------------------------------------

    def participants(self) -> list[CombatParticipant]:
        """Return all CombatParticipant rows in this encounter."""
        return list(self._state.participants)

    def active_clashes(self) -> list[Clash]:
        """Return Clash rows with status=ACTIVE."""
        return [c for c in self._state.clashes if c.status == ClashStatus.ACTIVE]

    def all_clashes(self) -> list[Clash]:
        """Return all Clash rows (active + resolved)."""
        return list(self._state.clashes)

    def pc_actions_for_round(self, round_number: int) -> list[CombatRoundAction]:
        """Return CombatRoundAction rows for a specific round."""
        return [a for a in self._state.pc_actions if a.round_number == round_number]

    def npc_actions_for_round(self, round_number: int) -> list[CombatOpponentAction]:
        """Return CombatOpponentAction rows for a specific round."""
        return [a for a in self._state.npc_actions if a.round_number == round_number]

    def principal_clashes_for(self, participant: CombatParticipant) -> list[Clash]:
        """Return active clashes where this participant is the initiator (principal)."""
        return [
            c
            for c in self._state.clashes
            if c.status == ClashStatus.ACTIVE and c.initiator_id == participant.character_sheet_id
        ]

    def contributions_for_clash(self, clash: Clash) -> list[ClashContribution]:
        """Return all ClashContribution rows across all rounds of one clash.

        Reads from the prefetched `cached_rounds` + `cached_contributions`
        attributes set by the _state queryset's Prefetch chain.
        """
        for cached_clash in self._state.clashes:
            if cached_clash.pk != clash.pk:
                continue
            result: list[ClashContribution] = []
            for clash_round in cached_clash.cached_rounds:
                result.extend(clash_round.cached_contributions)
            return result
        return []

    def clash_declarations_for_round(self, round_number: int) -> list[ClashContributionDeclaration]:
        """Return ClashContributionDeclaration rows for a specific round."""
        return [d for d in self._state.clash_declarations if d.round_number == round_number]

    def participant_for_sheet(self, character_sheet: CharacterSheet) -> CombatParticipant | None:
        """Return the CombatParticipant whose character_sheet matches."""
        for p in self._state.participants:
            if p.character_sheet_id == character_sheet.pk:
                return p
        return None

    def invalidate(self) -> None:
        """Drop the cache. Called by mutation services."""
        self.__dict__.pop("_state", None)
