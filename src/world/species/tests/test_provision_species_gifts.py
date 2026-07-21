"""Tests for provision_species_gifts service (#1580).

SQLite-safe tests: gift, thread, subspecies-inheritance, idempotent, no-species,
resonance-fallback.

@tag("postgres") tests: drawback condition — apply_condition goes through
_build_bulk_context which uses DISTINCT ON (PG-only). CI PG shard covers these.
"""

from django.test import TestCase, tag

from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import finalize_magic_data
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import GiftKind, TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, TraditionFactory
from world.magic.models import Thread
from world.magic.models.gifts import CharacterGift
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.species.services import provision_species_gifts, total_species_gift_cost


class ProvisionSpeciesGiftsTests(TestCase):
    """SQLite-safe unit tests for provision_species_gifts (no drawback path)."""

    @classmethod
    def setUpTestData(cls):
        cls.resonance = ResonanceFactory()
        cls.parent_species = SpeciesFactory(name="TestElven")
        cls.subspecies = SpeciesFactory(name="TestRexAlfar", parent=cls.parent_species)
        cls.minor_gift = GiftFactory(name="Test Night Vision", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.grant = SpeciesGiftGrantFactory(
            species=cls.parent_species,
            gift=cls.minor_gift,
            drawback_condition=None,
        )

    def test_grants_minor_gift_and_latent_thread(self):
        """provision_species_gifts creates CharacterGift + level-0 GIFT Thread at resonance."""
        sheet = CharacterSheetFactory(species=self.parent_species)
        provision_species_gifts(sheet, resonance=self.resonance)
        self.assertTrue(
            CharacterGift.objects.filter(character=sheet, gift=self.minor_gift).exists(),
            "CharacterGift should be created for the species' Minor Gift",
        )
        thread = Thread.objects.filter(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.minor_gift,
        ).first()
        self.assertIsNotNone(thread, "Latent GIFT thread should be created")
        self.assertEqual(thread.level, 0)
        self.assertEqual(thread.resonance, self.resonance)

    def test_subspecies_inherits_parent_grants(self):
        """A subspecies sheet gets grants from the parent species."""
        sheet = CharacterSheetFactory(species=self.subspecies)
        provision_species_gifts(sheet, resonance=self.resonance)
        self.assertTrue(
            CharacterGift.objects.filter(character=sheet, gift=self.minor_gift).exists(),
            "Subspecies should inherit parent's species gift grant",
        )
        self.assertTrue(
            Thread.objects.filter(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.minor_gift,
            ).exists(),
            "Subspecies sheet should also get the latent GIFT thread",
        )

    def test_idempotent(self):
        """Calling provision_species_gifts twice creates no duplicate CharacterGift / Thread."""
        sheet = CharacterSheetFactory(species=self.parent_species)
        provision_species_gifts(sheet, resonance=self.resonance)
        provision_species_gifts(sheet, resonance=self.resonance)
        self.assertEqual(
            CharacterGift.objects.filter(character=sheet, gift=self.minor_gift).count(),
            1,
            "No duplicate CharacterGift on second call",
        )
        self.assertEqual(
            Thread.objects.filter(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.minor_gift,
            ).count(),
            1,
            "No duplicate Thread on second call",
        )

    def test_no_op_when_no_species(self):
        """Sheet with no species returns empty list and creates nothing."""
        sheet = CharacterSheetFactory(species=None)
        result = provision_species_gifts(sheet)
        self.assertEqual(result, [])
        self.assertFalse(CharacterGift.objects.filter(character=sheet).exists())

    def test_resonance_falls_back_to_gift_supported_set(self):
        """When resonance=None, falls back to grant.gift.resonances.first()."""
        sheet = CharacterSheetFactory(species=self.parent_species)
        provision_species_gifts(sheet, resonance=None)
        thread = Thread.objects.filter(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.minor_gift,
        ).first()
        self.assertIsNotNone(thread, "Thread should be created via fallback resonance")
        self.assertEqual(
            thread.resonance,
            self.resonance,
            "Fallback resonance should match gift.resonances.first()",
        )

    def test_no_condition_when_no_drawback(self):
        """A grant without drawback_condition applies no ConditionInstance."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory(species=self.parent_species)
        provision_species_gifts(sheet, resonance=self.resonance)
        self.assertFalse(
            ConditionInstance.objects.filter(target=sheet.character).exists(),
            "No condition should be applied when grant has no drawback_condition",
        )

    def test_no_condition_when_no_benefit(self):
        """A grant without benefit_condition applies no extra ConditionInstance."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory(species=self.parent_species)
        provision_species_gifts(sheet, resonance=self.resonance)
        self.assertFalse(
            ConditionInstance.objects.filter(target=sheet.character).exists(),
            "No condition should be applied when grant has no benefit_condition",
        )

    def test_drawback_distinction_applied_with_species_origin(self):
        """A grant's drawback_distinction is minted at finalize with origin=SPECIES."""
        distinction = DistinctionFactory(slug="test-feared", name="Feared")
        grant = SpeciesGiftGrantFactory(
            species=SpeciesFactory(name="TestInfernal"),
            gift=GiftFactory(name="Test Hellfire", kind=GiftKind.MINOR),
            drawback_distinction=distinction,
        )
        grant.gift.resonances.add(self.resonance)
        sheet = CharacterSheetFactory(species=grant.species)
        provision_species_gifts(sheet, resonance=self.resonance)
        cd = CharacterDistinction.objects.get(character=sheet, distinction=distinction)
        self.assertEqual(cd.origin, DistinctionOrigin.SPECIES)

    def test_drawback_distinction_is_idempotent(self):
        """Double finalize does not rank up or duplicate the drawback distinction."""
        distinction = DistinctionFactory(slug="test-feared-2", name="Feared2", max_rank=2)
        grant = SpeciesGiftGrantFactory(
            species=SpeciesFactory(name="TestInfernal2"),
            gift=GiftFactory(name="Test Hellfire2", kind=GiftKind.MINOR),
            drawback_distinction=distinction,
        )
        grant.gift.resonances.add(self.resonance)
        sheet = CharacterSheetFactory(species=grant.species)
        provision_species_gifts(sheet, resonance=self.resonance)
        provision_species_gifts(sheet, resonance=self.resonance)
        rows = CharacterDistinction.objects.filter(character=sheet, distinction=distinction)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().rank, 1)


class ProvisionSpeciesGiftsFinalizeIntegrationTest(TestCase):
    """Integration: finalize_magic_data wires provision_species_gifts (SQLite-safe)."""

    @classmethod
    def setUpTestData(cls):
        cls.resonance = ResonanceFactory()
        cls.minor_gift = GiftFactory(name="Test Elven Sight", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.species = SpeciesFactory(name="TestFinalizeElven")
        SpeciesGiftGrantFactory(species=cls.species, gift=cls.minor_gift, drawback_condition=None)
        cls.tradition = TraditionFactory()

    def test_finalize_grants_minor_gift_at_cg_resonance(self):
        """finalize_magic_data provisions species Minor Gift at the CG-chosen resonance."""
        sheet = CharacterSheetFactory(species=self.species)
        draft = CharacterDraftFactory(
            selected_tradition=self.tradition,
            draft_data={
                "selected_gift_resonance_id": self.resonance.id,
            },
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            CharacterGift.objects.filter(character=sheet, gift=self.minor_gift).exists(),
            "finalize_magic_data should provision the species Minor Gift",
        )
        thread = Thread.objects.filter(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.minor_gift,
        ).first()
        self.assertIsNotNone(thread, "Latent GIFT thread for species gift should be created")
        self.assertEqual(
            thread.resonance,
            self.resonance,
            "Species gift thread should use the CG-chosen resonance",
        )


@tag("postgres")
class ProvisionSpeciesGiftsDrawbackTest(TestCase):
    """Drawback condition tests. PG-only: apply_condition uses DISTINCT ON via _build_bulk_context.

    Run on CI's postgres shard. Do NOT run on the SQLite fast tier.
    """

    @classmethod
    def setUpTestData(cls):
        from world.conditions.factories import ConditionTemplateFactory

        cls.drawback = ConditionTemplateFactory(name="Test Sunlight Vulnerability")
        cls.resonance = ResonanceFactory()
        cls.minor_gift = GiftFactory(name="Test Vampiric Gift", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.species = SpeciesFactory(name="TestVampireDrawback")
        SpeciesGiftGrantFactory(
            species=cls.species, gift=cls.minor_gift, drawback_condition=cls.drawback
        )

    def test_drawback_applied_when_set(self):
        """A grant with drawback_condition applies a ConditionInstance to the character."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory(species=self.species)
        provision_species_gifts(sheet, resonance=self.resonance)

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet.character,
                condition=self.drawback,
            ).exists(),
            "Drawback condition should be applied to the character when the grant has one",
        )

    def test_drawback_idempotent_for_stackable_template(self):
        """Re-calling provision_species_gifts does not stack a stackable drawback condition.

        Guard: only apply when no active ConditionInstance (resolved_at__isnull=True) already
        exists for (target, condition). Without the guard a stackable template would increment
        stacks on every finalize call.
        """
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionInstance

        stackable_drawback = ConditionTemplateFactory(
            name="Test Stackable Species Drawback",
            is_stackable=True,
            max_stacks=5,
        )
        resonance = ResonanceFactory()
        minor_gift = GiftFactory(name="Test Gift With Stackable Drawback", kind=GiftKind.MINOR)
        minor_gift.resonances.add(resonance)
        species = SpeciesFactory(name="TestStackableDrawbackSpecies")
        SpeciesGiftGrantFactory(
            species=species, gift=minor_gift, drawback_condition=stackable_drawback
        )
        sheet = CharacterSheetFactory(species=species)

        provision_species_gifts(sheet, resonance=resonance)
        provision_species_gifts(sheet, resonance=resonance)

        instances = ConditionInstance.objects.filter(
            target=sheet.character,
            condition=stackable_drawback,
            resolved_at__isnull=True,
        )
        self.assertEqual(instances.count(), 1, "Guard must prevent a second ConditionInstance")
        self.assertEqual(
            instances.first().stacks,
            1,
            "Guard must prevent stacks from incrementing on re-finalize",
        )


@tag("postgres")
class ProvisionSpeciesGiftsBenefitTest(TestCase):
    """Benefit condition tests. PG-only: apply_condition uses DISTINCT ON via
    _build_bulk_context. Run on CI's postgres shard. Do NOT run on SQLite fast tier.
    """

    @classmethod
    def setUpTestData(cls):
        from world.conditions.factories import ConditionTemplateFactory

        cls.benefit = ConditionTemplateFactory(name="Test Vampiric Will")
        cls.resonance = ResonanceFactory()
        cls.minor_gift = GiftFactory(name="Test Vampiric Benefit Gift", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.species = SpeciesFactory(name="TestVampireBenefit")
        SpeciesGiftGrantFactory(
            species=cls.species, gift=cls.minor_gift, benefit_condition=cls.benefit
        )

    def test_benefit_applied_when_set(self):
        """A grant with benefit_condition applies a ConditionInstance to the character."""
        from world.conditions.models import ConditionInstance

        sheet = CharacterSheetFactory(species=self.species)
        provision_species_gifts(sheet, resonance=self.resonance)

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet.character,
                condition=self.benefit,
            ).exists(),
            "Benefit condition should be applied to the character when the grant has one",
        )

    def test_benefit_idempotent_for_stackable_template(self):
        """Re-calling provision_species_gifts does not stack a stackable benefit condition."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionInstance

        stackable_benefit = ConditionTemplateFactory(
            name="Test Stackable Species Benefit",
            is_stackable=True,
            max_stacks=5,
        )
        resonance = ResonanceFactory()
        minor_gift = GiftFactory(name="Test Gift With Stackable Benefit", kind=GiftKind.MINOR)
        minor_gift.resonances.add(resonance)
        species = SpeciesFactory(name="TestStackableBenefitSpecies")
        SpeciesGiftGrantFactory(
            species=species, gift=minor_gift, benefit_condition=stackable_benefit
        )
        sheet = CharacterSheetFactory(species=species)

        provision_species_gifts(sheet, resonance=resonance)
        provision_species_gifts(sheet, resonance=resonance)

        instances = ConditionInstance.objects.filter(
            target=sheet.character,
            condition=stackable_benefit,
            resolved_at__isnull=True,
        )
        self.assertEqual(instances.count(), 1, "Guard must prevent a second ConditionInstance")
        self.assertEqual(
            instances.first().stacks,
            1,
            "Guard must prevent stacks from incrementing on re-finalize",
        )

    def test_benefit_condition_check_modifier_reaches_modifier_seam(self):
        """The species benefit condition's ConditionCheckModifier is picked up by
        get_check_modifier for the resist check type — no mocking, proves the
        existing modifier seam (condition_contributions) does the work for free.
        """
        from world.checks.factories import CheckTypeFactory
        from world.conditions.factories import (
            ConditionCheckModifierFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.services import get_check_modifier

        resist_check = CheckTypeFactory()
        benefit_with_modifier = ConditionTemplateFactory(name="Test Resolute Will")
        ConditionCheckModifierFactory(
            condition=benefit_with_modifier,
            check_type=resist_check,
            modifier_value=1000,
        )
        resonance = ResonanceFactory()
        minor_gift = GiftFactory(name="Test Gift With Check Modifier Benefit", kind=GiftKind.MINOR)
        minor_gift.resonances.add(resonance)
        species = SpeciesFactory(name="TestResoluteWillSpecies")
        SpeciesGiftGrantFactory(
            species=species, gift=minor_gift, benefit_condition=benefit_with_modifier
        )
        sheet = CharacterSheetFactory(species=species)

        provision_species_gifts(sheet, resonance=resonance)

        result = get_check_modifier(sheet, resist_check)
        self.assertEqual(
            result.total_modifier,
            1000,
            "Species benefit condition's ConditionCheckModifier should reach "
            "get_check_modifier for the resist check type",
        )


class TotalSpeciesGiftCostTests(TestCase):
    """Unit tests for total_species_gift_cost (#2472 encapsulation fix)."""

    def test_costed_grant_returns_cost(self):
        """A species with a costed grant returns that grant's cg_point_cost."""
        species = SpeciesFactory(name="TestCostedGiftSpecies")
        SpeciesGiftGrantFactory(
            species=species,
            gift=GiftFactory(name="Test Costed Gift", kind=GiftKind.MINOR),
            cg_point_cost=7,
        )
        self.assertEqual(total_species_gift_cost(species), 7)

    def test_subspecies_charged_for_parents_costed_grant(self):
        """A subspecies whose parent carries the costed grant returns the parent's cost."""
        parent = SpeciesFactory(name="TestCostedParentSpecies")
        SpeciesGiftGrantFactory(
            species=parent,
            gift=GiftFactory(name="Test Parent Costed Gift", kind=GiftKind.MINOR),
            cg_point_cost=5,
        )
        subspecies = SpeciesFactory(name="TestCostedSubspecies", parent=parent)
        self.assertEqual(total_species_gift_cost(subspecies), 5)

    def test_no_costed_grant_returns_zero(self):
        """A species with no costed grant returns 0."""
        species = SpeciesFactory(name="TestUncostedSpecies")
        SpeciesGiftGrantFactory(
            species=species,
            gift=GiftFactory(name="Test Free Gift", kind=GiftKind.MINOR),
            cg_point_cost=0,
        )
        self.assertEqual(total_species_gift_cost(species), 0)
