"""Service tests for ceremony lifecycle (#2289): open/offer/speech/finish/abandon."""

from unittest import mock

from django.test import TestCase
from django.utils import timezone

from world.ceremonies.constants import CeremonyStatus, CeremonyTypeKey, SeanceOfferStatus
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import CeremonyOffering, SeanceManifestationOffer
from world.ceremonies.services import (
    CeremonyError,
    abandon_ceremony,
    finish_ceremony,
    open_ceremony,
    open_funeral_for,
    record_offering,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import DevotionStanding, WorshipDeclaration


def _persona_with_sheet():
    sheet = CharacterSheetFactory()
    persona = sheet.primary_persona
    return persona, sheet


def _dead_sheet():
    sheet = CharacterSheetFactory()
    CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
    return sheet


class OpenCeremonyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        cls.funeral_type = CeremonyTypeFactory(key=CeremonyTypeKey.FUNERAL, name="Funeral")
        cls.public = WorshippedBeingFactory()
        cls.dark = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _officiant(self, public=None, secret=None):
        persona, sheet = _persona_with_sheet()
        if public or secret:
            WorshipDeclaration.objects.create(
                character_sheet=sheet, public_being=public, secret_being=secret
            )
        return persona, sheet

    def test_defaults_to_public_declaration(self) -> None:
        persona, _ = self._officiant(public=self.public)
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[_dead_sheet()],
            location_profile=self.location,
        )
        self.assertEqual(ceremony.being, self.public)
        self.assertEqual(ceremony.presented_being, self.public)
        self.assertFalse(ceremony.is_twisted)

    def test_no_declaration_and_no_explicit_being_errors(self) -> None:
        persona, _ = self._officiant()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.FUNERAL,
                honoree_sheets=[_dead_sheet()],
                location_profile=self.location,
            )

    def test_secret_being_override_is_twisted_with_public_front(self) -> None:
        persona, _ = self._officiant(public=self.public, secret=self.dark)
        with mock.patch("world.ceremonies.leak.run_twisted_rite_leak") as leak:
            ceremony = open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.FUNERAL,
                honoree_sheets=[_dead_sheet()],
                location_profile=self.location,
                being=self.dark,
            )
        self.assertEqual(ceremony.being, self.dark)
        self.assertEqual(ceremony.presented_being, self.public)
        self.assertTrue(ceremony.is_twisted)
        leak.assert_called_once()

    def test_third_being_override_is_open_rite(self) -> None:
        third = WorshippedBeingFactory()
        persona, _ = self._officiant(public=self.public, secret=self.dark)
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[_dead_sheet()],
            location_profile=self.location,
            being=third,
        )
        self.assertEqual(ceremony.being, third)
        self.assertEqual(ceremony.presented_being, third)
        self.assertFalse(ceremony.is_twisted)

    def test_living_honoree_rejected(self) -> None:
        persona, _ = self._officiant(public=self.public)
        living = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=living)
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.FUNERAL,
                honoree_sheets=[living],
                location_profile=self.location,
            )

    def test_second_open_ceremony_at_location_rejected(self) -> None:
        persona, _ = self._officiant(public=self.public)
        open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[_dead_sheet()],
            location_profile=self.location,
        )
        other, _ = self._officiant(public=self.public)
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=other,
                type_key=CeremonyTypeKey.FUNERAL,
                honoree_sheets=[_dead_sheet()],
                location_profile=self.location,
            )


class OpenSeanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        cls.seance_type = CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        cls.public = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _officiant(self):
        persona, sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=sheet, public_being=self.public)
        return persona

    def test_rejects_living_honoree(self) -> None:
        persona = self._officiant()
        living_sheet = CharacterSheetFactory()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.SEANCE,
                honoree_sheets=[living_sheet],
                location_profile=self.location,
            )

    def test_accepts_retired_honoree_and_creates_pending_offer(self) -> None:
        persona = self._officiant()
        dead_sheet = _dead_sheet()
        CharacterVitalsFactory(character_sheet=dead_sheet)  # no-op if already created
        dead_sheet.vitals.retired_at = timezone.now()
        dead_sheet.vitals.save(update_fields=["retired_at"])

        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[dead_sheet],
            location_profile=self.location,
        )

        honoree = ceremony.honorees.get(honoree_sheet=dead_sheet)
        self.assertEqual(honoree.seance_offer.status, SeanceOfferStatus.PENDING)
        self.assertEqual(
            SeanceManifestationOffer.objects.filter(ceremony_honoree=honoree).count(), 1
        )

    def test_requires_at_least_one_honoree(self) -> None:
        persona = self._officiant()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.SEANCE,
                honoree_sheets=[],
                location_profile=self.location,
            )


class CeremonyFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        cls.funeral_type = CeremonyTypeFactory(key=CeremonyTypeKey.FUNERAL, name="Funeral")
        cls.being = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _open_funeral(self):
        persona, sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=sheet, public_being=self.being)
        dead = _dead_sheet()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[dead],
            location_profile=self.location,
        )
        return ceremony, sheet, dead

    def test_offering_destroys_item_and_feeds_pool_and_devotion(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.items.models import ItemInstance

        ceremony, officiant_sheet, _ = self._open_funeral()
        instance = ItemInstanceFactory(template__value=10)
        instance_pk = instance.pk
        record_offering(ceremony=ceremony, item_instances=[instance])
        self.assertFalse(ItemInstance.objects.filter(pk=instance_pk).exists())
        self.being.refresh_from_db()
        self.assertGreater(self.being.resonance_pool, 0)
        offering = CeremonyOffering.objects.get(ceremony=ceremony)
        self.assertEqual(offering.item_value, 10)
        self.assertEqual(offering.item_legend_value, 0)
        self.assertIsNotNone(offering.worship_grant)
        standing = DevotionStanding.objects.get(character_sheet=officiant_sheet, being=self.being)
        self.assertGreater(standing.favor, 0)

    def test_offering_snapshots_item_legend_value(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.societies.factories import LegendEntryFactory, LegendSourceTypeFactory

        ceremony, _, _ = self._open_funeral()
        instance = ItemInstanceFactory(template__value=10)
        source_type = LegendSourceTypeFactory()
        sheet = CharacterSheetFactory()
        deed = LegendEntryFactory(
            persona=sheet.primary_persona, source_type=source_type, base_value=75
        )
        instance.legend_deeds.add(deed)

        record_offering(ceremony=ceremony, item_instances=[instance])

        offering = CeremonyOffering.objects.get(ceremony=ceremony)
        self.assertEqual(offering.item_legend_value, 75)

    def test_finish_tallies_honoree_and_officiant_deeds_and_calls_will_seam(self) -> None:
        from world.societies.models import LegendEntry

        ceremony, officiant_sheet, dead = self._open_funeral()
        with mock.patch("world.ceremonies.services.execute_will") as seam:
            finish_ceremony(ceremony=ceremony)
        seam.assert_called_once_with(dead)
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.COMPLETED)
        self.assertIsNotNone(ceremony.finished_at)
        honoree = ceremony.honorees.get()
        self.assertGreater(honoree.prestige_awarded, 0)
        self.assertTrue(LegendEntry.objects.filter(persona=dead.primary_persona).exists())
        self.assertTrue(
            LegendEntry.objects.filter(persona=officiant_sheet.primary_persona).exists()
        )

    def test_finish_adds_offering_legend_to_honoree_deed(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.societies.factories import LegendEntryFactory, LegendSourceTypeFactory
        from world.societies.models import LegendEntry

        ceremony, _officiant_sheet, dead = self._open_funeral()

        # Offer a legendary item (legend_value=75) alongside a plain item (legend_value=0)
        legendary = ItemInstanceFactory(template__value=10)
        source_type = LegendSourceTypeFactory()
        maker_sheet = CharacterSheetFactory()
        deed = LegendEntryFactory(
            persona=maker_sheet.primary_persona, source_type=source_type, base_value=75
        )
        legendary.legend_deeds.add(deed)
        plain = ItemInstanceFactory(template__value=5)

        record_offering(ceremony=ceremony, item_instances=[legendary, plain])

        with mock.patch("world.ceremonies.services.execute_will"):
            finish_ceremony(ceremony=ceremony)

        # The honoree's ceremony deed should include the 75 legend from the item.
        honoree_deed = LegendEntry.objects.filter(
            persona=dead.primary_persona,
            source_type__name="Ceremony",
        ).first()
        self.assertIsNotNone(honoree_deed)
        # Base honoree prestige (50) + offering gold (15*1=15) + legend (75) = 140
        # before multiplier. Just assert it exceeds the no-legend baseline.
        self.assertGreater(honoree_deed.base_value, 75)

        # The maker's deed survives — item was destroyed but deed is not.
        self.assertTrue(LegendEntry.objects.filter(pk=deed.pk).exists())
        self.assertEqual(deed.persona, maker_sheet.primary_persona)

    def test_finish_twice_rejected(self) -> None:
        ceremony, _, _ = self._open_funeral()
        finish_ceremony(ceremony=ceremony)
        with self.assertRaises(CeremonyError):
            finish_ceremony(ceremony=ceremony)

    def test_abandon_awards_nothing_and_frees_location_and_window(self) -> None:
        from world.societies.models import LegendEntry

        ceremony, _, dead = self._open_funeral()
        self.assertEqual(open_funeral_for(dead), ceremony)
        abandon_ceremony(ceremony=ceremony)
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)
        self.assertIsNone(open_funeral_for(dead))
        self.assertFalse(LegendEntry.objects.filter(persona=dead.primary_persona).exists())
        honoree = ceremony.honorees.get()
        self.assertEqual(honoree.prestige_awarded, 0)

    def test_open_funeral_for_finds_only_open_funerals(self) -> None:
        ceremony, _, dead = self._open_funeral()
        self.assertEqual(open_funeral_for(dead), ceremony)
        finish_ceremony(ceremony=ceremony)
        self.assertIsNone(open_funeral_for(dead))
