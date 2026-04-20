from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import CantripArchetype
from world.magic.factories import (
    EffectTypeFactory,
    FacetFactory,
    GiftFactory,
    MishapPoolTierFactory,
    ResonanceFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    Facet,
    Gift,
    MishapPoolTier,
    Reincarnation,
    Technique,
)
from world.magic.types import (
    AffinityType,
)

# Note: Power, CharacterPower, IntensityTier, and AnimaRitualType have been
# replaced by Technique, CharacterTechnique, and the new anima ritual system.


class CharacterAuraModelTests(TestCase):
    """Tests for the CharacterAura model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.aura = CharacterAura.objects.create(
            character=cls.character,
            celestial=Decimal("10.00"),
            primal=Decimal("75.00"),
            abyssal=Decimal("15.00"),
        )

    def test_aura_str(self):
        """Test string representation."""
        self.assertIn(str(self.character), str(self.aura))

    def test_aura_total_equals_100(self):
        """Test that aura percentages sum to 100."""
        total = self.aura.celestial + self.aura.primal + self.aura.abyssal
        self.assertEqual(total, Decimal("100.00"))

    def test_aura_one_per_character(self):
        """Test that a character can only have one aura."""
        with self.assertRaises(ValidationError):
            CharacterAura.objects.create(
                character=self.character,
                celestial=Decimal("33.33"),
                primal=Decimal("33.34"),
                abyssal=Decimal("33.33"),
            )

    def test_aura_dominant_affinity(self):
        """Test dominant_affinity property."""
        self.assertEqual(self.aura.dominant_affinity, AffinityType.PRIMAL)

    def test_aura_validation_requires_100_percent(self):
        """Test that aura validation requires percentages to sum to 100."""
        character2 = CharacterFactory()
        with self.assertRaises(ValidationError):
            CharacterAura.objects.create(
                character=character2,
                celestial=Decimal("50.00"),
                primal=Decimal("50.00"),
                abyssal=Decimal("50.00"),  # Total is 150, should fail
            )


class CharacterResonanceModelTests(TestCase):
    """Tests for the CharacterResonance model (post Spec A §2.2 merge)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.shadows = ResonanceFactory(name="Shadows")
        cls.char_resonance = CharacterResonance.objects.create(
            character_sheet=cls.sheet,
            resonance=cls.shadows,
            flavor_text="A shadowy presence lingers around them.",
        )

    def test_character_resonance_str(self):
        """Test string representation."""
        result = str(self.char_resonance)
        self.assertIn("Shadows", result)
        self.assertIn(str(self.sheet), result)

    def test_character_resonance_unique_together(self):
        """Test that a character can't have duplicate resonances."""
        with self.assertRaises(IntegrityError):
            CharacterResonance.objects.create(
                character_sheet=self.sheet,
                resonance=self.shadows,
            )

    def test_character_can_have_multiple_resonances(self):
        """Test that a character can have multiple different resonances."""
        majesty = ResonanceFactory(name="Majesty")
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=majesty,
        )
        self.assertEqual(self.sheet.resonances.count(), 2)


# =============================================================================
# Phase 2: Gifts & Techniques Tests
# =============================================================================


class GiftModelTests(TestCase):
    """Tests for the Gift model."""

    @classmethod
    def setUpTestData(cls):
        cls.shadows = ResonanceFactory(name="ShadowsGift")
        cls.gift = Gift.objects.create(
            name="Shadow Majesty",
            description="Dark regal influence.",
        )
        cls.gift.resonances.add(cls.shadows)

    def test_gift_str(self):
        """Test string representation."""
        self.assertEqual(str(self.gift), "Shadow Majesty")

    def test_gift_natural_key(self):
        """Test natural key lookup on name."""
        self.assertEqual(
            Gift.objects.get_by_natural_key("Shadow Majesty"),
            self.gift,
        )

    def test_gift_name_unique(self):
        """Test that gift name is unique."""
        with self.assertRaises(IntegrityError):
            Gift.objects.create(name="Shadow Majesty")

    def test_gift_has_resonances(self):
        """Test that gift can have resonances."""
        self.assertEqual(self.gift.resonances.count(), 1)
        self.assertIn(self.shadows, self.gift.resonances.all())


class CharacterGiftModelTests(TestCase):
    """Tests for the CharacterGift model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.gift = Gift.objects.create(name="Shadow Majesty")
        cls.char_gift = CharacterGift.objects.create(
            character=cls.sheet,
            gift=cls.gift,
        )

    def test_character_gift_str(self):
        """Test string representation."""
        result = str(self.char_gift)
        self.assertIn("Shadow Majesty", result)

    def test_character_gift_unique_together(self):
        """Test that character can't have duplicate gifts."""
        with self.assertRaises(IntegrityError):
            CharacterGift.objects.create(
                character=self.sheet,
                gift=self.gift,
            )


# =============================================================================
# Phase 3: Anima System Tests
# =============================================================================


class CharacterAnimaModelTests(TestCase):
    """Tests for the CharacterAnima model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.anima = CharacterAnima.objects.create(
            character=cls.character,
            current=8,
            maximum=10,
        )

    def test_anima_str(self):
        """Test string representation."""
        result = str(self.anima)
        self.assertIn(str(self.character), result)
        self.assertIn("8/10", result)

    def test_anima_one_per_character(self):
        """Test that a character can only have one anima record."""
        with self.assertRaises(ValidationError):
            CharacterAnima.objects.create(
                character=self.character,
                current=5,
                maximum=10,
            )

    def test_anima_current_cannot_exceed_maximum(self):
        """Test that current anima cannot exceed maximum."""
        character2 = CharacterFactory()
        with self.assertRaises(ValidationError):
            CharacterAnima.objects.create(
                character=character2,
                current=15,
                maximum=10,
            )

    def test_anima_update_current(self):
        """Test that current anima can be updated."""
        self.anima.current = 5
        self.anima.save()
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 5)


# CharacterAnimaRitual tests are in test_anima_ritual.py


# =============================================================================
# Legacy Thread family tests removed in Phase 2 of the resonance pivot.
# The new Thread model lands in Phase 4 with its own test coverage.
# =============================================================================


# =============================================================================
# Facet Model Tests
# =============================================================================


class FacetModelTest(TestCase):
    """Tests for hierarchical Facet model."""

    def test_create_top_level_facet(self):
        """Test creating a category-level facet."""
        creatures = Facet.objects.create(
            name="Creatures",
            description="Animals and mythical beasts",
        )
        self.assertIsNone(creatures.parent)
        self.assertEqual(creatures.depth, 0)

    def test_create_nested_facet(self):
        """Test creating nested facets with hierarchy."""
        creatures = Facet.objects.create(name="Creatures")
        mammals = Facet.objects.create(name="Mammals", parent=creatures)
        wolf = Facet.objects.create(name="Wolf", parent=mammals)

        self.assertEqual(mammals.parent, creatures)
        self.assertEqual(wolf.parent, mammals)
        self.assertEqual(mammals.depth, 1)
        self.assertEqual(wolf.depth, 2)

    def test_facet_full_path(self):
        """Test full_path property returns hierarchy."""
        creatures = Facet.objects.create(name="Creatures")
        mammals = Facet.objects.create(name="Mammals", parent=creatures)
        wolf = Facet.objects.create(name="Wolf", parent=mammals)

        self.assertEqual(wolf.full_path, "Creatures > Mammals > Wolf")
        self.assertEqual(mammals.full_path, "Creatures > Mammals")
        self.assertEqual(creatures.full_path, "Creatures")

    def test_facet_is_category(self):
        """Test is_category property."""
        creatures = Facet.objects.create(name="Creatures")
        wolf = Facet.objects.create(name="Wolf", parent=creatures)

        self.assertTrue(creatures.is_category)
        self.assertFalse(wolf.is_category)

    def test_unique_name_within_parent(self):
        """Test that names must be unique within same parent."""
        creatures = Facet.objects.create(name="Creatures")
        Facet.objects.create(name="Wolf", parent=creatures)

        with self.assertRaises(IntegrityError):
            Facet.objects.create(name="Wolf", parent=creatures)

    def test_same_name_different_parent_allowed(self):
        """Test that same name under different parents is allowed."""
        creatures = Facet.objects.create(name="Creatures")
        symbols = Facet.objects.create(name="Symbols")

        # Both can have a "Wolf" child
        Facet.objects.create(name="Wolf", parent=creatures)
        Facet.objects.create(name="Wolf", parent=symbols)  # Should not raise


# =============================================================================
# CharacterFacet Model Tests
# =============================================================================


class CharacterFacetModelTest(TestCase):
    """Tests for CharacterFacet linking facets to resonances."""

    @classmethod
    def setUpTestData(cls):
        from world.magic.factories import ResonanceFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.creatures = Facet.objects.create(name="Creatures")
        cls.spider = Facet.objects.create(name="Spider", parent=cls.creatures)

    def test_create_character_facet(self):
        """Test linking a facet to a character's resonance."""
        char_facet = CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
            flavor_text="Patient predator, weaving traps",
        )

        self.assertEqual(char_facet.character, self.sheet)
        self.assertEqual(char_facet.facet, self.spider)
        self.assertEqual(char_facet.resonance, self.resonance)
        self.assertEqual(char_facet.flavor_text, "Patient predator, weaving traps")

    def test_unique_facet_per_character(self):
        """Test that a character can only have each facet once."""
        CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
        )

        with self.assertRaises(IntegrityError):
            CharacterFacet.objects.create(
                character=self.sheet,
                facet=self.spider,
                resonance=self.resonance,
            )

    def test_same_facet_different_characters(self):
        """Test that different characters can have the same facet."""
        other_sheet = CharacterSheetFactory()

        CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
        )
        # Should not raise - different character
        CharacterFacet.objects.create(
            character=other_sheet,
            facet=self.spider,
            resonance=self.resonance,
        )

    def test_flavor_text_optional(self):
        """Test that flavor_text is optional."""
        char_facet = CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
        )
        self.assertEqual(char_facet.flavor_text, "")


# =============================================================================
# Reincarnation Model Tests
# =============================================================================


class ReincarnationModelTest(TestCase):
    """Test Reincarnation model."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()

    def test_create_reincarnation(self):
        """Can create a Reincarnation linking sheet to gift."""
        reincarnation = Reincarnation.objects.create(
            character=self.sheet,
            gift=self.gift,
        )
        self.assertEqual(reincarnation.character, self.sheet)
        self.assertEqual(reincarnation.gift, self.gift)
        self.assertEqual(reincarnation.past_life_name, "")
        self.assertEqual(reincarnation.past_life_notes, "")

    def test_reincarnation_str(self):
        """String representation is descriptive."""
        reincarnation = Reincarnation.objects.create(
            character=self.sheet,
            gift=self.gift,
            past_life_name="Archmage Valdris",
        )
        self.assertIn("Valdris", str(reincarnation))


# =============================================================================
# Cantrip Model Tests
# =============================================================================


class CantripModelTest(TestCase):
    """Tests for the Cantrip model."""

    def test_cantrip_str(self):
        """Test string representation."""
        cantrip = Cantrip.objects.create(
            name="Empowered Strike",
            description="Channel magic into your weapon.",
            archetype="attack",
            requires_facet=False,
            effect_type=EffectTypeFactory(),
            style=TechniqueStyleFactory(),
        )
        assert str(cantrip) == "Empowered Strike"

    def test_cantrip_with_facets(self):
        """Test cantrip with allowed facets via M2M relationship."""
        cantrip = Cantrip.objects.create(
            name="Elemental Strike",
            description="Imbue your weapon with elemental power.",
            archetype="attack",
            requires_facet=True,
            facet_prompt="Choose your element",
            effect_type=EffectTypeFactory(),
            style=TechniqueStyleFactory(),
        )
        fire = FacetFactory(name="Fire")
        ice = FacetFactory(name="Ice")
        cantrip.allowed_facets.add(fire, ice)
        assert cantrip.allowed_facets.count() == 2

    def test_innate_cantrip_no_facet_prompt(self):
        """Test that innate cantrips default to empty facet_prompt."""
        cantrip = Cantrip.objects.create(
            name="Danger Sense",
            description="Supernatural awareness of threats.",
            archetype="utility",
            requires_facet=False,
            effect_type=EffectTypeFactory(),
            style=TechniqueStyleFactory(),
        )
        assert cantrip.facet_prompt == ""

    def test_cantrip_has_mechanical_fields(self) -> None:
        """Cantrip stores enough mechanical info to produce a Technique."""
        effect_type = EffectTypeFactory(name="Attack")
        style = TechniqueStyleFactory(name="Manifestation")
        cantrip = Cantrip.objects.create(
            name="Flame Blade",
            description="Wreathe your weapon in flames.",
            archetype=CantripArchetype.ATTACK,
            effect_type=effect_type,
            style=style,
            base_intensity=1,
            base_control=1,
            base_anima_cost=5,
        )
        assert cantrip.effect_type == effect_type
        assert cantrip.style == style
        assert cantrip.base_intensity == 1
        assert cantrip.base_control == 1
        assert cantrip.base_anima_cost == 5

    def test_cantrip_mechanical_defaults(self) -> None:
        """Cantrip mechanical fields default to basic values."""
        cantrip = Cantrip.objects.create(
            name="Basic Cantrip",
            description="A basic ability.",
            archetype=CantripArchetype.UTILITY,
            effect_type=EffectTypeFactory(),
            style=TechniqueStyleFactory(),
        )
        assert cantrip.base_intensity == 1
        assert cantrip.base_control == 1
        assert cantrip.base_anima_cost == 5


# =============================================================================
# Technique Intensity/Control Tests
# =============================================================================


class TechniqueIntensityControlTest(TestCase):
    """Test intensity and control fields on Technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()

    def test_technique_has_intensity_and_control(self) -> None:
        """Technique stores base intensity and control stats."""
        technique = Technique.objects.create(
            name="Flame Blade",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            level=1,
            intensity=1,
            control=1,
            anima_cost=5,
        )
        assert technique.intensity == 1
        assert technique.control == 1

    def test_technique_intensity_control_defaults(self) -> None:
        """Intensity and control default to 1."""
        technique = Technique.objects.create(
            name="Default Spell",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            level=1,
            anima_cost=5,
        )
        assert technique.intensity == 1
        assert technique.control == 1

    def test_higher_tier_technique_intensity_exceeds_control(self) -> None:
        """Higher-tier techniques can have intensity > control (inherently volatile)."""
        technique = Technique.objects.create(
            name="Greater Flame",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            level=6,
            intensity=10,
            control=8,
            anima_cost=15,
        )
        assert technique.intensity == 10
        assert technique.control == 8
        assert technique.tier == 2


class MishapPoolTierCleanTests(TestCase):
    """Test MishapPoolTier overlap validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.pool1 = ConsequencePoolFactory()
        cls.pool2 = ConsequencePoolFactory()

    def test_non_overlapping_tiers_valid(self) -> None:
        """Adjacent, non-overlapping tiers pass validation."""
        MishapPoolTierFactory(min_deficit=1, max_deficit=5, consequence_pool=self.pool1)
        tier2 = MishapPoolTier(min_deficit=6, max_deficit=None, consequence_pool=self.pool2)
        tier2.clean()  # should not raise

    def test_overlapping_tiers_raise(self) -> None:
        """Overlapping deficit ranges are rejected by clean()."""
        MishapPoolTierFactory(min_deficit=1, max_deficit=10, consequence_pool=self.pool1)
        tier2 = MishapPoolTier(min_deficit=5, max_deficit=15, consequence_pool=self.pool2)
        with self.assertRaises(ValidationError):
            tier2.clean()

    def test_unbounded_tiers_overlap(self) -> None:
        """Two unbounded (max_deficit=None) tiers overlap."""
        MishapPoolTierFactory(min_deficit=1, max_deficit=None, consequence_pool=self.pool1)
        tier2 = MishapPoolTier(min_deficit=5, max_deficit=None, consequence_pool=self.pool2)
        with self.assertRaises(ValidationError):
            tier2.clean()
