"""Tests for capability source aggregation service."""

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterTechnique
from world.mechanics.constants import CapabilitySourceType
from world.mechanics.factories import TraitCapabilityDerivationFactory
from world.mechanics.services import get_capability_sources_for_character
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType


class TechniqueSourceTests(TestCase):
    """Tests for _get_technique_sources."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.capability = CapabilityTypeFactory(name="fire_control")
        cls.resonance = ResonanceFactory(name="Flame")
        cls.gift = GiftFactory(name="Pyromancy")
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(
            name="Flame Lance",
            gift=cls.gift,
            intensity=10,
        )
        cls.grant = TechniqueCapabilityGrantFactory(
            technique=cls.technique,
            capability=cls.capability,
            base_value=5,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechnique.objects.create(
            character=cls.sheet,
            technique=cls.technique,
        )

    def test_technique_source(self) -> None:
        """Technique with CapabilityGrant produces a source with correct values."""
        sources = get_capability_sources_for_character(self.character)
        technique_sources = [s for s in sources if s.source_type == CapabilitySourceType.TECHNIQUE]
        assert len(technique_sources) == 1

        src = technique_sources[0]
        assert src.capability_name == "fire_control"
        assert src.capability_id == self.capability.id
        # base_value=5 + intensity_multiplier=1.0 * intensity=10 = 15
        assert src.value == 15
        assert src.source_name == "Flame Lance"
        assert src.source_id == self.technique.id
        # effect_property_ids are derived from Property records matching resonance names
        assert isinstance(src.effect_property_ids, list)

    def test_zero_value_excluded(self) -> None:
        """Grants with value <= 0 are not returned."""
        cap2 = CapabilityTypeFactory(name="ice_control")
        TechniqueCapabilityGrantFactory(
            technique=self.technique,
            capability=cap2,
            base_value=0,
            intensity_multiplier=Decimal(0),
        )
        sources = get_capability_sources_for_character(self.character)
        ice_sources = [s for s in sources if s.capability_name == "ice_control"]
        assert len(ice_sources) == 0


class TraitSourceTests(TestCase):
    """Tests for _get_trait_sources."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="TraitTestChar")
        cls.capability = CapabilityTypeFactory(name="physical_force")
        cls.trait = Trait.objects.create(
            name="test_strength_src",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        cls.derivation = TraitCapabilityDerivationFactory(
            trait=cls.trait,
            capability=cls.capability,
            base_value=0,
            trait_multiplier=Decimal("1.00"),
        )
        CharacterTraitValue.objects.create(
            character=cls.character,
            trait=cls.trait,
            value=20,
        )

    def test_trait_source(self) -> None:
        """Trait derivation produces a source with calculated value."""
        sources = get_capability_sources_for_character(self.character)
        trait_sources = [s for s in sources if s.source_type == CapabilitySourceType.TRAIT]
        assert len(trait_sources) == 1

        src = trait_sources[0]
        assert src.capability_name == "physical_force"
        assert src.value == 20  # base=0 + 1.0 * 20
        assert src.source_name == "test_strength_src"
        assert src.source_id == self.trait.id

    def test_zero_trait_value_excluded(self) -> None:
        """Trait with value 0 produces no source."""
        char2 = ObjectDB.objects.create(db_key="NoTraitChar")
        CharacterTraitValue.objects.create(
            character=char2,
            trait=self.trait,
            value=0,
        )
        sources = get_capability_sources_for_character(char2)
        trait_sources = [s for s in sources if s.source_type == CapabilitySourceType.TRAIT]
        assert len(trait_sources) == 0


class MultipleSameCapabilityTests(TestCase):
    """Test that multiple sources for the same capability produce separate entries."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.capability = CapabilityTypeFactory(name="multi_cap")

        # Source 1: technique
        cls.gift = GiftFactory(name="MultiGift")
        cls.technique = TechniqueFactory(
            name="MultiTech",
            gift=cls.gift,
            intensity=5,
        )
        TechniqueCapabilityGrantFactory(
            technique=cls.technique,
            capability=cls.capability,
            base_value=3,
            intensity_multiplier=Decimal("1.0"),
        )
        CharacterTechnique.objects.create(
            character=cls.sheet,
            technique=cls.technique,
        )

        # Source 2: trait derivation
        cls.trait = Trait.objects.create(
            name="test_multi_trait",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        TraitCapabilityDerivationFactory(
            trait=cls.trait,
            capability=cls.capability,
            base_value=2,
            trait_multiplier=Decimal("1.00"),
        )
        CharacterTraitValue.objects.create(
            character=cls.character,
            trait=cls.trait,
            value=10,
        )

    def test_multiple_sources_same_capability(self) -> None:
        """Each source produces a separate CapabilitySource entry."""
        sources = get_capability_sources_for_character(self.character)
        multi_sources = [s for s in sources if s.capability_name == "multi_cap"]
        assert len(multi_sources) == 2

        source_types = {s.source_type for s in multi_sources}
        assert CapabilitySourceType.TECHNIQUE in source_types
        assert CapabilitySourceType.TRAIT in source_types
