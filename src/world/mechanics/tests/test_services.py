"""Tests for mechanics service functions."""

from django.test import TestCase, tag

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierSourceFactory,
    ModifierTargetFactory,
    ObjectPropertyFactory,
    PropertyDamageModifierFactory,
    PropertyFactory,
)
from world.mechanics.models import CharacterModifier, ObjectProperty
from world.mechanics.services import (
    covenant_role_bonus,
    create_distinction_modifiers,
    delete_distinction_modifiers,
    get_modifier_breakdown,
    get_modifier_total,
    passive_facet_bonuses,
    property_damage_bonus,
    stage_property,
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
            character=self.character,
            distinction=distinction,
            rank=2,
        )
        create_distinction_modifiers(char_distinction)

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 10  # 5 * rank 2
        assert len(breakdown.sources) == 1
        assert breakdown.sources[0].source_name == "Attractive"
        assert breakdown.sources[0].base_value == 10

    def test_null_effect_source_is_ignored(self):
        """A modifier whose source has a null distinction_effect is skipped, not crashed on.

        ModifierSource.distinction_effect is nullable (SET_NULL when the effect template
        is deleted, or a future non-distinction source type). Such an orphaned modifier
        has lost its amplifier/immunity/label semantics, so the breakdown must ignore it
        rather than dereference None (issue #909).
        """
        # A valid distinction modifier worth +5.
        distinction = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.allure,
            value_per_rank=5,
        )
        char_distinction = CharacterDistinctionFactory(
            character=self.character,
            distinction=distinction,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # An orphaned modifier on the same target whose source has no distinction_effect.
        CharacterModifierFactory(
            character=self.character,
            target=self.allure,
            value=7,
            source=ModifierSourceFactory(),
        )

        breakdown = get_modifier_breakdown(self.character, self.allure)

        # Orphan contributes nothing and is not listed; only the valid +5 remains.
        assert breakdown.total == 5
        assert len(breakdown.sources) == 1
        assert breakdown.sources[0].source_name == "Attractive"
        assert breakdown.has_immunity is False
        assert breakdown.negatives_blocked == 0

    def test_only_null_effect_source_returns_empty(self):
        """When every modifier row is orphaned, the breakdown is empty (no crash)."""
        CharacterModifierFactory(
            character=self.character,
            target=self.allure,
            value=9,
            source=ModifierSourceFactory(),
        )

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 0
        assert breakdown.sources == []
        assert breakdown.has_immunity is False
        assert breakdown.negatives_blocked == 0

    def test_recognized_non_distinction_source_is_counted_as_a_flat_addend(self):
        """A marker source (achievement_reward / residence_comfort) contributes its flat value.

        Unlike a bare/orphaned source (UNKNOWN → ignored, #909), a *recognized* non-distinction
        source is summed — outside the amplification graph but read by get_modifier_total.
        """
        CharacterModifierFactory(
            character=self.character,
            target=self.allure,
            value=5,
            source=ModifierSourceFactory(achievement_reward=True),
        )

        breakdown = get_modifier_breakdown(self.character, self.allure)

        assert breakdown.total == 5
        assert len(breakdown.sources) == 1
        assert breakdown.sources[0].source_name == "Achievement reward"
        assert breakdown.sources[0].is_amplifier is False

    def test_multiple_modifiers_sum(self):
        """Multiple modifiers are summed together."""
        # First distinction
        d1 = DistinctionFactory(name="Attractive")
        DistinctionEffectFactory(distinction=d1, target=self.allure, value_per_rank=5)
        cd1 = CharacterDistinctionFactory(character=self.character, distinction=d1, rank=1)
        create_distinction_modifiers(cd1)

        # Second distinction
        d2 = DistinctionFactory(name="Charming")
        DistinctionEffectFactory(distinction=d2, target=self.allure, value_per_rank=3)
        cd2 = CharacterDistinctionFactory(character=self.character, distinction=d2, rank=1)
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
            character=self.character,
            distinction=attractive,
            rank=1,
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character,
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
        cd_base = CharacterDistinctionFactory(character=self.character, distinction=base, rank=1)
        cd_amp1 = CharacterDistinctionFactory(character=self.character, distinction=amp1, rank=1)
        cd_amp2 = CharacterDistinctionFactory(character=self.character, distinction=amp2, rank=1)
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
            character=self.character,
            distinction=spotless,
            rank=1,
        )
        cd_cursed = CharacterDistinctionFactory(
            character=self.character,
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
            character=self.character, distinction=attractive, rank=1
        )
        cd_cleans = CharacterDistinctionFactory(
            character=self.character, distinction=cleans_up, rank=1
        )
        cd_spotless = CharacterDistinctionFactory(
            character=self.character, distinction=spotless, rank=1
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
            character=self.character,
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
            character=self.character,
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
            character=self.character,
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


@tag("postgres")
class PassiveFacetBonusesTests(TestCase):
    """Tests for passive_facet_bonuses (Spec D §5.2).

    PG-only: the equipment-walk path traverses
    ``sheet.character.threads`` and ``sheet.character.equipped_items``
    cached handlers, plus the per-instance ``cached_item_facets`` list on
    each ``ItemInstance``. On the SQLite tier, PKs reset between tests but
    the SharedMemoryModel idmap keeps stale handler / cached_item_facets
    state across the rollback boundary — ``item_facets_for(facet)`` then
    matches against stale ``facet_id`` values and returns the wrong (or
    empty) set. PG sequences don't reset across tests, so the pk
    collision can't fire; the parity tier covers this.
    """

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
        """Active but non-engaged role + equipped item → 0.

        After Phase 8 refactor, an un-engaged membership causes early exit
        before the equipment walk, so the result is 0 regardless of placeholder
        bonus values.
        """
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

        # Not engaged (factory default engaged=False)
        CharacterCovenantRoleFactory(character_sheet=sheet)
        sheet.character.covenant_roles.invalidate()

        template = ItemTemplateFactory(gear_archetype=GearArchetype.HEAVY_ARMOR)
        item = ItemInstanceFactory(template=template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        result = covenant_role_bonus(sheet, target)
        assert result == 0

    def test_compatible_gear_adds_role_bonus(self) -> None:
        """Patched helpers (role=10, gear=3). One compatible item → role_bonus = 10."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.covenants.services import set_engaged_membership
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
        set_engaged_membership(membership=assignment)
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

        assert result == 10  # role_bonus only (combat already counts gear stat)

    def test_incompatible_gear_marginal(self) -> None:
        """Patched helpers (role=10, gear=3). No compat row → max(0, 10-3) = 7."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.covenants.services import set_engaged_membership
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="IncompatChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="IncompatTarget")

        assignment = CharacterCovenantRoleFactory(character_sheet=sheet)
        set_engaged_membership(membership=assignment)
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

        assert result == 7  # max(0, 10-3) marginal surplus

    def test_incompatible_gear_suppressed_when_gear_exceeds_role(self) -> None:
        """Patched helpers (role=2, gear=15). No compat row → max(0, 2-15) = 0."""
        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.covenants.services import set_engaged_membership
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )

        char = CharacterFactory(db_key="GearDomChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = ModifierTargetFactory(name="GearDomTarget")

        assignment = CharacterCovenantRoleFactory(character_sheet=sheet)
        set_engaged_membership(membership=assignment)
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

        assert result == 0  # max(0, 2-15) = 0, gear fully suppresses role

    @tag("postgres")
    def test_two_items_aggregate(self) -> None:
        """Patched helpers (role=5, gear=2). One compatible, one not → 5 + max(0,5-2) = 8.

        Compatible slot contributes role_bonus=5. Incompatible slot contributes
        max(0, 5-2)=3. Total = 8.

        PG-only: same equipment-walk SharedMemoryModel idmap pollution path
        as ``PassiveFacetBonusesTests`` (see that class's docstring). The
        single-item variants above stay on both tiers; this is the only
        method that walks two items at once.
        """

        from unittest.mock import patch

        from evennia_extensions.factories import CharacterFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.covenants.services import set_engaged_membership
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
        set_engaged_membership(membership=assignment)
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

        assert result == 8  # 5 + max(0, 5-2) = 5 + 3


class GetModifierTotalEquipmentWalkTests(TestCase):
    """Tests for get_modifier_total equipment walk extension (Spec D §5.5)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.mechanics.factories import ModifierCategoryFactory

        cls.character = CharacterSheetFactory()
        # Equipment-relevant category. Deliberately not "resonance" — #1834 Task 5 made
        # distinction effects targeting a resonance-category ModifierTarget skip
        # CharacterModifier creation entirely, which would zero out the eager total this
        # test exercises. "stat" is equally equipment-relevant and unaffected by that skip.
        cls.eq_category = ModifierCategoryFactory(name="stat")
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
        mock_crb.assert_called_once_with(self.character, self.eq_target, level_override=None)

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
        cd = CharacterDistinctionFactory(character=self.character, distinction=distinction, rank=1)
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
        from world.character_sheets.factories import CharacterSheetFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        # Mirror the trait test fixture: raw ObjectDB, no Character typeclass.
        cls.character = ObjectDBFactory(db_key="RawChar")
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


class ItemMundaneStatForTargetTests(TestCase):
    """Tests for item_mundane_stat_for_target — reads effective_* from ItemInstance (#985)."""

    def test_weapon_damage_target_returns_effective_weapon_damage(self) -> None:
        from world.combat.factories import wire_weapon_damage_modifier_target
        from world.items.constants import GearArchetype
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.mechanics.services import item_mundane_stat_for_target

        target = wire_weapon_damage_modifier_target()
        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.MELEE_ONE_HAND, base_weapon_damage=7
        )
        item = ItemInstanceFactory(template=template)
        self.assertEqual(item_mundane_stat_for_target(item, target), item.effective_weapon_damage)
        self.assertGreater(item_mundane_stat_for_target(item, target), 0)

    def test_armor_soak_target_returns_effective_armor_soak(self) -> None:
        from world.combat.factories import wire_armor_soak_modifier_target
        from world.items.constants import GearArchetype
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.mechanics.services import item_mundane_stat_for_target

        target = wire_armor_soak_modifier_target()
        template = ItemTemplateFactory(gear_archetype=GearArchetype.LIGHT_ARMOR, base_armor_soak=5)
        item = ItemInstanceFactory(template=template)
        self.assertEqual(item_mundane_stat_for_target(item, target), item.effective_armor_soak)
        self.assertGreater(item_mundane_stat_for_target(item, target), 0)

    def test_unrelated_target_returns_zero(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.mechanics.services import item_mundane_stat_for_target

        target = ModifierTargetFactory(name="SomethingElse")
        item = ItemInstanceFactory()
        self.assertEqual(item_mundane_stat_for_target(item, target), 0)


class PropertyDamageBonusTest(TestCase):
    def test_returns_zero_with_no_matching_property(self) -> None:
        character = CharacterFactory()
        fire = DamageTypeFactory(name="Fire-stest")
        self.assertEqual(property_damage_bonus(character, fire), 0)

    def test_specific_damage_type_modifier_applies(self) -> None:
        character = CharacterFactory()
        flammable = PropertyFactory(name="flammable-stest")
        fire = DamageTypeFactory(name="Fire-stest-2")
        ObjectPropertyFactory(object=character, property=flammable)
        PropertyDamageModifierFactory(property=flammable, damage_type=fire, modifier_value=10)

        self.assertEqual(property_damage_bonus(character, fire), 10)

    def test_null_damage_type_modifier_applies_to_any_type(self) -> None:
        character = CharacterFactory()
        cursed = PropertyFactory(name="cursed-stest")
        fire = DamageTypeFactory(name="Fire-stest-3")
        ObjectPropertyFactory(object=character, property=cursed)
        PropertyDamageModifierFactory(property=cursed, damage_type=None, modifier_value=5)

        self.assertEqual(property_damage_bonus(character, fire), 5)

    def test_multiple_modifiers_stack(self) -> None:
        character = CharacterFactory()
        flammable = PropertyFactory(name="flammable-stest-2")
        cursed = PropertyFactory(name="cursed-stest-2")
        fire = DamageTypeFactory(name="Fire-stest-4")
        ObjectPropertyFactory(object=character, property=flammable)
        ObjectPropertyFactory(object=character, property=cursed)
        PropertyDamageModifierFactory(property=flammable, damage_type=fire, modifier_value=10)
        PropertyDamageModifierFactory(property=cursed, damage_type=None, modifier_value=5)

        self.assertEqual(property_damage_bonus(character, fire), 15)

    def test_none_damage_type_argument_only_matches_null_rows(self) -> None:
        character = CharacterFactory()
        cursed = PropertyFactory(name="cursed-stest-3")
        fire = DamageTypeFactory(name="Fire-stest-5")
        ObjectPropertyFactory(object=character, property=cursed)
        PropertyDamageModifierFactory(property=cursed, damage_type=fire, modifier_value=10)

        self.assertEqual(property_damage_bonus(character, None), 0)


class StagePropertyTests(TestCase):
    """``stage_property`` -- the GM improv attach/refresh service function (#2503)."""

    def test_creates_new_object_property(self) -> None:
        target = ObjectDBFactory(db_key="StagePropertyTarget")
        locked = PropertyFactory(name="locked-stage-test")

        obj_prop = stage_property(target, locked)

        self.assertEqual(obj_prop.object, target)
        self.assertEqual(obj_prop.property, locked)
        self.assertEqual(obj_prop.value, 1)

    def test_reapplying_upserts_instead_of_duplicating(self) -> None:
        target = ObjectDBFactory(db_key="StagePropertyTarget2")
        locked = PropertyFactory(name="locked-stage-test-2")

        stage_property(target, locked, value=2)
        stage_property(target, locked, value=5)

        rows = ObjectProperty.objects.filter(object=target, property=locked)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().value, 5)
