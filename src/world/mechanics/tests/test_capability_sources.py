"""Tests for capability source aggregation service."""

from decimal import Decimal

from django.test import TestCase

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
from world.mechanics.factories import PropertyFactory, TraitCapabilityDerivationFactory
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
        cls.flame_property = PropertyFactory(name="flame")
        cls.resonance.properties.add(cls.flame_property)
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
        # effect_property_ids are derived from resonance M2M to Property
        assert src.effect_property_ids == [self.flame_property.id]

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


class InertOracleAtNonzeroSensitivityTests(TestCase):
    """#2708 C1 review: the availability-oracle sibling of
    ``world.conditions.tests.test_effective_capability_value
    .InertOracleAtNonzeroSensitivityTests``.

    That test covers the agency oracle (``get_effective_capability_value``); this
    covers ``_get_technique_sources`` (via ``get_capability_sources_for_character``),
    the availability oracle. Both oracles previously shared the same bug: with no
    ``CapabilityPowerConfig`` row, each unconditionally computed
    ``technique.intensity + context_free_power + contextual_thread_power(...)`` and fed
    it to the RETIRED additive formula as ``effective_power``, so an ambiently-active
    thread's bump leaked into a value that should have been untouched. The fix makes
    both oracles skip the power derivation entirely when the config is absent
    (``_inert_technique_capability_sources`` here). This test uses the SAME fixture
    shape as the agency-oracle test (nonzero ``intensity_multiplier`` + a real
    ambiently-active GIFT-thread tier-0 ``INTENSITY_BUMP``, no config row) so the pair
    is obviously a pair to the next reader.
    """

    def test_ambient_gift_thread_bump_does_not_move_the_inert_value(self) -> None:
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory(innate_baseline=0)
        gift = GiftFactory()
        technique = TechniqueFactory(gift=gift, intensity=3)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=1, intensity_multiplier=1
        )
        CharacterTechnique.objects.create(character=sheet, technique=technique)

        # A GIFT thread is always in-action (_ALWAYS_IN_ACTION_KINDS), so this bump
        # is visible under the ambient default this oracle always uses (it has no
        # action_ctx param at all — see ADR-0169 D6).
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadFactory, ThreadPullEffectFactory

        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            target_trait=None,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=100,
        )

        sources = get_capability_sources_for_character(sheet.character)
        technique_sources = [s for s in sources if s.source_type == CapabilitySourceType.TECHNIQUE]
        assert len(technique_sources) == 1

        # No CapabilityPowerConfig row: the curve is disabled, and the ambient
        # thread's bump must be invisible to the RETIRED additive formula — the
        # exact pre-#2708 number, computed from technique.intensity alone:
        # base_value(1) + intensity_multiplier(1) * technique.intensity(3) = 4.
        self.assertEqual(technique_sources[0].value, 4)


class TraitSourceTests(TestCase):
    """Tests for _get_trait_sources."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
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
            character=cls.character.sheet_data,
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
        sheet2 = CharacterSheetFactory()
        char2 = sheet2.character
        CharacterTraitValue.objects.create(
            character=sheet2,
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
            character=cls.character.sheet_data,
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


class TechniqueSourceQueryCountTests(TestCase):
    """Query-count regression for the availability oracle's technique-power wiring
    (#2708). Mirrors ``world.conditions.tests.test_technique_capability_values_power``
    for the sibling oracle — both must resolve the technique->gift mapping ONCE for
    the whole sweep, never per technique (the N+1 Task 4's review caught twice)."""

    def _character_with_technique_sweep(self, technique_count: int, *, label: str | None = None):
        from world.magic.constants import TargetKind
        from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
        from world.magic.types.pull import PullActionContext

        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        capability = CapabilityTypeFactory(name=f"avail_sweep_cap_{label or technique_count}")
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            target_trait=None,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )
        for _ in range(technique_count):
            technique = TechniqueFactory(gift=gift, intensity=1)
            TechniqueCapabilityGrantFactory(
                technique=technique,
                capability=capability,
                base_value=1,
                intensity_multiplier=Decimal(0),
            )
            CharacterTechnique.objects.create(character=sheet, technique=technique)
        handler = sheet.character.threads
        _ = handler.context_free_power
        handler.contextual_thread_power(PullActionContext())
        return sheet.character

    def test_gift_id_mapping_and_config_do_not_scale_with_technique_count(self) -> None:
        """Growing the sweep from 3 to 10 techniques must add ZERO queries: both the
        technique->gift mapping (Task 4 review) and the ``CapabilityPowerConfig`` fetch
        (Task 5 review finding 1/2 — was landing inside this per-grant loop via
        ``calculate_value``'s own single-call default) are resolved ONCE for the whole
        sweep, never once per grant.

        Requires a config row: with none, the gift-id mapping is skipped entirely
        (#2708 C1) rather than resolved-once, so this test would prove nothing about
        the property it names."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.magic.models import CapabilityPowerConfig

        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        small_character = self._character_with_technique_sweep(3)
        large_character = self._character_with_technique_sweep(10)

        with CaptureQueriesContext(connection) as small_ctx:
            small_sources = get_capability_sources_for_character(small_character)
        with CaptureQueriesContext(connection) as large_ctx:
            large_sources = get_capability_sources_for_character(large_character)

        assert small_sources
        assert large_sources

        small_queries = len(small_ctx.captured_queries)
        large_queries = len(large_ctx.captured_queries)
        self.assertEqual(
            large_queries,
            small_queries,
            f"expected the SAME query count (O(1), not O(N)) growing from 3 to 10 "
            f"techniques; got {small_queries} -> {large_queries}. An extra query per "
            f"technique here means the gift mapping or the config lookup is being "
            f"re-resolved per grant instead of once for the whole sweep.",
        )

    def test_no_config_row_costs_fewer_queries_than_a_config_row(self) -> None:
        """No ``CapabilityPowerConfig`` row: the curve is disabled everywhere, so
        ``_get_technique_sources`` skips the thread/power derivation (and its own
        gift-id-mapping query) entirely rather than deriving it and discarding the
        result (#2708 C1) — the config-existence check is still fetched ONCE for the
        whole sweep either way (Task 5 review), but the inert sweep costs exactly ONE
        FEWER query than the curved sweep: the skipped gift-id-mapping query."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        character = self._character_with_technique_sweep(10, label="nocfg")
        with CaptureQueriesContext(connection) as ctx:
            sources = get_capability_sources_for_character(character)
        assert sources
        no_config_count = len(ctx.captured_queries)

        from world.magic.models import CapabilityPowerConfig

        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        character = self._character_with_technique_sweep(10, label="withcfg")
        with CaptureQueriesContext(connection) as ctx:
            sources = get_capability_sources_for_character(character)
        assert sources
        with_config_count = len(ctx.captured_queries)

        self.assertEqual(
            with_config_count,
            no_config_count + 1,
            "expected the curved sweep to cost exactly one more query than the inert "
            "sweep (the gift-id-mapping query, skipped entirely when no config row "
            f"exists — #2708 C1); got no_config={no_config_count}, "
            f"with_config={with_config_count}.",
        )
