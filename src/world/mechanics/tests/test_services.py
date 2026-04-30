"""Tests for mechanics service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import (
    covenant_role_bonus,
    create_distinction_modifiers,
    delete_distinction_modifiers,
    get_modifier_breakdown,
    get_modifier_total,
    passive_facet_bonuses,
    update_distinction_rank,
)


class TestGetModifierBreakdown(TestCase):
    """Tests for get_modifier_breakdown function."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_no_modifiers_returns_empty_breakdown(self):
        """Character with no modifiers returns zero total."""
        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 0
        assert breakdown.sources == []
        assert breakdown.has_immunity is False
        assert breakdown.negatives_blocked == 0

    def test_single_modifier_simple_sum(self):
        """Single modifier returns its value as total."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.allure,
            value_per_rank=5,
        )
        char_distinction = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=2,
        )
        create_distinction_modifiers(char_distinction)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 10  # 5 * rank 2
        assert len(breakdown.sources) == 1
        assert breakdown.sources[0].source_name == "Attractive"
        assert breakdown.sources[0].base_value == 10

    def test_multiple_modifiers_sum(self):
        """Multiple modifiers are summed together."""
        # First distinction
        d1 = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=d1, target=self.allure, value_per_rank=5)
        cd1 = CharacterDistinctionFactory(
            character=self.character.character, distinction=d1, rank=1
        )
        create_distinction_modifiers(cd1)

        # Second distinction
        d2 = DistinctionFactory(name="Charming")
        DistinctionEffectFactory(distinction=d2, target=self.allure, value_per_rank=3)
        cd2 = CharacterDistinctionFactory(
            character=self.character.character, distinction=d2, rank=1
        )
        create_distinction_modifiers(cd2)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 8  # 5 + 3

    def test_amplification_applies_to_other_sources(self):
        """Amplifier adds bonus to other sources, not itself."""
        # Create Attractive with +10 Allure
        attractive = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=attractive,
            target=self.allure,
            value_per_rank=10,
        )

        # Create Cleans Up Well with +5 Allure and +2 amplification
        cleans_up = DistinctionFactory(name="Cleans Up Well")
        DistinctionEffectFactory(
            distinction=cleans_up,
            target=self.allure,
            value_per_rank=5,
            amplifies_sources_by=2,
        )

        # Grant both distinctions
        cd_attractive = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=attractive,
            rank=1,
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=cleans_up,
            rank=1,
        )
        create_distinction_modifiers(cd_attractive)
        create_distinction_modifiers(cd_cleans)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Attractive: 10 + 2 (amplified) = 12
        # Cleans Up Well: 5 (no self-amplify)
        # Total: 17
        assert breakdown.total == 17

        # Check individual sources
        attractive_source = next(s for s in breakdown.sources if s.source_name == "Attractive")
        assert attractive_source.base_value == 10
        assert attractive_source.amplification == 2
        assert attractive_source.final_value == 12
        assert attractive_source.is_amplifier is False

        cleans_source = next(s for s in breakdown.sources if s.source_name == "Cleans Up Well")
        assert cleans_source.base_value == 5
        assert cleans_source.amplification == 0
        assert cleans_source.final_value == 5
        assert cleans_source.is_amplifier is True

    def test_multiple_amplifiers_stack(self):
        """Multiple amplifiers each add their bonus to other sources."""
        # Base distinction
        base = DistinctionFactory(name="Base")
        DistinctionEffectFactory(distinction=base, target=self.allure, value_per_rank=10)

        # Two amplifiers
        amp1 = DistinctionFactory(name="Amplifier1")
        DistinctionEffectFactory(
            distinction=amp1, target=self.allure, value_per_rank=5, amplifies_sources_by=2
        )

        amp2 = DistinctionFactory(name="Amplifier2")
        DistinctionEffectFactory(
            distinction=amp2, target=self.allure, value_per_rank=3, amplifies_sources_by=1
        )

        # Grant all
        cd_base = CharacterDistinctionFactory(
            character=self.character.character, distinction=base, rank=1
        )
        cd_amp1 = CharacterDistinctionFactory(
            character=self.character.character, distinction=amp1, rank=1
        )
        cd_amp2 = CharacterDistinctionFactory(
            character=self.character.character, distinction=amp2, rank=1
        )
        create_distinction_modifiers(cd_base)
        create_distinction_modifiers(cd_amp1)
        create_distinction_modifiers(cd_amp2)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Base: 10 + 2 + 1 = 13
        # Amp1: 5 + 1 = 6 (gets +1 from amp2)
        # Amp2: 3 + 2 = 5 (gets +2 from amp1)
        # Total: 13 + 6 + 5 = 24
        assert breakdown.total == 24

    def test_immunity_blocks_negative_modifiers(self):
        """Immunity prevents negative modifiers from counting."""
        # Create distinction with immunity
        spotless = DistinctionFactory(name="Somehow Always Spotless")
        DistinctionEffectFactory(
            distinction=spotless,
            target=self.allure,
            value_per_rank=5,
            grants_immunity_to_negative=True,
        )

        # Create a "debuff" distinction with negative value
        cursed = DistinctionFactory(name="Cursed Appearance")
        DistinctionEffectFactory(
            distinction=cursed,
            target=self.allure,
            value_per_rank=-3,
        )

        # Grant both
        cd_spotless = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=spotless,
            rank=1,
        )
        cd_cursed = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=cursed,
            rank=1,
        )
        create_distinction_modifiers(cd_spotless)
        create_distinction_modifiers(cd_cursed)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Spotless: 5
        # Cursed: -3 -> BLOCKED
        # Total: 5
        assert breakdown.total == 5
        assert breakdown.has_immunity is True
        assert breakdown.negatives_blocked == 1

        cursed_source = next(s for s in breakdown.sources if s.source_name == "Cursed Appearance")
        assert cursed_source.blocked_by_immunity is True

    def test_amplification_and_immunity_together(self):
        """Amplification and immunity work together correctly."""
        # Attractive: +10 Allure
        attractive = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=attractive, target=self.allure, value_per_rank=10)

        # Cleans Up Well: +5 Allure, +2 amplification
        cleans_up = DistinctionFactory(name="Cleans Up Well")
        DistinctionEffectFactory(
            distinction=cleans_up,
            target=self.allure,
            value_per_rank=5,
            amplifies_sources_by=2,
        )

        # Somehow Always Spotless: +5 Allure, immunity
        spotless = DistinctionFactory(name="Somehow Always Spotless")
        DistinctionEffectFactory(
            distinction=spotless,
            target=self.allure,
            value_per_rank=5,
            grants_immunity_to_negative=True,
        )

        # Grant all three
        cd_attractive = CharacterDistinctionFactory(
            character=self.character.character, distinction=attractive, rank=1
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character.character, distinction=cleans_up, rank=1
        )
        cd_spotless = CharacterDistinctionFactory(
            character=self.character.character, distinction=spotless, rank=1
        )
        create_distinction_modifiers(cd_attractive)
        create_distinction_modifiers(cd_cleans)
        create_distinction_modifiers(cd_spotless)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Attractive: 10 + 2 = 12
        # Cleans Up Well: 5 (no self-amplify)
        # Somehow Always Spotless: 5 + 2 = 7
        # Total: 12 + 5 + 7 = 24
        assert breakdown.total == 24
        assert breakdown.has_immunity is True


class TestGetModifierTotal(TestCase):
    """Tests for get_modifier_total convenience function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_returns_total_from_breakdown(self):
        """get_modifier_total returns just the total value."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.allure,
            value_per_rank=5,
        )
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=2,
        )
        create_distinction_modifiers(cd)

        total = get_modifier_total(self.character, self.allure)
        assert total == 10


class TestDeleteDistinctionModifiers(TestCase):
    """Tests for delete_distinction_modifiers function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_deletes_all_modifiers_for_distinction(self):
        """Removes all CharacterModifier and ModifierSource records."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=distinction, target=self.allure, value_per_rank=5)
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=1,
        )
        create_distinction_modifiers(cd)

        # Verify modifiers exist
        assert CharacterModifier.objects.filter(character=self.character).count() == 1

        # Delete
        count = delete_distinction_modifiers(cd)

        assert count == 1
        assert CharacterModifier.objects.filter(character=self.character).count() == 0


class TestUpdateDistinctionRank(TestCase):
    """Tests for update_distinction_rank function."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory()
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_updates_modifier_values_for_new_rank(self):
        """Recalculates modifier values when rank changes."""
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=distinction, target=self.allure, value_per_rank=5)
        cd = CharacterDistinctionFactory(
            character=self.character.character,
            distinction=distinction,
            rank=1,
        )
        create_distinction_modifiers(cd)

        # Initial value
        assert get_modifier_total(self.character, self.allure) == 5

        # Update rank
        cd.rank = 3
        cd.save()
        update_distinction_rank(cd)

        # New value
        assert get_modifier_total(self.character, self.allure) == 15


class PassiveFacetBonusesTests(TestCase):
    """Tests for passive_facet_bonuses (Spec D §5.2)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            FacetFactory,
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )

        # Character with both a Character typeclass and a CharacterSheet
        cls.character_obj = CharacterFactory(db_key="FacetBonusChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # Resonance with a linked ModifierTarget (OneToOne target_resonance)
        cls.resonance = ResonanceFactory()
        cls.target = ModifierTargetFactory(name="FacetTarget", target_resonance=cls.resonance)

        # Facet used as thread anchor and item facet
        cls.facet = FacetFactory(name="TestFacet")

        # Quality tiers: item quality stat_multiplier=2.0, attach quality stat_multiplier=3.0
        cls.item_quality = QualityTierFactory(name="ItemQuality", stat_multiplier=2.0)
        cls.attach_quality = QualityTierFactory(name="AttachQuality", stat_multiplier=3.0)

        # One ItemInstance equipped on the character, with the facet attached
        cls.item_template = ItemTemplateFactory(facet_capacity=1)
        cls.item_instance = ItemInstanceFactory(
            template=cls.item_template,
            quality_tier=cls.item_quality,
        )
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.item_instance,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )
        EquippedItemFactory(character=cls.character_obj, item_instance=cls.item_instance)

        # FACET thread anchored to cls.facet, resonance=cls.resonance, level=2
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            target_trait=None,
            level=2,
        )

        # Tier-0 FLAT_BONUS ThreadPullEffect for this resonance
        cls.effect = ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

    def test_no_items_worn_returns_zero(self) -> None:
        """Sheet with FACET thread but no matching worn items → 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.magic.constants import TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory, ThreadFactory

        # Separate character with no equipped items
        bare_char = CharacterFactory(db_key="BareChar")
        bare_sheet = CharacterSheetFactory(character=bare_char, primary_persona=False)
        bare_res = ResonanceFactory()
        bare_facet = FacetFactory(name="BareTestFacet")
        # ModifierTarget linked to bare_res so gating passes; items check will fail
        bare_target = ModifierTargetFactory(name="BareTarget", target_resonance=bare_res)
        ThreadFactory(
            owner=bare_sheet,
            resonance=bare_res,
            target_kind=TargetKind.FACET,
            target_facet=bare_facet,
            target_trait=None,
            level=2,
        )
        result = passive_facet_bonuses(bare_sheet, bare_target)
        assert result == 0

    def test_tier_0_flat_bonus_sums_contributions(self) -> None:
        """Contribution = flat_bonus × item_quality × attach_quality × max(1, level).

        Setup: flat=5, item_quality.stat_multiplier=2, attach_quality.stat_multiplier=3, level=2.
        Expected: 5 × 2 × 3 × 2 = 60.
        """
        result = passive_facet_bonuses(self.sheet, self.target)
        assert result == 60

    def test_target_without_resonance_link_returns_zero(self) -> None:
        """ModifierTarget with no target_resonance → gating blocks all effects → 0."""
        unlinked_target = ModifierTargetFactory(name="UnlinkedTarget", target_resonance=None)
        result = passive_facet_bonuses(self.sheet, unlinked_target)
        assert result == 0

    def test_two_items_aggregate_correctly(self) -> None:
        """Two equipped items each contribute independently; no division.

        Each item: 5 × 2 × 3 × 2 = 60. Two items → 120.
        """
        # Fresh character — equipped_items cached_property is unpopulated,
        # no invalidate needed.
        from evennia_extensions.factories import CharacterFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            QualityTierFactory,
        )
        from world.magic.constants import TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory, ThreadFactory

        # Fresh character so equipped_items cache is isolated
        two_item_char = CharacterFactory(db_key="TwoItemChar")
        two_item_sheet = CharacterSheetFactory(character=two_item_char, primary_persona=False)
        two_res = ResonanceFactory()
        two_facet = FacetFactory(name="TwoItemFacet")
        two_target = ModifierTargetFactory(name="TwoItemTarget", target_resonance=two_res)

        q_item = QualityTierFactory(name="TwoItemQuality", stat_multiplier=2.0)
        q_attach = QualityTierFactory(name="TwoAttachQuality", stat_multiplier=3.0)

        # Two instances, same facet, both equipped
        template = self.item_template
        inst_a = ItemInstanceFactory(template=template, quality_tier=q_item)
        inst_b = ItemInstanceFactory(template=template, quality_tier=q_item)
        ItemFacetFactory(item_instance=inst_a, facet=two_facet, attachment_quality_tier=q_attach)
        ItemFacetFactory(item_instance=inst_b, facet=two_facet, attachment_quality_tier=q_attach)
        from world.items.constants import BodyRegion, EquipmentLayer

        EquippedItemFactory(
            character=two_item_char,
            item_instance=inst_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItemFactory(
            character=two_item_char,
            item_instance=inst_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

        ThreadFactory(
            owner=two_item_sheet,
            resonance=two_res,
            target_kind=TargetKind.FACET,
            target_facet=two_facet,
            target_trait=None,
            level=2,
        )

        # Reuse the tier-0 FLAT_BONUS effect already in the DB for two_res
        from world.magic.constants import EffectKind
        from world.magic.factories import ThreadPullEffectFactory

        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=two_res,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        result = passive_facet_bonuses(two_item_sheet, two_target)
        assert result == 120  # (5 × 2 × 3 × 2) × 2 items


class CovenantRoleBonusTests(TestCase):
    """Tests for covenant_role_bonus (Spec D §5.6)."""

    def test_no_role_returns_zero(self) -> None:
        """Sheet with no active CharacterCovenantRole → returns 0."""
        from evennia_extensions.factories import CharacterFactory

        char = CharacterFactory(db_key="NoRoleChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="NoRoleTarget")

        result = covenant_role_bonus(sheet, target)
        assert result == 0

    def test_placeholders_return_zero_by_default(self) -> None:
        """Without patching, sheet with active role + equipped item → 0 (PR1 behavior)."""
        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="PlaceholderChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="PlaceholderTarget")

        CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        template = ItemTemplateFactory(gear_archetype=GearArchetype.HEAVY_ARMOR)
        item = ItemInstanceFactory(template=template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        result = covenant_role_bonus(sheet, target)
        assert result == 0

    def test_compatible_gear_additive(self) -> None:
        """Patched helpers (role=10, gear=3). One compatible item → 10+3 = 13."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="CompatChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="CompatTarget")

        assignment = CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        template = ItemTemplateFactory(gear_archetype=GearArchetype.HEAVY_ARMOR)
        item = ItemInstanceFactory(template=template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        # Create compatibility row so is_gear_compatible returns True
        GearArchetypeCompatibilityFactory(
            covenant_role=assignment.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=10),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=3),
        ):
            result = covenant_role_bonus(sheet, target)

        assert result == 13  # 10 + 3 (additive)

    def test_incompatible_gear_max(self) -> None:
        """Patched helpers (role=10, gear=3). No compat row → max(10, 3) = 10."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="IncompatChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="IncompatTarget")

        CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        template = ItemTemplateFactory(gear_archetype=GearArchetype.MELEE_ONE_HAND)
        item = ItemInstanceFactory(template=template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        # No GearArchetypeCompatibility row → incompatible

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=10),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=3),
        ):
            result = covenant_role_bonus(sheet, target)

        assert result == 10  # max(10, 3)

    def test_incompatible_gear_higher_max_wins(self) -> None:
        """Patched helpers (role=2, gear=15). No compat row → max(2, 15) = 15."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="GearDomChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="GearDomTarget")

        CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        template = ItemTemplateFactory(gear_archetype=GearArchetype.RANGED)
        item = ItemInstanceFactory(template=template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=2),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=15),
        ):
            result = covenant_role_bonus(sheet, target)

        assert result == 15  # max(2, 15)

    def test_two_items_aggregate(self) -> None:
        """Patched helpers (role=5, gear=2). One compatible, one not → (5+2) + max(5,2) = 12."""

        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="TwoItemRoleChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="TwoItemRoleTarget")

        assignment = CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        # Compatible item: HEAVY_ARMOR with compat row
        compat_template = ItemTemplateFactory(gear_archetype=GearArchetype.HEAVY_ARMOR)
        compat_item = ItemInstanceFactory(template=compat_template)
        EquippedItemFactory(
            character=char,
            item_instance=compat_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=assignment.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

        # Incompatible item: RANGED, no compat row
        incompat_template = ItemTemplateFactory(gear_archetype=GearArchetype.RANGED)
        incompat_item = ItemInstanceFactory(template=incompat_template)
        EquippedItemFactory(
            character=char,
            item_instance=incompat_item,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        char.equipped_items.invalidate()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=5),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=2),
        ):
            result = covenant_role_bonus(sheet, target)

        assert result == 12  # (5+2) + max(5,2) = 7 + 5


class GetModifierTotalEquipmentWalkTests(TestCase):
    """Tests for get_modifier_total equipment walk extension (Spec D §5.5)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.mechanics.factories import ModifierCategoryFactory

        cls.character = CharacterSheetFactory()
        # Equipment-relevant category
        cls.eq_category = ModifierCategoryFactory(name="resonance")
        cls.eq_target = ModifierTargetFactory(name="EqWalkTarget", category=cls.eq_category)
        # Non-equipment category (not in EQUIPMENT_RELEVANT_CATEGORIES)
        cls.other_category = ModifierCategoryFactory(name="goal")
        cls.other_target = ModifierTargetFactory(name="NonEqTarget", category=cls.other_category)

    def test_invokes_equipment_walk_for_relevant_categories(self) -> None:
        """Equipment walk fires when target.category.name is in EQUIPMENT_RELEVANT_CATEGORIES.

        With no eager modifiers and stubs returning 5 + 7, total == 12.
        """
        from unittest.mock import patch

        with (
            patch("world.mechanics.services.passive_facet_bonuses", return_value=5) as mock_pfb,
            patch("world.mechanics.services.covenant_role_bonus", return_value=7) as mock_crb,
        ):
            result = get_modifier_total(self.character, self.eq_target)

        assert result == 12
        mock_pfb.assert_called_once_with(self.character, self.eq_target)
        mock_crb.assert_called_once_with(self.character, self.eq_target)

    def test_skips_walk_for_non_equipment_categories(self) -> None:
        """Equipment walk does NOT fire when target.category.name is not in the set."""
        from unittest.mock import patch

        with (
            patch("world.mechanics.services.passive_facet_bonuses", return_value=5) as mock_pfb,
            patch("world.mechanics.services.covenant_role_bonus", return_value=7) as mock_crb,
        ):
            result = get_modifier_total(self.character, self.other_target)

        # No eager modifiers → 0; walk skipped → still 0
        assert result == 0
        mock_pfb.assert_not_called()
        mock_crb.assert_not_called()

    def test_combines_eager_and_equipment_totals(self) -> None:
        """Eager CharacterModifier (10) + patched facet (3) + patched role (4) = 17."""
        from unittest.mock import patch

        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
            DistinctionFactory,
        )
        from world.mechanics.services import create_distinction_modifiers

        distinction = DistinctionFactory(name="EqWalkDistinction")
        DistinctionEffectFactory(distinction=distinction, target=self.eq_target, value_per_rank=10)
        cd = CharacterDistinctionFactory(
            character=self.character.character, distinction=distinction, rank=1
        )
        create_distinction_modifiers(cd)

        with (
            patch("world.mechanics.services.passive_facet_bonuses", return_value=3),
            patch("world.mechanics.services.covenant_role_bonus", return_value=4),
        ):
            result = get_modifier_total(self.character, self.eq_target)

        assert result == 17  # 10 (eager) + 3 (facet) + 4 (role)


class EquipmentWalkRawObjectDBSafetyTests(TestCase):
    """Regression: passive_facet_bonuses + covenant_role_bonus must handle
    raw-ObjectDB sheet.character (typeclass not set up) gracefully.
    Caught by CI no-keepdb regression on Phase 8.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.objects.models import ObjectDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        # Mirror the trait test fixture: raw ObjectDB, no Character typeclass.
        cls.character = ObjectDB.objects.create(db_key="RawChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.target = ModifierTargetFactory(
            category=ModifierCategoryFactory(name="raw_stat"),
            name="example_stat",
        )

    def test_passive_facet_bonuses_returns_zero_for_raw_objectdb(self) -> None:
        from world.mechanics.services import passive_facet_bonuses

        self.assertEqual(passive_facet_bonuses(self.sheet, self.target), 0)

    def test_covenant_role_bonus_returns_zero_for_raw_objectdb(self) -> None:
        from world.mechanics.services import covenant_role_bonus

        self.assertEqual(covenant_role_bonus(self.sheet, self.target), 0)

    def test_get_modifier_total_returns_zero_for_raw_objectdb(self) -> None:
        from world.mechanics.services import get_modifier_total

        self.assertEqual(get_modifier_total(self.sheet, self.target), 0)
