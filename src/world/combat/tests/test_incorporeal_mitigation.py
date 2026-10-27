"""Incorporeal means near-total mitigation, never untargetable (#4742).

Cross-system: the vitals config's Physical designation, condition resistance and
damage-dealt rows, the combat damage seams, knockback ordering and held ground.
Scenario numbers match the spec on the issue.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType, PositionDestination
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import CombatTechniqueResolver, apply_damage_to_participant
from world.combat.services.held_ground import encounter_holds
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionDamageDealtModifier
from world.conditions.services import apply_condition, resolved_damage_type
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import get_vitals_consequence_config

SEVERITY = 6  # 10 Physical resistance per severity point -> 60


def _designate_physical():
    physical = DamageTypeFactory(name="Physical")
    config = get_vitals_consequence_config()
    config.physical_damage_type = physical
    config.save(update_fields=["physical_damage_type"])
    return physical


def _smoke_form(physical, *, intangible=True):
    category = ConditionCategoryFactory(grants_intangibility=intangible)
    smoke = ConditionTemplateFactory(category=category)
    ConditionResistanceModifierFactory(
        condition=smoke, damage_type=physical, modifier_value=10, scales_with_severity=True
    )
    ConditionDamageDealtModifier.objects.create(
        condition=smoke, damage_type=physical, modifier_percent=-75
    )
    return smoke


def _pc(encounter=None):
    participant = CombatParticipantFactory(**({"encounter": encounter} if encounter else {}))
    CharacterVitalsFactory(
        character_sheet=participant.character_sheet,
        health=500,
        max_health=500,
        base_max_health=500,
    )
    return participant


class UntypedDamageIsPhysicalTests(TestCase):
    def test_untyped_resolves_to_the_designated_row(self):
        physical = _designate_physical()
        fire = DamageTypeFactory(name="Fire")

        self.assertEqual(resolved_damage_type(None), physical)
        self.assertEqual(resolved_damage_type(fire), fire)

    def test_untyped_stays_untyped_with_no_designation(self):
        self.assertIsNone(resolved_damage_type(None))

    def test_existing_physical_vulnerability_now_meets_untyped_weapon_hits(self):
        """A Flanked-style Physical -15 row raises a 30-point untyped hit to 45."""
        physical = _designate_physical()
        flanked = ConditionTemplateFactory()
        ConditionResistanceModifierFactory(
            condition=flanked, damage_type=physical, modifier_value=-15
        )
        participant = _pc()
        apply_condition(participant.character_sheet.character, flanked)

        self.assertEqual(apply_damage_to_participant(participant, 30).damage_dealt, 45)


class IncorporealResistanceTests(TestCase):
    def setUp(self):
        self.physical = _designate_physical()
        self.participant = _pc()
        apply_condition(
            self.participant.character_sheet.character,
            _smoke_form(self.physical),
            severity=SEVERITY,
        )

    def test_scenario_1_ordinary_untyped_hit_does_nothing(self):
        self.assertEqual(apply_damage_to_participant(self.participant, 40).damage_dealt, 0)

    def test_scenario_2_overwhelming_hit_gets_through(self):
        self.assertEqual(apply_damage_to_participant(self.participant, 100).damage_dealt, 40)

    def test_scenario_3_fire_is_untouched(self):
        fire = DamageTypeFactory(name="Fire")
        result = apply_damage_to_participant(self.participant, 40, damage_type=fire)
        self.assertEqual(result.damage_dealt, 40)


class KnockbackNeedsAHitThatSurvivesResistanceTests(TestCase):
    def setUp(self):
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.physical = _designate_physical()
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = _pc(encounter)
        self.defender = self.participant.character_sheet.character
        self.defender.db_location = encounter.room
        self.defender.save(update_fields=["db_location"])
        self.opponent = CombatOpponentFactory(encounter=encounter)
        attacker_pos = PositionFactory(room=encounter.room, name="attacker_spot")
        self.defender_pos = PositionFactory(room=encounter.room, name="defender_spot")
        self.far_pos = PositionFactory(room=encounter.room, name="far_spot")
        connect_positions(attacker_pos, self.defender_pos)
        connect_positions(self.defender_pos, self.far_pos)
        place_in_position(self.opponent.objectdb, attacker_pos)
        place_in_position(self.defender, self.defender_pos)
        self.pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        ConsequencePoolEntryFactory(pool=self.pool, consequence=consequence)
        apply_condition(self.defender, _smoke_form(self.physical), severity=SEVERITY)

    def _hit(self, amount):
        with patch("world.combat.services._try_interpose"):
            apply_damage_to_participant(
                self.participant, amount, source=self.opponent, on_hit_pool=self.pool
            )

    def test_scenario_1_absorbed_hit_does_not_move_her(self):
        self._hit(40)
        self.assertEqual(position_of(self.defender).pk, self.defender_pos.pk)

    def test_scenario_2_hit_that_gets_through_moves_her(self):
        self._hit(100)
        self.assertEqual(position_of(self.defender).pk, self.far_pos.pk)


class OutgoingDamageDealtTests(TestCase):
    """Scenario 4: her Physical strikes are cut, her Fire strikes are not."""

    def setUp(self):
        self.physical = _designate_physical()
        self.fire = DamageTypeFactory(name="Fire")
        encounter = CombatEncounterFactory(round_number=1)
        self.opponent = CombatOpponentFactory(
            encounter=encounter, tier=OpponentTier.MOOK, health=500, max_health=500
        )
        self.participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=CharacterSheetFactory()
        )
        technique = TechniqueFactory(
            gift=GiftFactory(), effect_type=EffectTypeFactory(), damage_profile=False
        )
        self.untyped_profile = TechniqueDamageProfileFactory(
            technique=technique, base_damage=40, damage_type=None
        )
        self.fire_profile = TechniqueDamageProfileFactory(
            technique=technique, base_damage=40, damage_type=self.fire
        )
        action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=self.opponent,
            effort_level=EffortLevel.MEDIUM,
        )
        self.resolver = CombatTechniqueResolver(
            participant=self.participant,
            action=action,
            pull_flat_bonus=0,
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=CheckTypeFactory(),
            offense_check_fn=None,
        )

    def _damage(self, profile):
        return self.resolver._profile_damage(
            profile,
            None,
            self.opponent,
            sl=1,
            multiplier=Decimal("1.0"),
            eff_intensity=10,
        )

    def test_physical_cut_to_a_quarter_fire_untouched(self):
        plain_before, plain_type = self._damage(self.untyped_profile)
        fire_before, _ = self._damage(self.fire_profile)
        self.assertEqual(plain_type, self.physical)

        apply_condition(
            self.participant.character_sheet.character,
            _smoke_form(self.physical),
            severity=SEVERITY,
        )

        self.assertEqual(self._damage(self.untyped_profile)[0], int(plain_before * 25 / 100))
        self.assertEqual(self._damage(self.fire_profile)[0], fire_before)


class IncorporealHoldsNoGroundTests(TestCase):
    """Scenario 6: targetable again, but her position blocks nobody."""

    def test_intangible_pc_is_dropped_from_holds_even_when_handed_in(self):
        physical = _designate_physical()
        encounter = CombatEncounterFactory()
        solid = _pc(encounter)
        smoke = _pc(encounter)
        for participant, name in ((solid, "solid_spot"), (smoke, "smoke_spot")):
            character = participant.character_sheet.character
            character.db_location = encounter.room
            character.save(update_fields=["db_location"])
            place_in_position(character, PositionFactory(room=encounter.room, name=name))
        apply_condition(smoke.character_sheet.character, _smoke_form(physical))
        solid_position = position_of(solid.character_sheet.character).pk
        smoke_position = position_of(smoke.character_sheet.character).pk

        for handed_in in (None, [solid, smoke]):
            with self.subTest(handed_in=handed_in is not None):
                holds = encounter_holds(encounter, acting_participants=handed_in)
                self.assertIn(solid_position, holds.acting_pcs)
                self.assertNotIn(smoke_position, holds.acting_pcs)


class NpcAttackerDamageDealtTests(TestCase):
    """An NPC opponent in smoke form hits a quarter as hard with Physical, full with Fire."""

    def test_npc_body_rows_cut_its_physical_hits(self):
        from world.conditions.services import scaled_outgoing_damage

        physical = _designate_physical()
        fire = DamageTypeFactory(name="Fire")
        opponent = CombatOpponentFactory()
        apply_condition(opponent.objectdb, _smoke_form(physical))

        self.assertEqual(scaled_outgoing_damage(opponent.objectdb, 40, None), 10)
        self.assertEqual(scaled_outgoing_damage(opponent.objectdb, 40, fire), 40)
        self.assertEqual(scaled_outgoing_damage(None, 40, None), 40)
