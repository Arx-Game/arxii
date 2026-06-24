"""End-to-end duel integration tests (#568, Task 15).

Exercises the full duel lifecycle against real services (no mocking beyond
the offense-check roll, which is pinned via offense_check_fn to make outcomes
deterministic). Each scenario asserts structural guarantees established by
Tasks 1-14.

Scenario summary
----------------
1. PvP full round-trip — challenge → accept_challenge → both acks → declare →
   run round (_resolve_pc_action against mirror_B) → damage lands on mirror
   surface, B's CharacterVitals unchanged → drive mirror to DEFEATED →
   resolve_duel_end → winner == A, COMPLETED, Interaction rows created.

2. Non-lethal cap — inside the PvP duel deduct_anima draws no overburn deficit
   when lethal=False. Soulfray path tagged @tag("postgres") per repo convention.

3. Lethal NPC duel — create_lethal_duel → PC blocked until acknowledge → after
   acknowledge, declaration succeeds → duel is_lethal True (death gate ARMED).

4. Reach gating — SAME-reach technique against opponent in an adjacent position
   raises ActionDispatchError(TARGET_OUT_OF_REACH).

SetUp pattern
-------------
- CharacterSheet objects in setUpTestData (deepcopy-safe plain Django rows).
- Room and Evennia ObjectDB objects in setUp (not deepcopy-safe).
- evennia.utils.idmapper.models.flush_cache() called in setUp where ObjectDB
  rows are created, to prevent idmapper contamination between tests.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase, tag
from evennia import create_object
from evennia.utils import idmapper

from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
    EncounterOutcome,
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    RiskLevel,
)
from world.combat.duels import (
    accept_challenge,
    create_lethal_duel,
    create_pvp_duel,
    resolve_duel_end,
)
from world.combat.factories import (
    DuelChallengeFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction, EncounterRiskAcknowledgement
from world.combat.services import (
    _resolve_pc_action,
    acknowledge_encounter_risk,
    apply_damage_to_opponent,
    declare_action,
)
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.anima import deduct_anima
from world.scenes.models import Interaction
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _wire_vitals(sheet, *, health: int = 100, max_health: int = 100) -> CharacterVitals:
    """Create or return CharacterVitals for a sheet with the given health."""
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=sheet,
        defaults={"health": health, "max_health": max_health},
    )
    return vitals


def _success_check_fn(_character, _check_type, **_kwargs):
    """Offense check override: always returns success_level=2 (full damage)."""
    return MagicMock(success_level=2)


def _seed_damage_multipliers():
    """Seed DamageSuccessLevelMultiplier rows (idempotent via get_or_create)."""
    DamageSuccessLevelMultiplierFactory(
        min_success_level=2, multiplier=Decimal("1.00"), label="Full"
    )
    DamageSuccessLevelMultiplierFactory(
        min_success_level=1, multiplier=Decimal("0.50"), label="Half"
    )


def _build_combat_technique(*, action_category: str = ActionCategory.PHYSICAL, reach=None):
    """Build a technique with a damage profile and an action_template.

    TechniqueFactory auto-seeds one untyped TechniqueDamageProfile when
    effect_type.base_power is set (the post_generation hook). We rely on that
    instead of calling TechniqueDamageProfileFactory separately, which would
    violate the unique_untyped_damage_profile_per_technique constraint.

    action_template is required by _resolve_pc_action (it reads
    template.check_type for the offense check type).
    """
    check_type = CheckTypeFactory()
    kwargs = {
        "gift": GiftFactory(),
        "effect_type": EffectTypeFactory(base_power=20),
        "action_category": action_category,
        "action_template": ActionTemplateFactory(check_type=check_type),
    }
    if reach is not None:
        kwargs["reach"] = reach
    return TechniqueFactory(**kwargs)


# ---------------------------------------------------------------------------
# Scenario 1: PvP full round-trip
# ---------------------------------------------------------------------------


class PvpFullRoundTripTests(TestCase):
    """challenge → accept → acknowledge → declare → resolve round → winner.

    Structural-non-lethality guarantee: A attacks mirror_B; B's real
    CharacterVitals are never touched by apply_damage_to_opponent because
    opponents are separate CombatOpponent rows backed by their own health
    columns, not the PC's CharacterVitals.
    """

    @classmethod
    def setUpTestData(cls):
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        _seed_damage_multipliers()

    def setUp(self):
        idmapper.models.flush_cache()
        self.room = create_object("typeclasses.rooms.Room", key="PvP Room", nohome=True)

    # ------------------------------------------------------------------ step 1

    def test_challenge_accept_creates_pvp_duel(self):
        """accept_challenge creates a DUEL encounter with two mirrors."""
        challenge = DuelChallengeFactory(
            challenger_sheet=self.sheet_a,
            challenged_sheet=self.sheet_b,
            room=self.room,
        )
        enc = accept_challenge(challenge)

        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertEqual(enc.risk_level, RiskLevel.MODERATE)
        self.assertFalse(enc.is_lethal)
        self.assertEqual(enc.participants.count(), 2)
        mirrors = enc.opponents.filter(mirrors_participant__isnull=False)
        self.assertEqual(mirrors.count(), 2)

    # ------------------------------------------------------------------ step 2

    def test_both_duelists_acknowledged_after_accept(self):
        """create_pvp_duel auto-acknowledges both duelists."""
        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        self.assertEqual(enc.risk_acknowledgements.count(), 2)
        ack_sheets = set(enc.risk_acknowledgements.values_list("character_sheet_id", flat=True))
        self.assertIn(self.sheet_a.pk, ack_sheets)
        self.assertIn(self.sheet_b.pk, ack_sheets)

    # ------------------------------------------------------------------ step 3

    def test_a_declares_technique_targeting_mirror_b(self):
        """A can declare a focused technique targeting mirror_B (the surface)."""
        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        participant_a = enc.participants.get(character_sheet=self.sheet_a)
        _wire_vitals(self.sheet_a)
        CharacterAnimaFactory(character=self.sheet_a.character, current=20, maximum=20)
        technique = _build_combat_technique()
        CharacterTechniqueFactory(character=self.sheet_a, technique=technique)

        mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)

        action = declare_action(
            participant_a,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=mirror_b,
        )
        self.assertEqual(action.focused_opponent_target_id, mirror_b.pk)

    # ------------------------------------------------------------------ step 4

    def test_damage_lands_on_mirror_b_not_real_vitals(self):
        """apply_damage_to_opponent hits mirror_B.health; B's CharacterVitals unchanged.

        This is the structural non-lethality guarantee: mirror surfaces hold
        their own health columns. The PC's CharacterVitals are only touched by
        apply_damage_to_participant (NPC→PC path), never by apply_damage_to_opponent.
        """
        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)
        initial_mirror_health = mirror_b.max_health

        vitals_b = _wire_vitals(self.sheet_b, health=100, max_health=100)
        vitals_b_initial = vitals_b.health

        # Apply damage directly to the mirror surface (what A's round would do).
        apply_damage_to_opponent(mirror_b, 99999)
        mirror_b.refresh_from_db()

        # Mirror took damage (health dropped below initial).
        self.assertLess(mirror_b.health, initial_mirror_health)
        # B's real vitals are completely untouched.
        vitals_b.refresh_from_db()
        self.assertEqual(vitals_b.health, vitals_b_initial)

    # ------------------------------------------------------------------ step 5

    def test_resolve_pc_action_creates_interaction(self):
        """_resolve_pc_action creates Interaction rows for A's attack on mirror_B.

        Uses _resolve_pc_action directly (avoids wiring the full NPC action path
        which requires a seeded FleeConfig singleton). The Interaction is created
        when the participant's character_sheet has a primary Persona —
        CharacterSheetFactory wires this via create_character_with_sheet.
        """
        from world.scenes.factories import SceneFactory

        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        scene = SceneFactory(location=self.room)
        enc.scene = scene
        enc.save(update_fields=["scene"])

        participant_a = enc.participants.get(character_sheet=self.sheet_a)
        _wire_vitals(self.sheet_a)
        CharacterAnimaFactory(character=self.sheet_a.character, current=20, maximum=20)
        # CharacterEngagement is already created by add_participant inside create_pvp_duel.

        technique = _build_combat_technique()
        CharacterTechniqueFactory(character=self.sheet_a, technique=technique)

        mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)

        action = CombatRoundAction.objects.create(
            participant=participant_a,
            round_number=enc.round_number,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            focused_opponent_target=mirror_b,
            effort_level=EffortLevel.MEDIUM,
            is_ready=True,
        )

        pre_count = Interaction.objects.count()
        _resolve_pc_action(participant_a, action, _success_check_fn)
        post_count = Interaction.objects.count()

        # At least one Interaction row was created (ACTION + OUTCOME = 2 normally).
        self.assertGreater(post_count, pre_count)

    # ------------------------------------------------------------------ step 6

    def test_mirror_b_defeated_and_resolve_duel_end_sets_winner(self):
        """DEFEATED mirror_B → resolve_duel_end → winner=A, encounter COMPLETED."""
        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)

        # Drive mirror_B to DEFEATED by applying overwhelming damage.
        apply_damage_to_opponent(mirror_b, mirror_b.max_health * 100)
        mirror_b.refresh_from_db()
        self.assertEqual(mirror_b.status, OpponentStatus.DEFEATED)

        returned = resolve_duel_end(enc)
        enc.refresh_from_db()

        self.assertIsNotNone(returned)
        self.assertEqual(enc.duel_winner_id, self.sheet_a.pk)
        self.assertEqual(enc.status, EncounterStatus.COMPLETED)
        self.assertEqual(enc.outcome, EncounterOutcome.VICTORY)
        self.assertIsNotNone(enc.completed_at)

    def test_real_vitals_b_unchanged_after_duel_win(self):
        """B's CharacterVitals are still at full health after the duel concludes.

        Explicit assertion that the structural non-lethality guarantee holds
        all the way through duel resolution: killing the mirror never drains
        the real PC's health.
        """
        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        vitals_b = _wire_vitals(self.sheet_b, health=100, max_health=100)

        mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)
        apply_damage_to_opponent(mirror_b, mirror_b.max_health * 100)

        resolve_duel_end(enc)
        enc.refresh_from_db()
        self.assertEqual(enc.status, EncounterStatus.COMPLETED)

        vitals_b.refresh_from_db()
        self.assertEqual(
            vitals_b.health, 100, "B's real vitals must be unchanged after mirror defeat"
        )


# ---------------------------------------------------------------------------
# Scenario 2: Non-lethal cap inside a PvP duel
# ---------------------------------------------------------------------------


class PvpNonLethalCapFastTierTests(TestCase):
    """Non-lethal cast (lethal=False) draws no overburn deficit.

    This is the fast-tier (SQLite) assertion. The soulfray path (DISTINCT ON)
    requires Postgres and is tagged separately below.
    """

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def setUp(self):
        idmapper.models.flush_cache()
        # Exhaust anima so any lethal cast would create a deficit.
        self.anima = CharacterAnimaFactory(character=self.sheet.character, current=0, maximum=10)

    def tearDown(self):
        # Clean up anima so setUpTestData sheet is reusable across tests.
        self.anima.delete()

    def test_non_lethal_duel_deduct_anima_no_deficit(self):
        """deduct_anima(lethal=False) clamps to available anima: zero deficit."""
        deficit = deduct_anima(self.sheet.character, 10, lethal=False)
        self.assertEqual(deficit, 0, "Non-lethal cast must not generate overburn deficit")

    def test_lethal_cast_would_create_deficit(self):
        """Confirm lethal=True does create a deficit (control: the gate is real)."""
        deficit = deduct_anima(self.sheet.character, 10, lethal=True)
        self.assertGreater(deficit, 0, "Lethal cast with 0 anima must generate a deficit")

    def test_pvp_duel_is_non_lethal(self):
        """PvP duels created via create_pvp_duel are always non-lethal."""
        other = CharacterSheetFactory()
        room = create_object("typeclasses.rooms.Room", key="NLTest Room", nohome=True)
        enc = create_pvp_duel(self.sheet, other, room)
        self.assertFalse(enc.is_lethal)


@tag("postgres")
class PvpNonLethalCapSoulfrayTests(TestCase):
    """Non-lethal cast: soulfray severity stays below death-risk stage.

    Tagged postgres because apply_condition uses DISTINCT ON (Postgres-only)
    when advancing a progressive condition.
    """

    @classmethod
    def setUpTestData(cls):
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.checks.factories import (
            ConsequenceEffectFactory,
            ConsequenceFactory,
        )
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionStageFactory,
            ConditionTemplateFactory,
        )
        from world.magic.audere import SOULFRAY_CONDITION_NAME
        from world.magic.factories import SoulfrayConfigFactory

        cls.resilience_check_type = CheckTypeFactory(name="Resilience (duel nonlethal test)")
        cls.soulfray_config = SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.resilience_check_type,
            base_check_difficulty=15,
        )

        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
            default_duration_type=DurationType.PERMANENT,
        )

        cls.burnout_condition = ConditionTemplateFactory(
            name="Soul Burnout (duel nonlethal test)",
            default_duration_type=DurationType.PERMANENT,
        )
        cls.death_pool = ConsequencePoolFactory(name="Soulfray Death (duel nonlethal test)")
        cls.death_consequence = ConsequenceFactory(
            label="Burnout (duel nonlethal test)",
            character_loss=True,
        )
        ConsequenceEffectFactory(
            consequence=cls.death_consequence,
            effect_type="apply_condition",
            condition_template=cls.burnout_condition,
            condition_severity=1,
        )
        ConsequencePoolEntryFactory(pool=cls.death_pool, consequence=cls.death_consequence)

        # Stage 1 (benign) — holds non-lethal casts.
        ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=1,
            name="Smoldering (duel nonlethal test)",
            consequence_pool=None,
            severity_threshold=1,
        )
        # Stage 2 (death-risk) — only reachable by lethal overburn.
        ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=2,
            name="Soul Rupture (duel nonlethal test)",
            consequence_pool=cls.death_pool,
            severity_threshold=2,
        )

        cls.technique = TechniqueFactory(
            name="Overburn Blast (duel nonlethal test)",
            intensity=5,
            control=2,
            anima_cost=20,
        )

    def setUp(self):
        from world.mechanics.factories import CharacterEngagementFactory

        idmapper.models.flush_cache()
        self.sheet = CharacterSheetFactory()
        self.anima = CharacterAnimaFactory(character=self.sheet.character, current=0, maximum=10)
        CharacterEngagementFactory(character=self.sheet.character)

    def _run_non_lethal(self):
        from world.magic.services import use_technique

        return use_technique(
            character=self.sheet.character,
            technique=self.technique,
            resolve_fn=lambda *, power, ledger, extra_modifiers=0: "resolved",  # noqa: ARG005
            confirm_soulfray_risk=True,
            lethal=False,
        )

    def test_non_lethal_cast_no_deficit(self):
        """Non-lethal cast draws no overburn deficit (anima clamped at 0)."""
        result = self._run_non_lethal()
        self.assertEqual(result.anima_cost.deficit, 0)

    def test_non_lethal_cast_severity_clamped_below_death_stage(self):
        """Non-lethal soulfray: severity ceiling prevents reaching the death-risk stage.

        With a single death-risk stage at severity_threshold=2, the ceiling is 1.
        After the first cast the character sits at severity 1 (the ceiling).  A
        second non-lethal cast hits the ``_nonlethal_bounded_advance`` short-circuit
        (bounded=0) and returns immediately — the character never advances to the
        death stage and ``stage_consequence`` is guaranteed None.

        The ``_fire_stage_consequence_pool`` character_loss FILTER (which evaluates
        the pool and strips ``character_loss`` entries before selection) is exercised
        by the dedicated ``test_nonlethal_cap.py`` unit tests; this test covers the
        upstream ceiling-clamp guard.
        """
        # First cast creates soulfray at severity 1 (the non-lethal ceiling).
        self._run_non_lethal()
        self.anima.refresh_from_db()
        self.anima.current = 0
        self.anima.save(update_fields=["current"])

        # Second cast: already at ceiling → _nonlethal_bounded_advance returns
        # bounded=0 and short-circuits before the consequence pool is reached.
        result = self._run_non_lethal()

        # The soulfray result must exist (the condition was already created) and
        # must carry no stage_consequence — the ceiling clamp guarantees this
        # unconditionally (no conditional skip).
        self.assertIsNotNone(result.soulfray_result)
        self.assertIsNone(
            result.soulfray_result.stage_consequence,
            "Non-lethal PvP cast at severity ceiling must not fire any stage consequence",
        )


# ---------------------------------------------------------------------------
# Scenario 3: Lethal NPC duel — PC must acknowledge before acting
# ---------------------------------------------------------------------------


class LethalNpcDuelTests(TestCase):
    """create_lethal_duel → PC blocked → acknowledge → unblocked → lethal confirmed."""

    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()
        _seed_damage_multipliers()

    def setUp(self):
        idmapper.models.flush_cache()
        self.room = create_object("typeclasses.rooms.Room", key="Lethal Duel Room", nohome=True)
        self.opponent_kwargs = {
            "name": "Lethal Champion",
            "max_health": 200,
            "threat_pool": self.threat_pool,
            "soak_value": 50,
        }

    def test_lethal_duel_is_lethal(self):
        """create_lethal_duel produces a LETHAL DUEL encounter."""
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertTrue(enc.is_lethal)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)

    def test_pc_not_auto_acknowledged(self):
        """create_lethal_duel does NOT auto-acknowledge the PC (#777 gate)."""
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        self.assertEqual(enc.risk_acknowledgements.count(), 0)

    def test_declaration_blocked_before_ack(self):
        """declare_action raises ValueError with 'acknowledge' before the PC acks."""
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        enc.round_number = 1
        enc.save(update_fields=["round_number"])

        participant = enc.participants.get()
        _wire_vitals(self.pc_sheet)
        opponent = enc.opponents.get()
        technique = _build_combat_technique()

        with self.assertRaises(ValueError) as ctx:
            declare_action(
                participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=opponent,
            )
        self.assertIn("acknowledge", str(ctx.exception).lower())

    def test_declaration_allowed_after_ack(self):
        """After acknowledge_encounter_risk, declaration proceeds."""
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        enc.round_number = 1
        enc.save(update_fields=["round_number"])

        participant = enc.participants.get()
        _wire_vitals(self.pc_sheet)
        CharacterAnimaFactory(character=self.pc_sheet.character, current=20, maximum=20)
        acknowledge_encounter_risk(enc, self.pc_sheet)

        ack_exists = EncounterRiskAcknowledgement.objects.filter(
            encounter=enc, character_sheet=self.pc_sheet
        ).exists()
        self.assertTrue(ack_exists)

        opponent = enc.opponents.get()
        technique = _build_combat_technique()

        # Should not raise.
        action = declare_action(
            participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertIsNotNone(action)

    def test_lethal_flag_armed_after_ack(self):
        """After ack, the encounter's is_lethal flag is True (death gate ARMED).

        The death gate is the is_lethal=True encounter flag combined with the
        non-lethal cap being ABSENT (i.e. lethal=True flows to use_technique),
        which means overburn deficits and soulfray escalation can fire normally.
        """
        enc = create_lethal_duel(self.pc_sheet, self.opponent_kwargs, self.room)
        acknowledge_encounter_risk(enc, self.pc_sheet)
        enc.refresh_from_db()
        self.assertTrue(enc.is_lethal)

    def test_lethal_overburn_deficit_fires_for_lethal_duel(self):
        """In a lethal duel context, deduct_anima(lethal=True) generates deficit.

        Confirms that the death path is live: lethal=True means the soulfray /
        overburn machinery is fully armed (no cap in place).
        """
        anima = CharacterAnimaFactory(character=self.pc_sheet.character, current=0, maximum=10)
        try:
            deficit = deduct_anima(self.pc_sheet.character, 10, lethal=True)
            self.assertGreater(deficit, 0, "Lethal duel overburn deficit must be non-zero")
        finally:
            anima.delete()


# ---------------------------------------------------------------------------
# Scenario 4: Reach gating in a duel context
# ---------------------------------------------------------------------------


class DuelReachGatingTests(TestCase):
    """Technique with SAME reach rejected when attacker and target are in different positions.

    Mirrors the pattern in test_declare_reach_gate.py but specifically in a
    duel context: the attacker is a duel participant, the target is a mirror
    opponent surface, both placed in distinct room positions.

    The mirror_B's objectdb is the same ObjectDB as sheet_b's character. Both
    must be moved into the room before placement into positions.
    """

    def setUp(self):
        from evennia.objects.models import ObjectDB

        from world.areas.positioning.services import (
            connect_positions,
            create_position,
            place_in_position,
        )

        idmapper.models.flush_cache()

        self.sheet_a = CharacterSheetFactory()
        self.sheet_b = CharacterSheetFactory()

        self.room = create_object("typeclasses.rooms.Room", key="Reach Duel Room", nohome=True)
        self.pos_a = create_position(self.room, "reach_pos_a")
        self.pos_b = create_position(self.room, "reach_pos_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        enc = create_pvp_duel(self.sheet_a, self.sheet_b, self.room)
        enc.round_number = 1
        enc.save(update_fields=["round_number"])
        self.enc = enc

        self.participant_a = enc.participants.get(character_sheet=self.sheet_a)
        _wire_vitals(self.sheet_a)
        CharacterAnimaFactory(character=self.sheet_a.character, current=20, maximum=20)

        # Move both characters into the room before placing in positions.
        attacker_od = self.sheet_a.character
        attacker_od.move_to(self.room, quiet=True)
        place_in_position(attacker_od, self.pos_a)

        # mirror_B is backed by sheet_b's character ObjectDB (_make_mirror uses
        # _opponent_kwargs_from_sheet which sets objectdb_id = sheet.character_id).
        self.mirror_b = enc.opponents.get(mirrors_participant__character_sheet=self.sheet_b)
        mirror_b_od = ObjectDB.objects.get(pk=self.mirror_b.objectdb_id)
        mirror_b_od.move_to(self.room, quiet=True)
        place_in_position(mirror_b_od, self.pos_b)

    def test_same_reach_against_adjacent_mirror_raises(self):
        """SAME-reach technique cannot target mirror_B in an adjacent position."""
        technique = _build_combat_technique(reach=TechniqueReach.SAME)

        with self.assertRaises(ActionDispatchError) as cm:
            declare_action(
                self.participant_a,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=self.mirror_b,
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.TARGET_OUT_OF_REACH)
        self.assertIn("out of reach", cm.exception.user_message)

    def test_any_reach_against_adjacent_mirror_succeeds(self):
        """ANY-reach technique can target mirror_B regardless of position."""
        technique = _build_combat_technique(reach=TechniqueReach.ANY)

        action = declare_action(
            self.participant_a,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=self.mirror_b,
        )
        self.assertEqual(action.focused_opponent_target_id, self.mirror_b.pk)
