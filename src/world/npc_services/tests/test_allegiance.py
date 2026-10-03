"""Tests for derived-on-read NPC allegiance (#1590, #4091, ADR-0058, ADR-0014)."""

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.combat.constants import CombatAllegiance
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.conditions.charm_content import ensure_charm_content
from world.conditions.constants import (
    CALM_CONDITION_NAME,
    CHARM_CONDITION_NAME,
    Allegiance,
)
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionTemplate
from world.conditions.services import bulk_apply_conditions
from world.conditions.types import BulkConditionApplication
from world.npc_services.allegiance import derive_allegiance, effective_allegiances


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_charm_content gates on #2698
class DeriveAllegianceTest(TestCase):
    def setUp(self):
        ensure_charm_content()
        self.encounter = CombatEncounterFactory()
        self.enemy_opponent = CombatOpponentFactory(encounter=self.encounter)
        self.pc_participant = CombatParticipantFactory(encounter=self.encounter)

    def _apply_charm(self, opponent, source):
        template = ConditionTemplate.objects.get(name=CHARM_CONDITION_NAME)
        bulk_apply_conditions(
            [BulkConditionApplication(target=opponent.objectdb, template=template)],
            source_character=source.character_sheet.character,
        )

    def _apply_calm(self, opponent):
        template = ConditionTemplate.objects.get(name=CALM_CONDITION_NAME)
        bulk_apply_conditions(
            [BulkConditionApplication(target=opponent.objectdb, template=template)],
        )

    def test_no_objectdb_is_enemy(self):
        # An opponent with no in-world ObjectDB cannot be charmed -> ENEMY.
        opponent = CombatOpponentFactory(encounter=self.encounter, objectdb_id=None)
        self.assertEqual(derive_allegiance(opponent, self.encounter), Allegiance.ENEMY)

    def test_enemy_by_default(self):
        self.assertEqual(derive_allegiance(self.enemy_opponent, self.encounter), Allegiance.ENEMY)

    def test_charmed_ally_of_caster(self):
        self._apply_charm(self.enemy_opponent, source=self.pc_participant)
        self.assertEqual(
            derive_allegiance(self.enemy_opponent, self.encounter),
            Allegiance.ALLY_OF_CASTER,
        )

    def test_calmed_neutral(self):
        self._apply_calm(self.enemy_opponent)
        self.assertEqual(derive_allegiance(self.enemy_opponent, self.encounter), Allegiance.NEUTRAL)

    def test_calm_overrides_when_no_charm(self):
        # If both somehow present, charm wins (it is the stronger compulsion).
        self._apply_calm(self.enemy_opponent)
        self._apply_charm(self.enemy_opponent, source=self.pc_participant)
        self.assertEqual(
            derive_allegiance(self.enemy_opponent, self.encounter),
            Allegiance.ALLY_OF_CASTER,
        )


class EffectiveAllegianceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Break 4091")
        cls.charm = ConditionTemplateFactory(
            name="Velvet 4091",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        cls.turn = ConditionTemplateFactory(
            name="Sow Doubt 4091",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )
        cls.calm = ConditionTemplateFactory(
            name="Still 4091",
            sets_allegiance=Allegiance.NEUTRAL,
            allegiance_break_check_type=check,
        )
        cls.plain = ConditionTemplateFactory(name="Dazed 4091")
        cls.encounter = CombatEncounterFactory()

    def test_precedence_charm_turned_calm(self):
        opp = CombatOpponentFactory(encounter=self.encounter)
        for template in (self.calm, self.turn, self.charm):
            ConditionInstanceFactory(target=opp.objectdb, condition=template)
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.ALLY_OF_CASTER)

    def test_turned_beats_calm(self):
        opp = CombatOpponentFactory(encounter=self.encounter)
        ConditionInstanceFactory(target=opp.objectdb, condition=self.calm)
        ConditionInstanceFactory(target=opp.objectdb, condition=self.turn)
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.TURNED)

    def test_unflagged_condition_is_ignored(self):
        opp = CombatOpponentFactory(encounter=self.encounter)
        ConditionInstanceFactory(target=opp.objectdb, condition=self.plain)
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.ENEMY)

    def test_summon_is_ally(self):
        opp = CombatOpponentFactory(encounter=self.encounter, allegiance=CombatAllegiance.ALLY)
        self.assertEqual(effective_allegiances([opp])[opp.pk], Allegiance.ALLY_OF_CASTER)

    def test_one_query_for_many(self):
        opps = [CombatOpponentFactory(encounter=self.encounter) for _ in range(4)]
        for opp in opps:
            ConditionInstanceFactory(target=opp.objectdb, condition=self.turn)
        with self.assertNumQueries(1):
            result = effective_allegiances(opps)
        self.assertEqual(set(result.values()), {Allegiance.TURNED})

    def test_applied_since_filters_older_charm(self):
        from datetime import timedelta

        from django.utils import timezone

        opp = CombatOpponentFactory(encounter=self.encounter)
        ConditionInstanceFactory(target=opp.objectdb, condition=self.charm)
        later = timezone.now() + timedelta(seconds=5)
        self.assertEqual(
            effective_allegiances([opp], applied_since=later)[opp.pk], Allegiance.ENEMY
        )
