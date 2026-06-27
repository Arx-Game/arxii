"""Per-character comfort readout (#1522): clothing mitigation, resonance swing, injury, bands.

A character feels the room's exposure minus what their worn clothing mitigates (floored per axis),
plus injury — resolved to a named band with the biting reasons. Resonance-imbued clothing is a
huge swing, so a scantily-clad-but-warded character stays comfortable.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    EquippedItemFactory,
    GarmentMitigationFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.locations.character_comfort import character_comfort_summary
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.magic.factories import ResonanceFactory
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.vitals.factories import CharacterVitalsFactory


class CharacterComfortTests(TestCase):
    def _cold_room(self, cold: int = 50):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        if cold:
            LocationValueModifier.objects.create(
                parent_type=LocationParentType.AREA, area=ward, stat_key=StatKey.COLD, value=cold
            )
        return profile.objectdb

    def _character_in(self, room):
        sheet = CharacterSheetFactory()
        character = sheet.character
        character.location = room
        return sheet, character

    def _wear(self, character, template):
        EquippedItemFactory(
            character=character, item_instance=ItemInstanceFactory(template=template)
        )

    def test_unclothed_character_feels_the_cold(self) -> None:
        _, character = self._character_in(self._cold_room(50))
        summary = character_comfort_summary(character)
        assert summary.discomfort == 50
        assert summary.reasons == ["cold"]
        assert summary.band == "Moderately uncomfortable"  # 25 ≤ 50 < 60

    def test_clothing_mitigates_the_cold_before_the_floor(self) -> None:
        _, character = self._character_in(self._cold_room(50))
        coat = ItemTemplateFactory(name="Wool Coat")
        GarmentMitigationFactory(item_template=coat, stat_key=StatKey.COLD, value=30)
        self._wear(character, coat)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 20  # max(0, 50 - 30)
        assert summary.band == "Slightly uncomfortable"

    def test_over_mitigation_floors_at_zero(self) -> None:
        _, character = self._character_in(self._cold_room(50))
        parka = ItemTemplateFactory(name="Arctic Parka")
        GarmentMitigationFactory(item_template=parka, stat_key=StatKey.COLD, value=80)
        self._wear(character, parka)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 0  # not negative
        assert summary.band == "Comfortable"
        assert summary.reasons == []

    def test_resonant_clothing_is_a_huge_swing(self) -> None:
        # Scantily clad but warded: a fire-woven cloak (resonance, big value) shrugs off the cold.
        _, character = self._character_in(self._cold_room(50))
        cloak = ItemTemplateFactory(name="Fire-Woven Cloak")
        GarmentMitigationFactory(
            item_template=cloak,
            stat_key=StatKey.COLD,
            value=200,
            resonance=ResonanceFactory(),
        )
        self._wear(character, cloak)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 0
        assert summary.band == "Comfortable"

    def test_a_warding_modifier_mitigates_like_clothing(self) -> None:
        # Comfort mitigation is general: a spell/ward (a CharacterModifier on the cold_mitigation
        # target) reduces felt cold exactly like a garment does.
        sheet, character = self._character_in(self._cold_room(50))
        target = ModifierTargetFactory(
            name="cold_mitigation", category=ModifierCategoryFactory(name="comfort_mitigation")
        )
        source = DistinctionModifierSourceFactory(distinction_effect__target=target)
        CharacterModifierFactory(character=sheet, value=30, source=source, target=target)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 20  # 50 cold − 30 ward
        assert summary.band == "Slightly uncomfortable"

    def test_clothing_and_a_ward_stack(self) -> None:
        sheet, character = self._character_in(self._cold_room(50))
        coat = ItemTemplateFactory(name="Wool Coat")
        GarmentMitigationFactory(item_template=coat, stat_key=StatKey.COLD, value=20)
        self._wear(character, coat)
        target = ModifierTargetFactory(
            name="cold_mitigation", category=ModifierCategoryFactory(name="comfort_mitigation")
        )
        source = DistinctionModifierSourceFactory(distinction_effect__target=target)
        CharacterModifierFactory(character=sheet, value=30, source=source, target=target)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 0  # 50 − (20 coat + 30 ward), floored

    def test_injury_adds_discomfort_and_a_reason(self) -> None:
        sheet, character = self._character_in(self._cold_room(0))  # no environmental exposure
        CharacterVitalsFactory(
            character_sheet=sheet, health=50, max_health=100, base_max_health=100
        )
        summary = character_comfort_summary(character)
        assert summary.injury == 20  # (1 - 0.5) * 40
        assert summary.discomfort == 20
        assert "injured" in summary.reasons

    def test_cold_and_injured_reads_both(self) -> None:
        sheet, character = self._character_in(self._cold_room(50))
        CharacterVitalsFactory(character_sheet=sheet, health=0, max_health=100, base_max_health=100)
        summary = character_comfort_summary(character)
        assert summary.discomfort == 90  # 50 cold + 40 injury
        assert summary.band == "Very uncomfortable"  # 60 ≤ 90 < 120
        assert summary.reasons == ["cold", "injured"]

    def test_nowhere_is_comfortable(self) -> None:
        sheet = CharacterSheetFactory()
        character = sheet.character
        character.location = None
        summary = character_comfort_summary(character)
        assert summary.band == "Comfortable"
        assert summary.discomfort == 0
