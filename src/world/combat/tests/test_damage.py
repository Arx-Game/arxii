"""Tests for combat damage resolution service functions."""

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, EncounterStatus, OpponentStatus, OpponentTier
from world.combat.factories import (
    BossOpponentFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import (
    apply_damage_to_opponent,
    apply_damage_to_participant,
    resolve_round,
)
from world.conditions.factories import (
    DamageSuccessLevelMultiplierFactory,
    UnconsciousConditionFactory,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals


class ApplyDamageToOpponentTest(TestCase):
    """Tests for apply_damage_to_opponent."""

    def test_damage_reduces_health(self) -> None:
        opponent = CombatOpponentFactory(health=50, max_health=50)
        result = apply_damage_to_opponent(opponent, 20)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)
        self.assertEqual(result.damage_dealt, 20)
        self.assertTrue(result.health_damaged)
        self.assertFalse(result.defeated)

    def test_damage_below_soak_still_probes(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        result = apply_damage_to_opponent(opponent, 30)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 500)
        self.assertEqual(result.damage_dealt, 0)
        self.assertFalse(result.health_damaged)
        self.assertTrue(result.probed)
        self.assertEqual(result.probing_increment, 30)

    def test_damage_above_soak_applies_and_probes(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        result = apply_damage_to_opponent(opponent, 100)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 480)
        self.assertEqual(result.damage_dealt, 20)
        self.assertTrue(result.health_damaged)
        self.assertTrue(result.probed)
        self.assertEqual(result.probing_increment, 100)

    def test_zero_health_defeats_opponent(self) -> None:
        opponent = CombatOpponentFactory(health=10, max_health=50)
        result = apply_damage_to_opponent(opponent, 15)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, -5)
        self.assertEqual(opponent.status, OpponentStatus.DEFEATED)
        self.assertTrue(result.defeated)

    def test_combo_damage_bypasses_soak(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)
        probing_before = opponent.probing_current
        result = apply_damage_to_opponent(opponent, 50, bypass_soak=True)

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 450)
        self.assertEqual(result.damage_dealt, 50)
        self.assertTrue(result.health_damaged)
        # Combo damage should not probe — probing_current unchanged
        self.assertEqual(opponent.probing_current, probing_before)
        self.assertFalse(result.probed)
        self.assertEqual(result.probing_increment, 0)

    def test_probing_increment_equals_raw_damage(self) -> None:
        opponent = BossOpponentFactory(health=500, max_health=500, soak_value=80)

        result_soaked = apply_damage_to_opponent(opponent, 30)
        self.assertEqual(result_soaked.probing_increment, 30)

        opponent.refresh_from_db()
        result_through = apply_damage_to_opponent(opponent, 100)
        self.assertEqual(result_through.probing_increment, 100)


class ApplyDamageToParticipantTest(TestCase):
    """Tests for apply_damage_to_participant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.participant = CombatParticipantFactory()

    def setUp(self) -> None:
        self.vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.participant.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        self.vitals.health = 100
        self.vitals.max_health = 100
        self.vitals.life_state = CharacterLifeState.ALIVE
        self.vitals.save()

    def test_damage_reduces_health(self) -> None:
        result = apply_damage_to_participant(self.participant, 30)
        self.vitals.refresh_from_db()
        assert self.vitals.health == 70
        assert result.damage_dealt == 30

    def test_health_can_go_negative(self) -> None:
        apply_damage_to_participant(self.participant, 150)
        self.vitals.refresh_from_db()
        assert self.vitals.health == -50

    def test_knockout_eligible_below_20_percent(self) -> None:
        result = apply_damage_to_participant(self.participant, 85)
        assert result.knockout_eligible is True

    def test_not_knockout_eligible_above_20_percent(self) -> None:
        result = apply_damage_to_participant(self.participant, 50)
        assert result.knockout_eligible is False

    def test_death_eligible_at_zero(self) -> None:
        result = apply_damage_to_participant(self.participant, 100)
        assert result.death_eligible is True

    def test_permanent_wound_on_big_hit(self) -> None:
        result = apply_damage_to_participant(self.participant, 60)
        assert result.permanent_wound_eligible is True

    def test_no_permanent_wound_on_small_hit(self) -> None:
        result = apply_damage_to_participant(self.participant, 10)
        assert result.permanent_wound_eligible is False

    def test_force_death_does_not_write_status(self) -> None:
        """force_death no longer mutates vitals.status / dying_final_round.

        Incapacitation/dying are now conditions applied by
        process_damage_consequences. apply_damage_to_participant only applies
        the health change and reports eligibility; force_death drives the
        CHARACTER_KILLED event but writes no life-state to vitals.
        """
        result = apply_damage_to_participant(self.participant, 10, force_death=True)
        self.vitals.refresh_from_db()
        # Health change applied; no DYING/DEAD life-state write here.
        assert self.vitals.health == 90
        # death_eligible is health-derived (not force_death-derived); 90hp → False.
        assert result.death_eligible is False
        assert self.vitals.life_state == CharacterLifeState.ALIVE


class KnockoutDeathProcessingTest(TestCase):
    """Tests for knockout/death processing during NPC action resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _setup_encounter(
        self,
        *,
        pc_health: int = 100,
        npc_damage: int = 30,
    ) -> tuple:
        """Create encounter with 1 PC, 1 NPC, NPC targeting PC."""
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=npc_damage)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=pc_health,
            max_health=100,
        )
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomKO",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)
        return encounter, participant, opponent

    def test_no_knockout_without_check_type(self) -> None:
        """Without knockout check type, participant stays ALIVE even at low health."""
        # PC has 15 health, NPC deals 5 damage -> 10/100 = 10% < 20%
        encounter, participant, _ = self._setup_encounter(pc_health=15, npc_damage=5)
        result = resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)
        # Damage consequence should still be recorded
        npc_outcomes = [o for o in result.action_outcomes if o.entity_type == "npc"]
        self.assertTrue(any(o.damage_consequences for o in npc_outcomes))

    def test_no_death_without_check_type(self) -> None:
        """Without death check type, participant stays ALIVE even at zero health."""
        # PC has 10 health, NPC deals 20 damage -> -10 <= 0
        encounter, participant, _ = self._setup_encounter(pc_health=10, npc_damage=20)
        result = resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)
        # Damage consequence should still be recorded
        npc_outcomes = [o for o in result.action_outcomes if o.entity_type == "npc"]
        self.assertTrue(any(o.damage_consequences for o in npc_outcomes))

    def test_bleed_out_advances_to_death_after_round(self) -> None:
        """A participant with an active Bleeding-Out condition at its terminal
        stage dies (life_state=DEAD) when the round-end resist check fails.

        Replaces the old DYING + dying_final_round → DEAD consumption: dying is
        now a Bleeding-Out condition, and resolve_round drives advance_bleed_out
        once per round (resist check + stage advance + terminal death).
        """
        from world.conditions.factories import (
            BleedingOutConditionFactory,
            ConditionInstanceFactory,
            ConditionStageFactory,
        )
        from world.covenants.factories import CovenantRoleFactory
        from world.traits.factories import CheckOutcomeFactory

        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        bleeding_pc = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=50,
            max_health=100,
            life_state=CharacterLifeState.ALIVE,
        )
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="TestRoomDying",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        # Bleeding-Out at a single terminal stage with a resist check that we
        # force to fail → advance_bleed_out marks the character DEAD.
        resist_check = CheckTypeFactory()
        bleed_out = BleedingOutConditionFactory()
        terminal_stage = ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Dying",
            resist_check_type=resist_check,
            resist_difficulty=20,
            rounds_to_next=None,
        )
        ConditionInstanceFactory(
            target=sheet.character,
            condition=bleed_out,
            current_stage=terminal_stage,
        )

        # Passives-only action (no focused_action) so no offense check fires
        # this round — that lets the single-shot force_check_outcome land on the
        # round-end bleed-out resist check (which is what we're exercising).
        CombatRoundAction.objects.create(
            participant=bleeding_pc,
            round_number=1,
            focused_action=None,
            focused_category=None,
        )

        from world.checks.test_helpers import force_check_outcome

        failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        with force_check_outcome(failure_outcome):
            resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
        self.assertIsNotNone(vitals.died_at)


class ApplyDamageToOpponentResistanceTests(EvenniaTestCase):
    """Tests for resistance modifier in apply_damage_to_opponent."""

    def test_resistance_modifier_reduces_damage(self) -> None:
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=10)

        opp = CombatOpponentFactory(soak_value=0, max_health=100, health=100)
        apply_condition(opp.objectdb, wet)

        result = apply_damage_to_opponent(opp, 15, damage_type=fire)
        # 15 raw - 0 soak - 10 resistance = 5
        self.assertEqual(result.damage_dealt, 5)

    def test_no_resistance_when_damage_type_null(self) -> None:
        opp = CombatOpponentFactory(soak_value=0, max_health=100, health=100)
        result = apply_damage_to_opponent(opp, 10, damage_type=None)
        self.assertEqual(result.damage_dealt, 10)

    def test_negative_resistance_amplifies_damage(self) -> None:
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        holy = DamageTypeFactory(name="Holy")
        cursed = ConditionTemplateFactory(name="Cursed")
        ConditionResistanceModifierFactory(condition=cursed, damage_type=holy, modifier_value=-5)

        opp = CombatOpponentFactory(soak_value=0, max_health=100, health=100)
        apply_condition(opp.objectdb, cursed)

        result = apply_damage_to_opponent(opp, 10, damage_type=holy)
        # 10 raw - 0 soak - (-5) resistance = 15
        self.assertEqual(result.damage_dealt, 15)

    def test_no_resistance_when_objectdb_null(self) -> None:
        from world.conditions.factories import DamageTypeFactory

        fire = DamageTypeFactory(name="Fire")
        opp = CombatOpponentFactory(soak_value=0, max_health=100, health=100)
        opp.objectdb = None
        opp.save(update_fields=["objectdb"])
        result = apply_damage_to_opponent(opp, 10, damage_type=fire)
        self.assertEqual(result.damage_dealt, 10)


class ApplyDamageToParticipantResistanceTests(EvenniaTestCase):
    """Tests for resistance modifier in apply_damage_to_participant."""

    def test_resistance_modifier_reduces_damage(self) -> None:
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )
        from world.conditions.services import apply_condition

        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        # Move character into the room so DAMAGE_PRE_APPLY can fire (location-scoped)
        participant.character_sheet.character.location = encounter.room
        participant.character_sheet.character.save()

        CharacterVitals.objects.get_or_create(
            character_sheet=participant.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        vitals.health = 100
        vitals.max_health = 100
        vitals.life_state = CharacterLifeState.ALIVE
        vitals.save()

        fire = DamageTypeFactory(name="Fire")
        wet = ConditionTemplateFactory(name="Wet")
        ConditionResistanceModifierFactory(condition=wet, damage_type=fire, modifier_value=8)
        apply_condition(participant.character_sheet.character, wet)

        result = apply_damage_to_participant(participant, 12, damage_type=fire)
        # 12 - 8 resistance = 4 (no threads on test character, so thread reduction = 0)
        self.assertEqual(result.damage_dealt, 4)


class NpcActionInteractionLazyCreationTests(TestCase):
    """Tests that the NPC-action Interaction is created lazily (only when a
    survivability tier fires) rather than eagerly before the per-target loop.

    Two invariants:
    - When no tier fires (whiff), no narrator-authored Interaction is created.
    - When a tier fires, exactly one narrator-authored Interaction is created,
      and the ConsequenceOutcome references it.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="LazyNPCAttack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="LazyFull"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="LazyPartial"
        )

    def _seed_knockout_pool(self):
        """Seed a knockout pool with an Unconscious-applying consequence.

        Returns the CheckOutcome that triggers knockout (failure tier).
        """
        from world.vitals.services import get_vitals_consequence_config

        failure_outcome = CheckOutcomeFactory(name="LazyKO-Failure", success_level=-1)
        unconscious = UnconsciousConditionFactory()
        consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])
        return failure_outcome

    def _setup_encounter(self, *, pc_health: int = 100, npc_damage: int = 5):
        """Create an encounter: 1 PC, 1 NPC (mook), NPC targeting PC."""
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=npc_damage)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=pc_health,
            max_health=100,
        )
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key=f"LazyNPCRoom-{pc_health}-{npc_damage}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)
        return encounter, participant, opponent

    def _npc_action_interactions(self):
        """Return the queryset of narrator-authored ACTION-mode Interactions.

        These are the only interactions created by create_npc_action_interaction;
        broadcast_action_outcome creates OUTCOME-mode interactions with the same
        narrator persona, so we must filter on mode=ACTION to isolate the signal.
        """
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        return Interaction.objects.filter(persona__name="Narrator", mode=InteractionMode.ACTION)

    def test_npc_action_whiff_creates_no_interaction(self) -> None:
        """When no survivability tier fires (PC at full health, small NPC damage),
        no narrator-authored ACTION Interaction should be created.

        Before fix: create_npc_action_interaction() is called eagerly → narrator
        ACTION interaction created unconditionally. After fix: it must not be created.
        """
        # PC full health (100/100), NPC deals 5 damage → health 95/100.
        # wound_difficulty=0 (5 < 50% of 100), death_difficulty=0 (95>0),
        # knockout_difficulty=0 (95% > 20%). No tier fires.
        encounter, _participant, _opponent = self._setup_encounter(pc_health=100, npc_damage=5)

        count_before = self._npc_action_interactions().count()
        resolve_round(encounter)
        count_after = self._npc_action_interactions().count()

        self.assertEqual(
            count_after,
            count_before,
            "No narrator ACTION Interaction should be created when no tier fires (whiff)",
        )

    def test_npc_action_tier_fire_creates_one_shared_interaction(self) -> None:
        """When a survivability tier fires (PC in knockout zone, knockout pool
        seeded, forced failure outcome), exactly one narrator ACTION Interaction
        is created, and the ConsequenceOutcome references it.
        """
        from world.checks.outcome_models import ConsequenceOutcome

        failure_outcome = self._seed_knockout_pool()

        # PC at 10/100 health (10%), NPC deals 5 damage → health 5/100 (5%).
        # knockout_difficulty > 0, death_difficulty=0 (5>0), wound_difficulty=0 (5<50).
        encounter, participant, _opponent = self._setup_encounter(pc_health=10, npc_damage=5)

        count_before = self._npc_action_interactions().count()

        with force_check_outcome(failure_outcome):
            resolve_round(encounter)

        new_count = self._npc_action_interactions().count() - count_before
        self.assertEqual(
            new_count,
            1,
            "Exactly one narrator ACTION Interaction should be created when a tier fires",
        )

        # The ConsequenceOutcome must reference that interaction.
        outcomes = list(ConsequenceOutcome.objects.filter(character=participant.character_sheet))
        self.assertEqual(len(outcomes), 1, "Exactly one ConsequenceOutcome should be recorded")
        npc_action_interaction = self._npc_action_interactions().order_by("-timestamp").first()
        self.assertIsNotNone(npc_action_interaction)
        self.assertEqual(
            outcomes[0].combat_interaction_id,
            npc_action_interaction.pk,
            "ConsequenceOutcome must reference the narrator ACTION Interaction",
        )
