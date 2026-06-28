"""Tests for derived-on-read NPC allegiance (#1590, ADR-0058, ADR-0014)."""

from django.test import TestCase

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
from world.conditions.models import ConditionTemplate
from world.conditions.services import bulk_apply_conditions
from world.conditions.types import BulkConditionApplication
from world.npc_services.allegiance import derive_allegiance


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
