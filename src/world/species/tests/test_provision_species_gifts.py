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
from world.magic.constants import GiftKind, TargetKind
from world.magic.factories import CantripFactory, GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.models.gifts import CharacterGift
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.species.services import provision_species_gifts


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


class ProvisionSpeciesGiftsFinalizeIntegrationTest(TestCase):
    """Integration: finalize_magic_data wires provision_species_gifts (SQLite-safe)."""

    @classmethod
    def setUpTestData(cls):
        cls.resonance = ResonanceFactory()
        cls.minor_gift = GiftFactory(name="Test Elven Sight", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.species = SpeciesFactory(name="TestFinalizeElven")
        SpeciesGiftGrantFactory(species=cls.species, gift=cls.minor_gift, drawback_condition=None)
        cls.cantrip = CantripFactory()

    def test_finalize_grants_minor_gift_at_cg_resonance(self):
        """finalize_magic_data provisions species Minor Gift at the CG-chosen resonance."""
        sheet = CharacterSheetFactory(species=self.species)
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.cantrip.id,
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
