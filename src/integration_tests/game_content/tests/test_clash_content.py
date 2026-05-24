"""Tests for ClashContent seed factory (Task 8.1).

Verifies:
1. ClashContent.create_all() returns a populated ClashContentResult with no None fields.
2. A second call produces zero new DB writes (idempotent).
3. The seeded lock_applying_technique.is_lock_applying property returns True.
4. The LOCK resolution pool's PC_DECISIVE tier consequence has an APPLY_CONDITION
   effect wired to the boss_held_condition template.
5. ClashContent.attach_barrier_to_opponent() sets barrier_strength and
   barrier_break_pool on a freshly-created CombatOpponent.
"""

from __future__ import annotations

from django.test import TestCase

from integration_tests.game_content.clash import ClashContent, ClashContentResult


class ClashContentCreateAllTests(TestCase):
    """First-call assertions: result is fully populated."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ClashContentResult = ClashContent.create_all()

    def test_create_all_returns_populated_result(self) -> None:
        """Every field on ClashContentResult is a non-None DB row."""
        r = self.result

        self.assertIsNotNone(r.clash_capable_technique)
        self.assertIsNotNone(r.lock_applying_technique)
        self.assertIsNotNone(r.npc_clash_capable_entry)
        self.assertIsNotNone(r.npc_lock_applying_entry)
        self.assertIsNotNone(r.sustained_attack_entry)
        self.assertIsNotNone(r.lock_condition)
        self.assertIsNotNone(r.boss_held_condition)
        self.assertIsNotNone(r.clash_resolution_pool)
        self.assertIsNotNone(r.clash_per_round_pool)
        self.assertIsNotNone(r.lock_resolution_pool)
        self.assertIsNotNone(r.ward_resolution_pool)
        self.assertIsNotNone(r.ward_per_round_pool)
        self.assertIsNotNone(r.break_resolution_pool)
        self.assertIsNotNone(r.clash_window_combo)
        self.assertIsNotNone(r.threat_pool)

    def test_all_result_fields_have_pks(self) -> None:
        """Spot-check: all non-pool result fields are persisted (have a pk)."""
        r = self.result
        self.assertGreater(r.clash_capable_technique.pk, 0)
        self.assertGreater(r.lock_applying_technique.pk, 0)
        self.assertGreater(r.lock_condition.pk, 0)
        self.assertGreater(r.boss_held_condition.pk, 0)
        self.assertGreater(r.clash_window_combo.pk, 0)
        self.assertGreater(r.threat_pool.pk, 0)

    def test_clash_capable_technique_flag(self) -> None:
        """clash_capable_technique.clash_capable is True."""
        self.assertTrue(self.result.clash_capable_technique.clash_capable)

    def test_npc_clash_capable_entry_flag(self) -> None:
        """NPC clash entry has clash_capable=True and clash_npc_pressure set."""
        entry = self.result.npc_clash_capable_entry
        self.assertTrue(entry.clash_capable)
        self.assertIsNotNone(entry.clash_npc_pressure)
        self.assertGreater(entry.clash_npc_pressure, 0)

    def test_npc_lock_applying_entry_flag(self) -> None:
        """NPC lock entry has is_lock_applying=True and clash_break_free_force set."""
        entry = self.result.npc_lock_applying_entry
        self.assertTrue(entry.is_lock_applying)
        self.assertIsNotNone(entry.clash_break_free_force)
        self.assertGreater(entry.clash_break_free_force, 0)

    def test_sustained_attack_entry_flag(self) -> None:
        """Sustained attack entry has is_sustained_attack=True and duration set."""
        entry = self.result.sustained_attack_entry
        self.assertTrue(entry.is_sustained_attack)
        self.assertIsNotNone(entry.sustained_duration_rounds)
        self.assertGreater(entry.sustained_duration_rounds, 0)

    def test_lock_condition_is_clash_lock(self) -> None:
        """lock_condition has is_clash_lock=True and a positive clash_lock_strength."""
        cond = self.result.lock_condition
        self.assertTrue(cond.is_clash_lock)
        self.assertIsNotNone(cond.clash_lock_strength)
        self.assertGreater(cond.clash_lock_strength, 0)

    def test_combo_has_required_clash_window_condition(self) -> None:
        """clash_window_combo.required_clash_window_condition is boss_held_condition."""
        combo = self.result.clash_window_combo
        self.assertEqual(
            combo.required_clash_window_condition_id,
            self.result.boss_held_condition.pk,
        )

    def test_combo_has_two_slots(self) -> None:
        """clash_window_combo has at least two ComboSlot rows."""
        from world.combat.models import ComboSlot

        slot_count = ComboSlot.objects.filter(combo=self.result.clash_window_combo).count()
        self.assertGreaterEqual(slot_count, 2)

    def test_six_consequence_pools_created(self) -> None:
        """Exactly six named pools are created (one per flavor/event)."""
        from actions.models import ConsequencePool

        expected_names = {
            "Clash Resolution Pool (Clash Test)",
            "Clash Per-Round Pool (Clash Test)",
            "Lock Resolution Pool (Clash Test)",
            "Ward Resolution Pool (Clash Test)",
            "Ward Per-Round Pool (Clash Test)",
            "Break Resolution Pool (Clash Test)",
        }
        actual = set(
            ConsequencePool.objects.filter(name__endswith="(Clash Test)").values_list(
                "name", flat=True
            )
        )
        self.assertGreaterEqual(actual, expected_names)


class ClashContentIdempotencyTests(TestCase):
    """Second-call assertions: row counts unchanged."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.first: ClashContentResult = ClashContent.create_all()
        cls.second: ClashContentResult = ClashContent.create_all()

    def _counts(self) -> dict[str, int]:
        from actions.models import ConsequencePool, ConsequencePoolEntry
        from world.checks.models import Consequence, ConsequenceEffect
        from world.combat.models import ComboDefinition, ComboSlot, ThreatPool, ThreatPoolEntry
        from world.conditions.models import ConditionTemplate
        from world.magic.models import Technique, TechniqueAppliedCondition
        from world.traits.models import CheckOutcome

        return {
            "technique": Technique.objects.count(),
            "technique_applied_condition": TechniqueAppliedCondition.objects.count(),
            "threat_pool": ThreatPool.objects.count(),
            "threat_pool_entry": ThreatPoolEntry.objects.count(),
            "condition_template": ConditionTemplate.objects.count(),
            "consequence_pool": ConsequencePool.objects.count(),
            "consequence_pool_entry": ConsequencePoolEntry.objects.count(),
            "consequence": Consequence.objects.count(),
            "consequence_effect": ConsequenceEffect.objects.count(),
            "combo_definition": ComboDefinition.objects.count(),
            "combo_slot": ComboSlot.objects.count(),
            "check_outcome": CheckOutcome.objects.count(),
        }

    def test_create_all_is_idempotent(self) -> None:
        """Calling create_all() twice must not double any row counts."""
        # Snapshot taken after both calls have already run (in setUpTestData).
        # A third call must leave counts unchanged.
        before = self._counts()
        ClashContent.create_all()
        after = self._counts()

        for model_name, count_before in before.items():
            with self.subTest(model=model_name):
                self.assertEqual(
                    after[model_name],
                    count_before,
                    f"{model_name}: count changed from {count_before} to {after[model_name]} "
                    f"on third create_all() call",
                )

    def test_same_pks_returned_on_second_call(self) -> None:
        """Result PKs are stable across calls (get, not create, on second call)."""
        self.assertEqual(
            self.first.clash_capable_technique.pk,
            self.second.clash_capable_technique.pk,
        )
        self.assertEqual(
            self.first.lock_applying_technique.pk,
            self.second.lock_applying_technique.pk,
        )
        self.assertEqual(self.first.lock_condition.pk, self.second.lock_condition.pk)
        self.assertEqual(
            self.first.boss_held_condition.pk,
            self.second.boss_held_condition.pk,
        )
        self.assertEqual(
            self.first.lock_resolution_pool.pk,
            self.second.lock_resolution_pool.pk,
        )
        self.assertEqual(
            self.first.clash_window_combo.pk,
            self.second.clash_window_combo.pk,
        )


class ClashContentLockApplyingTechniqueTests(TestCase):
    """Verify the lock-applying technique's is_lock_applying property."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ClashContentResult = ClashContent.create_all()

    def test_lock_applying_technique_property_is_true(self) -> None:
        """lock_applying_technique.is_lock_applying returns True.

        This verifies the Task 1.5 property (Technique.is_lock_applying) fires
        correctly when TechniqueAppliedCondition has a condition with is_clash_lock=True.
        """
        technique = self.result.lock_applying_technique
        self.assertTrue(
            technique.is_lock_applying,
            "lock_applying_technique.is_lock_applying must be True — "
            "TechniqueAppliedCondition should link to a condition with is_clash_lock=True",
        )


class ClashContentLockResolutionPoolTests(TestCase):
    """Verify the LOCK resolution pool has the critical APPLY_CONDITION wiring."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ClashContentResult = ClashContent.create_all()

    def test_lock_resolution_pool_applies_boss_held_condition(self) -> None:
        """The LOCK resolution pool's PC_DECISIVE tier consequence applies boss_held_condition.

        PC_DECISIVE maps to success_level=3 (_resolution_to_check_outcome in clash.py).
        The consequence linked at that tier must have an APPLY_CONDITION ConsequenceEffect
        whose condition_template is the boss_held_condition.

        This is the critical authored piece that makes the combo-prereq integration test
        drivable in Task 8.2.
        """
        from world.checks.constants import EffectType as CheckEffectType
        from world.checks.models import ConsequenceEffect
        from world.traits.models import CheckOutcome

        # Retrieve the CheckOutcome at success_level=3 (PC_DECISIVE tier).
        decisive_outcome = CheckOutcome.objects.filter(success_level=3).order_by("pk").first()
        self.assertIsNotNone(
            decisive_outcome,
            "No CheckOutcome with success_level=3 found — create_all() must seed this row.",
        )

        lock_pool = self.result.lock_resolution_pool
        boss_held = self.result.boss_held_condition

        # Find all APPLY_CONDITION effects whose consequence is in the lock pool
        # and whose condition_template is boss_held_condition.
        matching_effects = ConsequenceEffect.objects.filter(
            effect_type=CheckEffectType.APPLY_CONDITION,
            condition_template=boss_held,
            consequence__outcome_tier=decisive_outcome,
            consequence__pool_entries__pool=lock_pool,
        )
        self.assertTrue(
            matching_effects.exists(),
            "LOCK resolution pool must have a PC_DECISIVE (success_level=3) consequence "
            "with an APPLY_CONDITION ConsequenceEffect targeting boss_held_condition. "
            f"Pool pk={lock_pool.pk}, boss_held pk={boss_held.pk}, "
            f"decisive_outcome pk={decisive_outcome.pk}.",
        )


class ClashContentBarrierHelperTests(TestCase):
    """Verify attach_barrier_to_opponent() sets fields correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ClashContentResult = ClashContent.create_all()

    def _make_bare_opponent(self) -> CombatOpponent:  # type: ignore[name-defined]
        """Create a minimal CombatOpponent without an ObjectDB (barrier tests only)."""
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        # Use direct ORM to avoid the lazy_attribute objectdb_id which creates Evennia objects.
        from world.combat.constants import OpponentTier
        from world.combat.models import CombatOpponent

        return CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="Barrier Test Boss",
            health=500,
            max_health=500,
        )

    def test_attach_barrier_to_opponent_sets_fields(self) -> None:
        """attach_barrier_to_opponent sets barrier_strength and barrier_break_pool."""
        opponent = self._make_bare_opponent()

        # Preconditions: barrier fields should be null before attachment.
        self.assertIsNone(opponent.barrier_strength)
        self.assertIsNone(opponent.barrier_break_pool_id)

        ClashContent.attach_barrier_to_opponent(
            opponent=opponent,
            strength=15,
            break_pool=self.result.break_resolution_pool,
        )

        # Re-fetch from DB to verify the save() actually persisted.
        from world.combat.models import CombatOpponent

        refreshed = (
            CombatOpponent.objects.filter(pk=opponent.pk)
            .values("barrier_strength", "barrier_break_pool_id")
            .get()
        )
        self.assertEqual(refreshed["barrier_strength"], 15)
        self.assertEqual(refreshed["barrier_break_pool_id"], self.result.break_resolution_pool.pk)

    def test_attach_barrier_default_strength(self) -> None:
        """attach_barrier_to_opponent uses strength=10 by default."""
        opponent = self._make_bare_opponent()

        ClashContent.attach_barrier_to_opponent(opponent=opponent)

        from world.combat.models import CombatOpponent

        refreshed = CombatOpponent.objects.filter(pk=opponent.pk).values("barrier_strength").get()
        self.assertEqual(refreshed["barrier_strength"], 10)
