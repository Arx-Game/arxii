"""E2E: PerformRitualAction consumes a touchstone-mode requirement (#707).

NOTE: deviates from the task brief's verbatim ritual setup — the brief's SERVICE
dispatch to ``world.magic.services.touchstones.attune_touchstone`` targets a module
Task 7 creates, which does not exist yet at Task 6 time. Using CEREMONY dispatch
here instead (the same zero-dependency dispatch kind already proven in
``actions/tests/test_perform_ritual_action.py``) exercises the exact same code
path this task rewires — ``_validate_components`` runs and consumes components
before the execution_kind branch — without a forward reference to unbuilt code.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.ritual import PerformRitualAction
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
)


class PerformRitualActionTouchstoneTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.sheet_data = self.sheet
        self.resonance = ResonanceFactory(name="Praedari")
        self.tier = ResonanceTierFactory(name="Faint", tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier
        )
        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)
        self.instance = ItemInstanceFactory(
            template=self.template, attuned_to_character_sheet=self.sheet
        )

    def test_touchstone_requirement_is_consumed_on_perform(self) -> None:
        action = PerformRitualAction()
        result = action.execute(
            self.character, ritual=self.ritual, components_provided=[self.instance]
        )
        assert result.success
        assert not ItemInstance.objects.filter(pk=self.instance.pk).exists()
