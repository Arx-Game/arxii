"""Tests for combat damage resolution service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus, OpponentStatus, OpponentTier
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
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.vitals.constants import CharacterStatus
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
        self.vitals.status = CharacterStatus.ALIVE
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

    def test_force_death_sets_dying(self) -> None:
        apply_damage_to_participant(self.participant, 10, force_death=True)
        self.vitals.refresh_from_db()
        assert self.vitals.status == CharacterStatus.DYING
        assert self.vitals.dying_final_round is True


class KnockoutDeathProcessingTest(TestCase):
    """Tests for knockout/death processing during NPC action resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()

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
            status=CharacterStatus.ALIVE,
        )
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_attack)
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=opponent,
        )
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(participant)
        return encounter, participant, opponent

    def test_knockout_at_low_health(self) -> None:
        """Participant at low health after NPC damage becomes UNCONSCIOUS."""
        # PC has 15 health, NPC deals 5 damage -> 10/100 = 10% < 20%
        encounter, participant, _ = self._setup_encounter(pc_health=15, npc_damage=5)
        resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        self.assertEqual(vitals.status, CharacterStatus.UNCONSCIOUS)

    def test_death_at_zero_health(self) -> None:
        """Participant at 0 health becomes DYING."""
        # PC has 10 health, NPC deals 20 damage -> -10 <= 0
        encounter, participant, _ = self._setup_encounter(pc_health=10, npc_damage=20)
        resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=participant.character_sheet)
        # Should be DEAD because dying_final_round is consumed in same round
        self.assertEqual(vitals.status, CharacterStatus.DEAD)

    def test_dying_consumed_after_round(self) -> None:
        """DYING participant with dying_final_round becomes DEAD after resolve."""
        from world.covenants.factories import CovenantRoleFactory

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
        dying_pc = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=CovenantRoleFactory(speed_rank=1),
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=50,
            max_health=100,
            status=CharacterStatus.DYING,
            dying_final_round=True,
        )
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_attack)
        CombatRoundAction.objects.create(
            participant=dying_pc,
            round_number=1,
            focused_category="physical",
            focused_action=technique,
            focused_target=encounter.opponents.first(),
        )

        resolve_round(encounter)

        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        self.assertEqual(vitals.status, CharacterStatus.DEAD)
        self.assertFalse(vitals.dying_final_round)
