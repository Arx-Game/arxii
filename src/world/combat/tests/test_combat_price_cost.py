"""A combat cast decides whether it pays its price when the round RESOLVES (#4099).

The action is declared first and resolved later; the component is checked at
resolution, so dropping it after declaring means the cast goes off without the price,
and carrying it at resolution spends it. Driven through ``resolve_round``, the
production round driver.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_round
from world.conditions.factories import (
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    PriceFactory,
    TechniqueFactory,
)
from world.magic.models import PriceComponentRequirement
from world.magic.tests.price_cost_helpers import carry
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

PRICE_LEDGER_LABEL = "price power"


class CombatPriceCheckedAtResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        cls.needle = ItemTemplateFactory(name="Combat needle")
        cls.weary = ConditionTemplateFactory(name="Combat weary")
        cls.price = PriceFactory(power_bonus=9, inflicted_condition=cls.weary)
        PriceComponentRequirement.objects.create(
            restriction=cls.price, item_template=cls.needle, quantity=1
        )

    def _declare(self):
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=30)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        room = ObjectDBFactory(db_key="PriceRoom", db_typeclass_path="typeclasses.rooms.Room")
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CharacterTechniqueFactory(character=sheet, technique=technique, price=self.price)
        sheet.character.techniques.invalidate()
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        return encounter, sheet, action

    def _resolve(self, encounter) -> None:
        resolve_round(encounter, offense_check_fn=lambda *_a, **_k: MagicMock(success_level=2))

    def _price_rows(self, action) -> list:
        action.refresh_from_db()
        return [
            row
            for row in action.interaction.power_ledger_entries.all()
            if row.source_label == PRICE_LEDGER_LABEL
        ]

    def test_component_carried_at_resolution_is_spent(self) -> None:
        encounter, sheet, action = self._declare()
        stack = carry(sheet.character, self.needle, quantity=1)

        self._resolve(encounter)

        self.assertFalse(ItemInstance.objects.filter(pk=stack.pk).exists())
        self.assertEqual([row.amount for row in self._price_rows(action)], [9])
        self.assertTrue(
            ConditionInstance.objects.filter(target=sheet.character, condition=self.weary).exists()
        )

    def test_component_dropped_after_declaring_is_not_paid(self) -> None:
        encounter, sheet, action = self._declare()
        stack = carry(sheet.character, self.needle, quantity=1)
        # Declared while carrying it; gone by the time the round resolves.
        stack.delete()
        sheet.character.carried_items.invalidate()

        self._resolve(encounter)

        action.refresh_from_db()
        self.assertIsNotNone(action.interaction_id, "the cast still resolves")
        self.assertEqual(self._price_rows(action), [])
        self.assertFalse(
            ConditionInstance.objects.filter(target=sheet.character, condition=self.weary).exists()
        )
