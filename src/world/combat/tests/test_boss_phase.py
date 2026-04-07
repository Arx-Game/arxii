"""Tests for boss phase transition service."""

from django.test import TestCase

from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    ThreatPoolFactory,
)
from world.combat.models import BossPhase, CombatOpponent
from world.combat.services import check_and_advance_boss_phase


class CheckAndAdvanceBossPhaseTests(TestCase):
    """Tests for check_and_advance_boss_phase."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.pool_p1 = ThreatPoolFactory(name="Boss Phase 1")
        cls.pool_p2 = ThreatPoolFactory(name="Boss Phase 2")
        cls.pool_p3 = ThreatPoolFactory(name="Boss Phase 3")

    def _make_boss(self, *, health: int, max_health: int = 500) -> CombatOpponent:
        return CombatOpponent.objects.create(
            encounter=CombatEncounterFactory(),
            tier=OpponentTier.BOSS,
            name="Dragon",
            health=health,
            max_health=max_health,
            soak_value=80,
            probing_threshold=50,
            probing_current=30,
            threat_pool=self.pool_p1,
            current_phase=1,
        )

    def test_advance_on_health_trigger(self) -> None:
        """Boss transitions to phase 2 when health drops below trigger."""
        boss = self._make_boss(health=200)  # 40% health
        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=self.pool_p2,
            soak_value=60,
            probing_threshold=30,
            health_trigger_percentage=0.5,
            description="Dragon enters rage mode.",
        )
        result = check_and_advance_boss_phase(boss)
        self.assertIsNotNone(result)
        boss.refresh_from_db()
        self.assertEqual(boss.current_phase, 2)
        self.assertEqual(boss.threat_pool, self.pool_p2)
        self.assertEqual(boss.soak_value, 60)
        self.assertEqual(boss.probing_threshold, 30)
        self.assertEqual(boss.probing_current, 0)  # Reset

    def test_no_advance_above_threshold(self) -> None:
        """Boss does not advance if health is above the trigger."""
        boss = self._make_boss(health=400)  # 80% health
        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=self.pool_p2,
            soak_value=60,
            probing_threshold=30,
            health_trigger_percentage=0.5,
        )
        result = check_and_advance_boss_phase(boss)
        self.assertIsNone(result)
        boss.refresh_from_db()
        self.assertEqual(boss.current_phase, 1)

    def test_multi_phase_skips_to_correct(self) -> None:
        """If health drops low enough, advance to the first matching phase."""
        boss = self._make_boss(health=100)  # 20% health
        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=self.pool_p2,
            soak_value=60,
            probing_threshold=30,
            health_trigger_percentage=0.5,
        )
        BossPhase.objects.create(
            opponent=boss,
            phase_number=3,
            threat_pool=self.pool_p3,
            soak_value=40,
            probing_threshold=20,
            health_trigger_percentage=0.25,
        )
        result = check_and_advance_boss_phase(boss)
        # Should advance to phase 2 first (ordered by phase_number)
        self.assertIsNotNone(result)
        boss.refresh_from_db()
        self.assertEqual(boss.current_phase, 2)

    def test_no_phases_defined(self) -> None:
        """No phases means no transition."""
        boss = self._make_boss(health=50)
        result = check_and_advance_boss_phase(boss)
        self.assertIsNone(result)

    def test_phase_without_health_trigger(self) -> None:
        """A phase with no health_trigger_percentage is skipped."""
        boss = self._make_boss(health=100)
        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=self.pool_p2,
            soak_value=60,
            probing_threshold=30,
            health_trigger_percentage=None,
        )
        result = check_and_advance_boss_phase(boss)
        self.assertIsNone(result)

    def test_already_in_final_phase(self) -> None:
        """Boss already in phase 2 doesn't advance to phase 2 again."""
        boss = self._make_boss(health=100)
        boss.current_phase = 2
        boss.save(update_fields=["current_phase"])

        BossPhase.objects.create(
            opponent=boss,
            phase_number=2,
            threat_pool=self.pool_p2,
            soak_value=60,
            probing_threshold=30,
            health_trigger_percentage=0.5,
        )
        result = check_and_advance_boss_phase(boss)
        self.assertIsNone(result)
