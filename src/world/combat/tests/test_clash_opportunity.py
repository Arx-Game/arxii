"""Tests for detect_clash_opportunities (Task 5.1).

One test per clash flavor. Tests verify:
  - Empty-encounter returns empty list.
  - CLASH: opposed clash-capable attacks produce a CLASH row.
  - LOCK/SUSTAINING: a lock-applying PC technique produces a LOCK row (SUSTAINING).
  - LOCK/ESCAPING: a lock-applying NPC action produces LOCK rows (ESCAPING) per target.
  - WARD: a sustained NPC attack produces a WARD row with correct ward_ends_on_round.
  - BREAK: an opponent with barrier_strength produces a BREAK row.
  - Idempotency: duplicate WARD and BREAK not recreated on second call.
  - Skip when resolution pool missing: no CLASH formed without clash_resolution_pool.
"""

from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from world.combat.constants import ClashFlavor, ClashStatus, LockPcRole
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import (
    Clash,
    CombatOpponentAction,
    CombatRoundAction,
)
from world.magic.factories import TechniqueFactory


class DetectClashOpportunitiesTests(TestCase):
    """Test suite for detect_clash_opportunities — one test per flavor."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pc_action(self, *, participant, technique, opponent, round_number=1):
        """Create a CombatRoundAction for a PC."""
        return CombatRoundAction.objects.create(
            participant=participant,
            round_number=round_number,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

    def _npc_action(self, *, opponent, threat_entry, round_number=1, targets=None):
        """Create a CombatOpponentAction for an NPC."""
        action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=round_number,
            threat_entry=threat_entry,
        )
        if targets:
            for t in targets:
                action.targets.add(t)
        return action

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_no_actions_returns_empty(self):
        """Encounter with no declared actions / no barrier → empty list."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        result = detect_clash_opportunities(encounter=encounter, round_number=1)
        self.assertEqual(result, [])

    def test_clash_from_opposed_clash_capable_attacks(self):
        """PC declares clash-capable attack against NPC whose round action's threat_entry
        is also clash_capable → one CLASH formed.
        """
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()
        technique = TechniqueFactory(clash_capable=True, clash_resolution_pool=pool)
        opponent = CombatOpponentFactory(encounter=encounter)
        participant = CombatParticipantFactory(encounter=encounter)

        self._pc_action(participant=participant, technique=technique, opponent=opponent)

        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            clash_capable=True,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry)

        clashes = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual(clash.flavor, ClashFlavor.CLASH)
        self.assertEqual(clash.status, ClashStatus.ACTIVE)
        self.assertEqual(clash.npc_opponent, opponent)
        self.assertEqual(clash.resolution_consequence_pool, pool)
        self.assertEqual(clash.pc_win_threshold, 10)
        self.assertEqual(clash.npc_win_threshold, 10)
        self.assertEqual(clash.started_round, 1)

    def test_lock_sustaining_from_lock_applying_pc_technique(self):
        """PC declares a technique that applies an is_clash_lock=True condition → one
        LOCK/SUSTAINING formed with threshold = clash_lock_strength.
        """
        from world.combat.clash import detect_clash_opportunities
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.models.techniques import TechniqueAppliedCondition

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()
        technique = TechniqueFactory(clash_resolution_pool=pool)
        lock_condition = ConditionTemplateFactory(is_clash_lock=True, clash_lock_strength=8)
        TechniqueAppliedCondition.objects.create(
            technique=technique,
            condition=lock_condition,
        )
        opponent = CombatOpponentFactory(encounter=encounter)
        participant = CombatParticipantFactory(encounter=encounter)

        self._pc_action(participant=participant, technique=technique, opponent=opponent)

        # NPC has an action this round so break-free force has a source.
        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            clash_break_free_force=5,
            clash_npc_pressure=3,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry)

        clashes = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual(clash.flavor, ClashFlavor.LOCK)
        self.assertEqual(clash.lock_pc_role, LockPcRole.SUSTAINING)
        self.assertEqual(clash.pc_win_threshold, 8)
        self.assertEqual(clash.progress, 0)
        self.assertEqual(clash.resolution_consequence_pool, pool)

    def test_lock_escaping_from_lock_applying_npc_action(self):
        """NPC's round action threat_entry is is_lock_applying → one LOCK/ESCAPING per target."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()

        opponent = CombatOpponentFactory(encounter=encounter)
        participant = CombatParticipantFactory(encounter=encounter)

        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            is_lock_applying=True,
            clash_break_free_force=12,
            clash_npc_pressure=4,
            clash_resolution_pool=pool,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry, targets=[participant])

        clashes = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual(clash.flavor, ClashFlavor.LOCK)
        self.assertEqual(clash.lock_pc_role, LockPcRole.ESCAPING)
        self.assertEqual(clash.pc_win_threshold, 12)
        self.assertEqual(clash.progress, 0)
        self.assertEqual(clash.resolution_consequence_pool, pool)
        self.assertEqual(clash.initiator, participant.character_sheet)

    def test_ward_from_sustained_attack(self):
        """NPC's round action threat_entry is_sustained_attack → one WARD with
        ward_ends_on_round set correctly.
        """
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()

        opponent = CombatOpponentFactory(encounter=encounter)
        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            is_sustained_attack=True,
            sustained_duration_rounds=3,
            clash_npc_pressure=4,
            clash_resolution_pool=pool,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry, round_number=2)

        clashes = detect_clash_opportunities(encounter=encounter, round_number=2)

        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual(clash.flavor, ClashFlavor.WARD)
        self.assertEqual(clash.ward_ends_on_round, 5)  # round_number(2) + duration(3)
        # progress starts at pc_win_threshold (full ward integrity)
        self.assertEqual(clash.progress, clash.pc_win_threshold)
        self.assertEqual(clash.resolution_consequence_pool, pool)

    def test_break_from_opponent_barrier(self):
        """Opponent with barrier_strength set → one BREAK formed."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()

        CombatOpponentFactory(
            encounter=encounter,
            barrier_strength=20,
            barrier_break_pool=pool,
        )

        clashes = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual(clash.flavor, ClashFlavor.BREAK)
        self.assertEqual(clash.pc_win_threshold, 20)
        self.assertEqual(clash.progress, 0)
        self.assertIsNone(clash.npc_win_threshold)
        self.assertEqual(clash.resolution_consequence_pool, pool)

    def test_duplicate_ward_not_recreated(self):
        """Running detection twice on the same round with a sustained attack → only ONE WARD."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()

        opponent = CombatOpponentFactory(encounter=encounter)
        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            is_sustained_attack=True,
            sustained_duration_rounds=3,
            clash_npc_pressure=2,
            clash_resolution_pool=pool,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry)

        first_run = detect_clash_opportunities(encounter=encounter, round_number=1)
        second_run = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(first_run), 1)
        self.assertEqual(len(second_run), 0)  # already exists, idempotent
        self.assertEqual(
            Clash.objects.filter(encounter=encounter, flavor=ClashFlavor.WARD).count(), 1
        )

    def test_duplicate_break_not_recreated(self):
        """Running detection twice with a standing barrier → only ONE BREAK."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        pool = ConsequencePoolFactory()

        CombatOpponentFactory(
            encounter=encounter,
            barrier_strength=10,
            barrier_break_pool=pool,
        )

        first_run = detect_clash_opportunities(encounter=encounter, round_number=1)
        second_run = detect_clash_opportunities(encounter=encounter, round_number=1)

        self.assertEqual(len(first_run), 1)
        self.assertEqual(len(second_run), 0)
        self.assertEqual(
            Clash.objects.filter(encounter=encounter, flavor=ClashFlavor.BREAK).count(), 1
        )

    def test_skips_when_no_resolution_pool(self):
        """PC attack is clash_capable but has no clash_resolution_pool → no CLASH formed."""
        from world.combat.clash import detect_clash_opportunities

        encounter = CombatEncounterFactory()
        # technique with clash_capable=True but NO clash_resolution_pool
        technique = TechniqueFactory(clash_capable=True, clash_resolution_pool=None)
        opponent = CombatOpponentFactory(encounter=encounter)
        participant = CombatParticipantFactory(encounter=encounter)

        self._pc_action(participant=participant, technique=technique, opponent=opponent)

        npc_entry = ThreatPoolEntryFactory(
            pool=opponent.threat_pool,
            clash_capable=True,
        )
        self._npc_action(opponent=opponent, threat_entry=npc_entry)

        clashes = detect_clash_opportunities(encounter=encounter, round_number=1)
        self.assertEqual(clashes, [])
        self.assertEqual(Clash.objects.filter(encounter=encounter).count(), 0)
