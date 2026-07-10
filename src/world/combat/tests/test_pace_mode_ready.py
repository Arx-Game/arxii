"""Tests for PaceMode.READY early resolution (#2120).

Two duelists who have both declared and readied should resolve immediately in
PaceMode.READY, rather than waiting out a TIMED-mode timer built for
unattended play. ``maybe_resolve_on_ready`` compares the ACTIVE participant
count against this round's ``is_ready=True`` CombatRoundAction count.

Declarations here are passives-only (no maneuver, no focused action) so the
resolution pass is a no-op per participant — the tests stay focused on the
ready-count comparison without needing FleeConfig or a seeded check pipeline.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier, PaceMode, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import maybe_resolve_on_ready, toggle_action_ready
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_encounter(pace_mode: str = PaceMode.READY):
    encounter = CombatEncounterFactory(
        status=RoundStatus.DECLARING,
        pace_mode=pace_mode,
        round_number=1,
    )
    CombatOpponentFactory(encounter=encounter, tier=OpponentTier.MOOK)
    return encounter


def _add_pc(encounter):
    sheet = CharacterSheetFactory()
    CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
    return CombatParticipantFactory(
        encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
    )


def _declare_passive(participant, *, ready: bool = True) -> CombatRoundAction:
    """A passives-only declaration — resolves as a no-op at round resolution."""
    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=participant.encounter.round_number,
        is_ready=ready,
    )


class MaybeResolveOnReadyTests(TestCase):
    def test_both_ready_resolves_the_round(self) -> None:
        """Two ACTIVE participants, both is_ready=True -> resolve_round fires."""
        encounter = _make_encounter()
        first = _add_pc(encounter)
        second = _add_pc(encounter)
        _declare_passive(first)
        _declare_passive(second)

        result = maybe_resolve_on_ready(encounter)

        assert result is not None
        encounter.refresh_from_db()
        assert encounter.status != RoundStatus.DECLARING

    def test_lone_ready_does_not_resolve(self) -> None:
        """One of two ACTIVE participants ready -> no resolution."""
        encounter = _make_encounter()
        first = _add_pc(encounter)
        _add_pc(encounter)  # never declares/readies
        _declare_passive(first)

        result = maybe_resolve_on_ready(encounter)

        assert result is None
        encounter.refresh_from_db()
        assert encounter.status == RoundStatus.DECLARING

    def test_un_readying_never_triggers_resolution(self) -> None:
        """Toggling a participant back to not-ready must never itself resolve the round."""
        encounter = _make_encounter()
        first = _add_pc(encounter)
        second = _add_pc(encounter)
        action_first = _declare_passive(first)
        _declare_passive(second)
        toggle_action_ready(action_first)  # flips first back to is_ready=False

        result = maybe_resolve_on_ready(encounter)

        assert result is None
        encounter.refresh_from_db()
        assert encounter.status == RoundStatus.DECLARING

    def test_timed_mode_is_a_noop(self) -> None:
        """PaceMode.TIMED encounters never early-resolve here — the game-clock sweep owns them."""
        encounter = _make_encounter(pace_mode=PaceMode.TIMED)
        first = _add_pc(encounter)
        second = _add_pc(encounter)
        _declare_passive(first)
        _declare_passive(second)

        result = maybe_resolve_on_ready(encounter)

        assert result is None
        encounter.refresh_from_db()
        assert encounter.status == RoundStatus.DECLARING

    def test_manual_mode_is_a_noop(self) -> None:
        encounter = _make_encounter(pace_mode=PaceMode.MANUAL)
        first = _add_pc(encounter)
        second = _add_pc(encounter)
        _declare_passive(first)
        _declare_passive(second)

        result = maybe_resolve_on_ready(encounter)

        assert result is None
        encounter.refresh_from_db()
        assert encounter.status == RoundStatus.DECLARING

    def test_no_active_participants_is_a_noop(self) -> None:
        encounter = _make_encounter()

        result = maybe_resolve_on_ready(encounter)

        assert result is None

    def test_not_declaring_is_a_noop(self) -> None:
        encounter = _make_encounter()
        encounter.status = RoundStatus.BETWEEN_ROUNDS
        encounter.save(update_fields=["status"])

        result = maybe_resolve_on_ready(encounter)

        assert result is None
