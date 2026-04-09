"""Tests for combat timer task."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.combat.constants import EncounterStatus, PaceMode
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.tasks import check_and_resolve_timed_encounters


class CombatTimerTaskTest(TestCase):
    def test_resolves_expired_encounter(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            pace_mode=PaceMode.TIMED,
            pace_timer_minutes=10,
            round_started_at=timezone.now() - timedelta(minutes=15),
            round_number=1,
        )
        CombatOpponentFactory(encounter=encounter)

        resolved = check_and_resolve_timed_encounters()

        assert encounter.pk in resolved
        encounter.refresh_from_db()
        assert encounter.status != EncounterStatus.DECLARING

    def test_ignores_non_expired_encounter(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            pace_mode=PaceMode.TIMED,
            pace_timer_minutes=10,
            round_started_at=timezone.now() - timedelta(minutes=5),
            round_number=1,
        )
        CombatOpponentFactory(encounter=encounter)

        resolved = check_and_resolve_timed_encounters()

        assert encounter.pk not in resolved
        encounter.refresh_from_db()
        assert encounter.status == EncounterStatus.DECLARING

    def test_ignores_paused_encounter(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            pace_mode=PaceMode.TIMED,
            is_paused=True,
            pace_timer_minutes=10,
            round_started_at=timezone.now() - timedelta(minutes=15),
            round_number=1,
        )
        CombatOpponentFactory(encounter=encounter)

        resolved = check_and_resolve_timed_encounters()

        assert encounter.pk not in resolved

    def test_ignores_manual_mode(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            pace_mode=PaceMode.MANUAL,
            round_started_at=timezone.now() - timedelta(minutes=15),
            round_number=1,
        )

        resolved = check_and_resolve_timed_encounters()

        assert encounter.pk not in resolved

    def test_ignores_non_declaring_encounter(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            pace_mode=PaceMode.TIMED,
            round_started_at=timezone.now() - timedelta(minutes=15),
        )

        resolved = check_and_resolve_timed_encounters()

        assert encounter.pk not in resolved
