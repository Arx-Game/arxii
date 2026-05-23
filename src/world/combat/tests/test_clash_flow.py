"""Per-flavor end-to-end integration tests for the Clash mechanic (Task 8.2).

These are the proof-of-life tests for the full clash pipeline: from declared
actions through resolve_round to consequences. One test class per flavor.

Each class:
- Uses ClashContent.create_all() in setUpTestData for the heavy authored-content
  seed (idempotent get_or_creates; no Evennia ObjectDB there).
- Creates encounters, participants, and opponents in setUp (per-test) because
  CombatOpponentFactory creates Evennia ObjectDB instances that are not
  deepcopyable by Django's setUpTestData machinery.
- Uses force_check_outcome for deterministic rolls.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from integration_tests.game_content.clash import ClashContent
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    ClashActionSlot,
    ClashFlavor,
    ClashStatus,
    EncounterStatus,
    LockPcRole,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    ClashConfigFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import (
    Clash,
    ClashRound,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatRoundAction,
)
from world.combat.services import (
    begin_declaration_phase,
    declare_clash_contribution,
    resolve_round,
)
from world.conditions.models import ConditionInstance
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Shared helpers — module-level so they can be called from setUpTestData
# ---------------------------------------------------------------------------


def _ensure_configs() -> None:
    """Ensure StrainConfig + ClashConfig singleton rows exist."""
    StrainConfigFactory()
    ClashConfigFactory()


def _ensure_multipliers() -> None:
    """Ensure DamageSuccessLevelMultiplier rows exist for the combat pipeline."""
    from world.conditions.factories import DamageSuccessLevelMultiplierFactory

    DamageSuccessLevelMultiplierFactory(
        min_success_level=2, multiplier=Decimal("1.00"), label="flow_full"
    )
    DamageSuccessLevelMultiplierFactory(
        min_success_level=1, multiplier=Decimal("0.50"), label="flow_partial"
    )


def _seed_check_outcomes() -> dict[int, object]:
    """Seed CheckOutcome rows for all tiers used by the clash pipeline."""
    tiers = {
        3: "flow_critical",
        2: "flow_great",
        1: "flow_success",
        0: "flow_partial",
        -1: "flow_failure",
        -2: "flow_botch",
    }
    outcomes: dict[int, object] = {}
    for sl, name in tiers.items():
        outcomes[sl] = CheckOutcomeFactory(name=name, success_level=sl)
    return outcomes


def _ensure_technique_action_template(technique: object, check_type: object) -> object:
    """Attach an action_template to a technique if it doesn't have one yet."""
    if technique.action_template is None:
        template = ActionTemplateFactory(check_type=check_type)
        technique.action_template = template
        technique.save(update_fields=["action_template"])
    return technique


# ---------------------------------------------------------------------------
# Per-test helper: build a participant with anima/engagement/vitals
# ---------------------------------------------------------------------------


def _make_participant(encounter: CombatEncounter) -> object:
    """Build a PC participant with anima + engagement + vitals."""
    sheet = CharacterSheetFactory()
    CharacterAnimaFactory(character=sheet.character, current=100, maximum=100)
    CharacterEngagementFactory(character=sheet.character)
    CharacterVitals.objects.create(character_sheet=sheet, health=100)
    return CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
    )


def _make_boss_opponent(encounter: CombatEncounter, threat_pool: object) -> CombatOpponent:
    """Build a BOSS-tier opponent linked to the shared threat pool."""
    return CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.BOSS,
        health=200,
        max_health=200,
        threat_pool=threat_pool,
    )


def _npc_action_for_entry(
    opponent: CombatOpponent,
    entry: object,
    round_number: int,
    targets: list | None = None,
) -> CombatOpponentAction:
    """Create a CombatOpponentAction row for the NPC."""
    action = CombatOpponentAction.objects.create(
        opponent=opponent,
        threat_entry=entry,
        round_number=round_number,
    )
    if targets:
        action.targets.set(targets)
    return action


def _pc_passive_action(participant: object, round_number: int) -> CombatRoundAction:
    """Create a minimal pass action for the PC so resolve_round can proceed."""
    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=round_number,
    )


def _start_next_round(encounter: CombatEncounter) -> None:
    """Transition encounter from BETWEEN_ROUNDS to DECLARING for the next round."""
    encounter.refresh_from_db()
    begin_declaration_phase(encounter)
    encounter.refresh_from_db()


# ---------------------------------------------------------------------------
# 1. CLASH flavor
# ---------------------------------------------------------------------------


class ClashFlavorFlowTests(TestCase):
    """Full-pipeline CLASH flavor test.

    PC declares clash-capable attack → NPC has clash-capable threat entry →
    resolve_round forms a Clash (CLASH flavor) → ClashRound rows accumulate →
    meter crosses threshold → resolve_clash fires the resolution pool.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Singletons and authored content (no Evennia ObjectDB here).
        _ensure_configs()
        _ensure_multipliers()
        cls.outcomes = _seed_check_outcomes()
        cls.content = ClashContent.create_all()
        cls.check_type = ActionTemplateFactory().check_type
        _ensure_technique_action_template(cls.content.clash_capable_technique, cls.check_type)

    def setUp(self) -> None:
        # Per-test encounter + participants + boss (involves Evennia ObjectDB).
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = _make_participant(self.encounter)
        self.boss = _make_boss_opponent(self.encounter, self.content.threat_pool)

    # -----------------------------------------------------------------------
    # Test
    # -----------------------------------------------------------------------

    def test_clash_flavor_full_pipeline(self) -> None:
        """CLASH flavor: NPC + PC clash-capable actions → Clash formed → meter
        accumulates → crosses threshold → resolved with consequence pool.
        """
        # ------------------------------------------------------------------ #
        # Round 1: both sides declare clash-capable actions → Clash forms.   #
        # ------------------------------------------------------------------ #
        CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.content.clash_capable_technique,
            focused_opponent_target=self.boss,
        )

        _npc_action_for_entry(
            self.boss,
            self.content.npc_clash_capable_entry,
            round_number=1,
            targets=[self.participant],
        )

        with force_check_outcome(self.outcomes[1]):
            result_r1 = resolve_round(self.encounter)

        # Verify a Clash was created.
        clash = Clash.objects.filter(
            encounter=self.encounter,
            flavor=ClashFlavor.CLASH,
        ).first()
        self.assertIsNotNone(clash, "A CLASH-flavor Clash should have been created in round 1.")
        self.assertIn(clash.status, (ClashStatus.ACTIVE, ClashStatus.RESOLVED))
        self.assertEqual(len(result_r1.clash_outcomes), 1)

        # At least one ClashRound row should exist.
        self.assertTrue(
            ClashRound.objects.filter(clash=clash).exists(),
            "A ClashRound row should exist after round 1.",
        )

        # ------------------------------------------------------------------ #
        # Drive to resolution if still ACTIVE.                                #
        # ------------------------------------------------------------------ #
        max_rounds = 20
        for _ in range(max_rounds):
            clash.refresh_from_db()
            if clash.status == ClashStatus.RESOLVED:
                break

            _start_next_round(self.encounter)
            self.encounter.refresh_from_db()
            rn = self.encounter.round_number

            _pc_passive_action(self.participant, rn)

            _npc_action_for_entry(
                self.boss,
                self.content.npc_clash_capable_entry,
                round_number=rn,
                targets=[self.participant],
            )

            declare_clash_contribution(
                participant=self.participant,
                clash=clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.content.clash_capable_technique,
                strain_commitment=0,
            )

            with force_check_outcome(self.outcomes[3]):  # critical → large delta
                resolve_round(self.encounter)

        # Final assertions.
        clash.refresh_from_db()
        self.assertEqual(
            clash.status,
            ClashStatus.RESOLVED,
            f"Clash should be RESOLVED after {max_rounds} rounds with critical successes.",
        )
        self.assertIsNotNone(clash.resolution, "Clash should have a resolution tier.")
        self.assertIsNotNone(clash.resolved_round, "Clash should record its resolved round.")

        round_count = ClashRound.objects.filter(clash=clash).count()
        self.assertGreaterEqual(round_count, 1, "At least one ClashRound row should exist.")

        pool = clash.resolution_consequence_pool
        self.assertTrue(
            pool.cached_consequences,
            "Resolution pool should have at least one consequence entry.",
        )


# ---------------------------------------------------------------------------
# 2. Suppress (LOCK/SUSTAINING) flavor
# ---------------------------------------------------------------------------


class SuppressFlowTests(TestCase):
    """Full-pipeline LOCK/SUSTAINING flavor test.

    PC declares lock-applying technique against boss → LOCK/SUSTAINING clash
    forms → PC declares maintenance contributions across rounds → meter reaches
    threshold → resolve_clash fires → APPLY_CONDITION effect creates the
    boss_held ConditionInstance on the boss → clash_window_combo becomes
    available in detect_available_combos.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_configs()
        _ensure_multipliers()
        cls.outcomes = _seed_check_outcomes()
        cls.content = ClashContent.create_all()
        cls.check_type = ActionTemplateFactory().check_type
        _ensure_technique_action_template(cls.content.lock_applying_technique, cls.check_type)

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = _make_participant(self.encounter)
        self.boss = _make_boss_opponent(self.encounter, self.content.threat_pool)

    # -----------------------------------------------------------------------
    # Test
    # -----------------------------------------------------------------------

    def test_suppress_flavor_full_pipeline(self) -> None:
        """LOCK/SUSTAINING: PC lock-applying technique → clash forms with SUSTAINING
        role → meter reaches threshold → boss_held condition applied to boss NPC →
        clash_window_combo shows up in detect_available_combos.
        """
        # ------------------------------------------------------------------ #
        # Round 1: PC declares lock-applying technique aimed at boss.        #
        # ------------------------------------------------------------------ #
        CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.content.lock_applying_technique,
            focused_opponent_target=self.boss,
        )

        # NPC action (any non-lock entry so the encounter can proceed).
        npc_entry = ThreatPoolEntryFactory(pool=self.content.threat_pool, base_damage=5)
        _npc_action_for_entry(self.boss, npc_entry, round_number=1, targets=[self.participant])

        with force_check_outcome(self.outcomes[1]):
            result_r1 = resolve_round(self.encounter)

        # Verify a LOCK/SUSTAINING clash was created.
        clash = Clash.objects.filter(
            encounter=self.encounter,
            flavor=ClashFlavor.LOCK,
            lock_pc_role=LockPcRole.SUSTAINING,
        ).first()
        self.assertIsNotNone(clash, "A LOCK/SUSTAINING Clash should have been formed in round 1.")
        self.assertEqual(len(result_r1.clash_outcomes), 1)

        # ------------------------------------------------------------------ #
        # Subsequent rounds: PC declares maintenance contributions.          #
        # ------------------------------------------------------------------ #
        max_rounds = 20
        for _ in range(max_rounds):
            clash.refresh_from_db()
            if clash.status == ClashStatus.RESOLVED:
                break

            _start_next_round(self.encounter)
            self.encounter.refresh_from_db()
            rn = self.encounter.round_number

            _pc_passive_action(self.participant, rn)

            entry = ThreatPoolEntryFactory(pool=self.content.threat_pool, base_damage=0)
            _npc_action_for_entry(self.boss, entry, round_number=rn, targets=[self.participant])

            declare_clash_contribution(
                participant=self.participant,
                clash=clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.content.lock_applying_technique,
                strain_commitment=0,
            )

            with force_check_outcome(self.outcomes[3]):  # decisive win
                resolve_round(self.encounter)

        clash.refresh_from_db()
        self.assertEqual(
            clash.status,
            ClashStatus.RESOLVED,
            f"LOCK/SUSTAINING clash should have resolved within {max_rounds} rounds.",
        )

        # PC should win (decisive or marginal — both tiers apply boss_held in
        # ClashContent).  With default delta_critical_success=3 and threshold=10,
        # the first crossing gives overshoot=2 < decisive_overshoot=3 → PC_MARGINAL.
        # ClashContent seeds boss_held on both PC_DECISIVE and PC_MARGINAL tiers.
        self.assertIn(
            clash.resolution,
            ("PC_DECISIVE", "PC_MARGINAL"),
            f"Expected PC win resolution for LOCK/SUSTAINING, got {clash.resolution!r}.",
        )

        boss_objectdb = self.boss.objectdb
        self.assertIsNotNone(boss_objectdb, "Boss should have an ObjectDB.")

        boss_held_instance = ConditionInstance.objects.filter(
            target=boss_objectdb,
            condition=self.content.boss_held_condition,
        ).first()
        self.assertIsNotNone(
            boss_held_instance,
            "boss_held_condition should have been applied to the boss after a decisive LOCK win.",
        )

        # ------------------------------------------------------------------ #
        # Verify the clash_window_combo is now detectable.                   #
        # ------------------------------------------------------------------ #
        from world.combat.models import ComboSlot
        from world.combat.services import detect_available_combos

        _start_next_round(self.encounter)
        self.encounter.refresh_from_db()
        rn = self.encounter.round_number

        # Build two techniques whose effect_type matches the combo's slots.
        slot = ComboSlot.objects.filter(combo=self.content.clash_window_combo).first()
        self.assertIsNotNone(slot, "clash_window_combo should have at least one slot.")
        effect_type = slot.required_action_type

        combo_technique_1 = TechniqueFactory(effect_type=effect_type)
        combo_technique_2 = TechniqueFactory(effect_type=effect_type)

        # Add a second participant for the 2-slot combo.
        sheet2 = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet2.character, current=50, maximum=50)
        CharacterEngagementFactory(character=sheet2.character)
        CharacterVitals.objects.create(character_sheet=sheet2, health=100)
        participant2 = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=sheet2,
            status=ParticipantStatus.ACTIVE,
        )

        CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=rn,
            focused_action=combo_technique_1,
            focused_opponent_target=self.boss,
        )
        CombatRoundAction.objects.create(
            participant=participant2,
            round_number=rn,
            focused_action=combo_technique_2,
            focused_opponent_target=self.boss,
        )

        available = detect_available_combos(self.encounter, rn)
        combo_ids = {av.combo.pk for av in available}
        self.assertIn(
            self.content.clash_window_combo.pk,
            combo_ids,
            "clash_window_combo should be available now that boss_held condition is active "
            "and both participants declared matching techniques.",
        )


# ---------------------------------------------------------------------------
# 3. Break Free (LOCK/ESCAPING) flavor
# ---------------------------------------------------------------------------


class BreakFreeFlowTests(TestCase):
    """Full-pipeline LOCK/ESCAPING flavor test.

    NPC's lock-applying threat entry targets a PC → LOCK/ESCAPING clash forms →
    PC declares escape contributions across rounds → meter reaches 0 → resolve_clash
    fires → PC escapes (PC_DECISIVE or PC_MARGINAL resolution).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_configs()
        _ensure_multipliers()
        cls.outcomes = _seed_check_outcomes()
        cls.content = ClashContent.create_all()
        cls.check_type = ActionTemplateFactory().check_type
        # lock_applying_technique is used for PC escape contributions.
        _ensure_technique_action_template(cls.content.lock_applying_technique, cls.check_type)

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = _make_participant(self.encounter)
        self.boss = _make_boss_opponent(self.encounter, self.content.threat_pool)

    # -----------------------------------------------------------------------
    # Test
    # -----------------------------------------------------------------------

    def test_break_free_flavor_full_pipeline(self) -> None:
        """LOCK/ESCAPING: NPC lock-applying entry hits PC → LOCK/ESCAPING clash forms →
        PC escape contributions across rounds → meter reaches 0 → PC escapes.
        """
        # ------------------------------------------------------------------ #
        # Round 1: NPC uses lock-applying entry against the PC.              #
        # ------------------------------------------------------------------ #
        _pc_passive_action(self.participant, round_number=1)

        _npc_action_for_entry(
            self.boss,
            self.content.npc_lock_applying_entry,
            round_number=1,
            targets=[self.participant],
        )

        with force_check_outcome(self.outcomes[1]):
            result_r1 = resolve_round(self.encounter)

        clash = Clash.objects.filter(
            encounter=self.encounter,
            flavor=ClashFlavor.LOCK,
            lock_pc_role=LockPcRole.ESCAPING,
        ).first()
        self.assertIsNotNone(clash, "A LOCK/ESCAPING Clash should have been formed in round 1.")
        self.assertEqual(len(result_r1.clash_outcomes), 1)

        # ESCAPING: starts at 0; NPC pushes UP, PC pushes DOWN; PC wins at <=0.
        # threshold = clash_break_free_force = 5 (from npc_lock_applying_entry).
        self.assertEqual(clash.pc_win_threshold, 5)

        # ------------------------------------------------------------------ #
        # Subsequent rounds: PC declares escape contributions.               #
        # ------------------------------------------------------------------ #
        max_rounds = 20
        for _ in range(max_rounds):
            clash.refresh_from_db()
            if clash.status == ClashStatus.RESOLVED:
                break

            _start_next_round(self.encounter)
            self.encounter.refresh_from_db()
            rn = self.encounter.round_number

            _pc_passive_action(self.participant, rn)

            # NPC maintains the lock (any entry from the pool).
            entry = ThreatPoolEntryFactory(
                pool=self.content.threat_pool,
                base_damage=0,
                clash_npc_pressure=1,
            )
            _npc_action_for_entry(self.boss, entry, round_number=rn, targets=[self.participant])

            declare_clash_contribution(
                participant=self.participant,
                clash=clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.content.lock_applying_technique,
                strain_commitment=0,
            )

            with force_check_outcome(self.outcomes[3]):  # critical success
                resolve_round(self.encounter)

        clash.refresh_from_db()
        self.assertEqual(
            clash.status,
            ClashStatus.RESOLVED,
            f"LOCK/ESCAPING clash should have resolved within {max_rounds} rounds.",
        )
        self.assertIn(
            clash.resolution,
            ("PC_DECISIVE", "PC_MARGINAL"),
            f"Expected PC win resolution, got {clash.resolution!r}.",
        )


# ---------------------------------------------------------------------------
# 4. WARD flavor
# ---------------------------------------------------------------------------


class WardFlowTests(TestCase):
    """Full-pipeline WARD flavor test.

    NPC sustained attack opens a WARD clash → PCs declare ward contributions
    across rounds → barrage expires → WARD resolves → per-round pool fired
    each round → resolution pool fired at expiry.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_configs()
        _ensure_multipliers()
        cls.outcomes = _seed_check_outcomes()
        cls.content = ClashContent.create_all()
        cls.check_type = ActionTemplateFactory().check_type
        # Use clash_capable_technique for ward contributions.
        _ensure_technique_action_template(cls.content.clash_capable_technique, cls.check_type)

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = _make_participant(self.encounter)
        self.boss = _make_boss_opponent(self.encounter, self.content.threat_pool)

    # -----------------------------------------------------------------------
    # Test
    # -----------------------------------------------------------------------

    def test_ward_flavor_full_pipeline(self) -> None:
        """WARD: NPC sustained attack → WARD clash forms → PC ward contributions →
        per-round pool fires each round → barrage expires → resolution pool fires.
        """
        # ------------------------------------------------------------------ #
        # Round 1: NPC starts a sustained attack → WARD clash forms.        #
        # ------------------------------------------------------------------ #
        _pc_passive_action(self.participant, round_number=1)

        _npc_action_for_entry(
            self.boss,
            self.content.sustained_attack_entry,
            round_number=1,
            targets=[self.participant],
        )

        with force_check_outcome(self.outcomes[1]):
            result_r1 = resolve_round(self.encounter)

        clash = Clash.objects.filter(
            encounter=self.encounter,
            flavor=ClashFlavor.WARD,
        ).first()
        self.assertIsNotNone(clash, "A WARD-flavor Clash should have been created in round 1.")
        self.assertEqual(len(result_r1.clash_outcomes), 1)

        # WARD starts at full integrity (pc_win_threshold).
        # sustained_duration_rounds=3, so ward_ends_on_round = 1 + 3 = 4.
        self.assertIsNotNone(clash.ward_ends_on_round)
        ward_end = clash.ward_ends_on_round

        # ------------------------------------------------------------------ #
        # Drive rounds until the WARD expires.                               #
        # ------------------------------------------------------------------ #
        max_iter = 20
        for _ in range(max_iter):
            clash.refresh_from_db()
            if clash.status == ClashStatus.RESOLVED:
                break

            _start_next_round(self.encounter)
            self.encounter.refresh_from_db()
            rn = self.encounter.round_number

            _pc_passive_action(self.participant, rn)

            # Sustained attack repeats (WARD idempotency: same (opponent, entry) pair
            # won't create a second WARD).
            _npc_action_for_entry(
                self.boss,
                self.content.sustained_attack_entry,
                round_number=rn,
                targets=[self.participant],
            )

            declare_clash_contribution(
                participant=self.participant,
                clash=clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.content.clash_capable_technique,
                strain_commitment=0,
            )

            with force_check_outcome(self.outcomes[2]):  # great success
                resolve_round(self.encounter)

        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.RESOLVED, "WARD clash should have resolved.")
        self.assertIsNotNone(clash.resolution)

        # Multiple ClashRound rows should exist (one per active round).
        round_count = ClashRound.objects.filter(clash=clash).count()
        self.assertGreaterEqual(round_count, 1, "At least one ClashRound row should exist.")

        # Resolution pool is non-empty.
        pool = clash.resolution_consequence_pool
        self.assertTrue(
            pool.cached_consequences,
            "Ward resolution pool should have at least one consequence entry.",
        )

        # WARD resolves when round_number > ward_ends_on_round.
        self.assertIsNotNone(clash.resolved_round)
        self.assertGreaterEqual(
            clash.resolved_round,
            ward_end,
            "Clash should have resolved at or after the ward expiry round.",
        )


# ---------------------------------------------------------------------------
# 5. BREAK flavor
# ---------------------------------------------------------------------------


class BreakFlavorFlowTests(TestCase):
    """Full-pipeline BREAK flavor test.

    Barrier attached to boss → resolve_round detects BREAK clash →
    PC declares break contributions → meter crosses barrier_strength threshold →
    barrier breached → BREAK resolution pool fires.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        _ensure_configs()
        _ensure_multipliers()
        cls.outcomes = _seed_check_outcomes()
        cls.content = ClashContent.create_all()
        cls.check_type = ActionTemplateFactory().check_type
        _ensure_technique_action_template(cls.content.clash_capable_technique, cls.check_type)

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = _make_participant(self.encounter)
        self.boss = _make_boss_opponent(self.encounter, self.content.threat_pool)

        # Attach a barrier to the boss (small strength for fast test).
        ClashContent.attach_barrier_to_opponent(
            self.boss,
            strength=5,
            break_pool=self.content.break_resolution_pool,
        )

    # -----------------------------------------------------------------------
    # Test
    # -----------------------------------------------------------------------

    def test_break_flavor_full_pipeline(self) -> None:
        """BREAK: boss has barrier → detect_clash_opportunities forms BREAK →
        PC break contributions drive meter to barrier_strength → breach →
        break_resolution_pool fires.
        """
        # ------------------------------------------------------------------ #
        # Round 1: any NPC action triggers BREAK detection for the barrier.  #
        # ------------------------------------------------------------------ #
        _pc_passive_action(self.participant, round_number=1)

        npc_entry = ThreatPoolEntryFactory(pool=self.content.threat_pool, base_damage=5)
        _npc_action_for_entry(self.boss, npc_entry, round_number=1, targets=[self.participant])

        with force_check_outcome(self.outcomes[1]):
            result_r1 = resolve_round(self.encounter)

        # A BREAK clash should have been detected.
        clash = Clash.objects.filter(
            encounter=self.encounter,
            flavor=ClashFlavor.BREAK,
        ).first()
        self.assertIsNotNone(clash, "A BREAK-flavor Clash should have been created in round 1.")
        self.assertEqual(len(result_r1.clash_outcomes), 1)

        # Threshold = barrier_strength = 5.
        self.assertEqual(clash.pc_win_threshold, 5)

        # ------------------------------------------------------------------ #
        # Subsequent rounds: PC declares break contributions.                #
        # ------------------------------------------------------------------ #
        max_rounds = 20
        for _ in range(max_rounds):
            clash.refresh_from_db()
            if clash.status == ClashStatus.RESOLVED:
                break

            _start_next_round(self.encounter)
            self.encounter.refresh_from_db()
            rn = self.encounter.round_number

            _pc_passive_action(self.participant, rn)

            entry = ThreatPoolEntryFactory(pool=self.content.threat_pool, base_damage=0)
            _npc_action_for_entry(self.boss, entry, round_number=rn, targets=[self.participant])

            declare_clash_contribution(
                participant=self.participant,
                clash=clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.content.clash_capable_technique,
                strain_commitment=0,
            )

            with force_check_outcome(self.outcomes[3]):  # critical success
                resolve_round(self.encounter)

        clash.refresh_from_db()
        self.assertEqual(
            clash.status,
            ClashStatus.RESOLVED,
            f"BREAK clash should have resolved within {max_rounds} rounds.",
        )
        self.assertIn(
            clash.resolution,
            ("PC_DECISIVE", "PC_MARGINAL"),
            f"Expected PC win resolution for BREAK, got {clash.resolution!r}.",
        )

        pool = clash.resolution_consequence_pool
        self.assertTrue(
            pool.cached_consequences,
            "Break resolution pool should have at least one consequence entry.",
        )

        round_count = ClashRound.objects.filter(clash=clash).count()
        self.assertGreaterEqual(
            round_count,
            2,
            "Multiple ClashRound rows should exist (round 1 + break contributions).",
        )
