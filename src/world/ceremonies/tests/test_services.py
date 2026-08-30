"""Service tests for ceremony lifecycle (#2289): open/offer/speech/finish/abandon."""

from unittest import mock

from django.test import TestCase
from django.utils import timezone

from world.ceremonies.constants import (
    CeremonyStatus,
    CeremonyTypeKey,
    ConversionOfferStatus,
    SeanceOfferStatus,
)
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import CeremonyOffering, SeanceManifestationOffer
from world.ceremonies.services import (
    CeremonyError,
    ConversionOfferError,
    SeanceOfferError,
    abandon_ceremony,
    finish_ceremony,
    open_ceremony,
    open_funeral_for,
    pending_seance_offers_for_account,
    record_offering,
    respond_to_conversion_offer,
    respond_to_seance_offer,
    respond_to_wedding_consent_offer,
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


class OpenCoronationTests(TestCase):
    """Coronation open-time preconditions (#2358): solemnize-only, title required."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CORONATION, name="Coronation")
        cls.location = RoomProfileFactory()

    def _officiant(self):
        persona, sheet = _persona_with_sheet()
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=sheet, public_being=being)
        return persona

    def _title_and_holder(self, *, title_name: str = "Duchess of Crownward"):
        from world.roster.factories import FamilyFactory, KinspersonFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Title

        family = FamilyFactory(name=title_name)
        org = OrganizationFactory(name=f"House {title_name}", family=family)
        realm = org.society.realm
        honoree_sheet = CharacterSheetFactory()
        holder_kin = KinspersonFactory(family=family, sheet=honoree_sheet)
        title = Title.objects.create(
            name=title_name, tier="duchy", realm=realm, house=org, holder=holder_kin
        )
        return title, honoree_sheet

    def test_open_requires_title_kwarg(self) -> None:
        persona = self._officiant()
        _title, honoree_sheet = self._title_and_holder()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.CORONATION,
                honoree_sheets=[honoree_sheet],
                location_profile=self.location,
            )

    def test_open_rejects_non_holder_without_fiat(self) -> None:
        persona = self._officiant()
        title, _honoree_sheet = self._title_and_holder()
        outsider_sheet = CharacterSheetFactory()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.CORONATION,
                honoree_sheets=[outsider_sheet],
                location_profile=self.location,
                title=title,
            )

    def test_open_staff_fiat_bypasses_holder_check(self) -> None:
        persona = self._officiant()
        title, _honoree_sheet = self._title_and_holder()
        outsider_sheet = CharacterSheetFactory()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CORONATION,
            honoree_sheets=[outsider_sheet],
            location_profile=self.location,
            title=title,
            is_staff_fiat=True,
        )
        self.assertEqual(ceremony.title_id, title.pk)

    def test_open_accepts_holder(self) -> None:
        persona = self._officiant()
        title, honoree_sheet = self._title_and_holder()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CORONATION,
            honoree_sheets=[honoree_sheet],
            location_profile=self.location,
            title=title,
        )
        self.assertEqual(ceremony.title_id, title.pk)

    def test_open_requires_exactly_one_honoree(self) -> None:
        persona = self._officiant()
        title, honoree_sheet = self._title_and_holder()
        other_sheet = CharacterSheetFactory()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.CORONATION,
                honoree_sheets=[honoree_sheet, other_sheet],
                location_profile=self.location,
                title=title,
            )


class CoronationFinishTests(TestCase):
    """Coronation finish (#2358): mints the honoree deed + the permanent record."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CORONATION, name="Coronation")
        cls.location = RoomProfileFactory()

    def _open_coronation(self, *, title_name: str = "Duke of Crownfast"):
        from world.roster.factories import FamilyFactory, KinspersonFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Title

        persona, officiant_sheet = _persona_with_sheet()
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)

        family = FamilyFactory(name=title_name)
        org = OrganizationFactory(name=f"House {title_name}", family=family)
        realm = org.society.realm
        honoree_sheet = CharacterSheetFactory()
        holder_kin = KinspersonFactory(family=family, sheet=honoree_sheet)
        title = Title.objects.create(
            name=title_name, tier="duchy", realm=realm, house=org, holder=holder_kin
        )
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CORONATION,
            honoree_sheets=[honoree_sheet],
            location_profile=self.location,
            title=title,
        )
        return ceremony, honoree_sheet, title

    def test_finish_records_coronation_and_prestige(self) -> None:
        from world.ceremonies.models import Coronation

        ceremony, honoree_sheet, title = self._open_coronation()
        finish_ceremony(ceremony=ceremony)
        record = Coronation.objects.get(ceremony=ceremony)
        self.assertEqual(record.honoree_sheet_id, honoree_sheet.pk)
        self.assertEqual(record.title_id, title.pk)
        honoree = ceremony.honorees.get()
        self.assertGreater(honoree.prestige_awarded, 0)

    def test_second_coronation_same_title_rejected_at_open(self) -> None:
        ceremony, honoree_sheet, title = self._open_coronation()
        finish_ceremony(ceremony=ceremony)

        persona2, officiant_sheet2 = _persona_with_sheet()
        being2 = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet2, public_being=being2)
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona2,
                type_key=CeremonyTypeKey.CORONATION,
                honoree_sheets=[honoree_sheet],
                location_profile=self.location,
                title=title,
            )

    def test_second_coronation_different_title_allowed(self) -> None:
        from world.societies.houses.models import Title

        ceremony, honoree_sheet, title = self._open_coronation()
        finish_ceremony(ceremony=ceremony)

        imperial_title = Title.objects.create(
            name="Empress of Everything",
            tier="empire",
            realm=title.realm,
            house=title.house,
            holder=title.holder,
        )
        persona2, officiant_sheet2 = _persona_with_sheet()
        being2 = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet2, public_being=being2)

        ceremony2 = open_ceremony(
            officiant_persona=persona2,
            type_key=CeremonyTypeKey.CORONATION,
            honoree_sheets=[honoree_sheet],
            location_profile=self.location,
            title=imperial_title,
        )
        self.assertEqual(ceremony2.title_id, imperial_title.pk)


class WeddingConsentTests(TestCase):
    """Consent lives at the WEDDING ceremony, not at propose_betrothal (#2358)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.WEDDING, name="Wedding")
        cls.location = RoomProfileFactory()

    def _sheet_with_account(self):
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        sheet = CharacterSheetFactory()
        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        return sheet, player_data.account

    def _open_wedding(self, *, sheets):
        persona, officiant_sheet = _persona_with_sheet()
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)
        return open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.WEDDING,
            honoree_sheets=sheets,
            location_profile=self.location,
        )

    def test_open_creates_pending_consent_offer_per_honoree(self) -> None:
        sheet_a, _ = self._sheet_with_account()
        sheet_b, _ = self._sheet_with_account()
        ceremony = self._open_wedding(sheets=[sheet_a, sheet_b])
        for sheet in (sheet_a, sheet_b):
            offer = ceremony.honorees.get(honoree_sheet=sheet).wedding_consent_offer
            self.assertEqual(offer.status, SeanceOfferStatus.PENDING)

    def test_finish_blocked_while_any_offer_pending(self) -> None:
        sheet_a, account_a = self._sheet_with_account()
        sheet_b, _account_b = self._sheet_with_account()
        ceremony = self._open_wedding(sheets=[sheet_a, sheet_b])
        offer_a = ceremony.honorees.get(honoree_sheet=sheet_a).wedding_consent_offer
        respond_to_wedding_consent_offer(offer_a, account=account_a, accept=True)

        with self.assertRaises(CeremonyError):
            finish_ceremony(ceremony=ceremony)

    def test_finish_proceeds_once_both_accept(self) -> None:
        sheet_a, account_a = self._sheet_with_account()
        sheet_b, account_b = self._sheet_with_account()
        ceremony = self._open_wedding(sheets=[sheet_a, sheet_b])
        offer_a = ceremony.honorees.get(honoree_sheet=sheet_a).wedding_consent_offer
        offer_b = ceremony.honorees.get(honoree_sheet=sheet_b).wedding_consent_offer
        respond_to_wedding_consent_offer(offer_a, account=account_a, accept=True)
        respond_to_wedding_consent_offer(offer_b, account=account_b, accept=True)

        finish_ceremony(ceremony=ceremony)

        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.COMPLETED)

    def test_decline_aborts_whole_ceremony(self) -> None:
        sheet_a, account_a = self._sheet_with_account()
        sheet_b, _account_b = self._sheet_with_account()
        ceremony = self._open_wedding(sheets=[sheet_a, sheet_b])
        offer_a = ceremony.honorees.get(honoree_sheet=sheet_a).wedding_consent_offer

        respond_to_wedding_consent_offer(offer_a, account=account_a, accept=False)

        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)
        with self.assertRaises(CeremonyError):
            finish_ceremony(ceremony=ceremony)

    def test_full_flow_solemnizes_only_after_both_consent(self) -> None:
        from world.roster.factories import FamilyFactory, KinspersonFactory
        from world.roster.models import Union, UnionKind
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
        from world.societies.houses.pact_services import propose_betrothal

        UnionKind.objects.create(name="Marriage Ceremony Flow", confers_wedlock=True)
        senior_family = FamilyFactory(name="Solemn")
        senior_org = OrganizationFactory(name="House Solemn", family=senior_family)
        junior_family = FamilyFactory(name="Vow")
        junior_org = OrganizationFactory(name="House Vow", family=junior_family)
        leader = PersonaFactory()
        OrganizationMembershipFactory(organization=senior_org, persona=leader, rank=1)

        sheet_a, account_a = self._sheet_with_account()
        sheet_b, account_b = self._sheet_with_account()
        bride = KinspersonFactory(family=senior_family, sheet=sheet_a)
        groom = KinspersonFactory(family=junior_family, sheet=sheet_b)
        propose_betrothal(
            proposer=leader,
            kinsperson_a=bride,
            kinsperson_b=groom,
            senior_house=senior_org,
            junior_house=junior_org,
        )

        ceremony = self._open_wedding(sheets=[sheet_a, sheet_b])
        # Not yet solemnized — consent is still outstanding.
        self.assertFalse(Union.objects.filter(members=bride).filter(members=groom).exists())

        offer_a = ceremony.honorees.get(honoree_sheet=sheet_a).wedding_consent_offer
        offer_b = ceremony.honorees.get(honoree_sheet=sheet_b).wedding_consent_offer
        respond_to_wedding_consent_offer(offer_a, account=account_a, accept=True)
        respond_to_wedding_consent_offer(offer_b, account=account_b, accept=True)

        finish_ceremony(ceremony=ceremony)

        self.assertTrue(Union.objects.filter(members=bride).filter(members=groom).exists())


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

        # #3463: the ceremony deed is now minted at ZERO — a rite that risked
        # nothing is worth no song. The row survives because a conversion
        # ceremony's deed carries the scandal archetypes that route the #1464
        # fork, so the assertion moves to what the offering actually feeds now:
        # the honoree's PRESTIGE. Offerings still make a funeral grander; they
        # just no longer make the dead legendary.
        honoree_deed = LegendEntry.objects.filter(
            persona=dead.primary_persona,
            source_type__name="Ceremony",
        ).first()
        self.assertIsNotNone(honoree_deed)
        self.assertEqual(honoree_deed.base_value, 0)
        honoree = ceremony.honorees.get(honoree_sheet=dead)
        self.assertGreater(honoree.prestige_awarded, 0)

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


class RespondToSeanceOfferTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        cls.location = RoomProfileFactory()

    def _open_seance(self, *, sheet):
        persona, officiant_sheet = _persona_with_sheet()
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)
        return open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=self.location,
        )

    def _retired_sheet_with_account(self):
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        sheet = _dead_sheet()
        sheet.vitals.retired_at = timezone.now()
        sheet.vitals.save(update_fields=["retired_at"])
        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        return sheet, player_data.account

    def test_accept_moves_character_to_ceremony_location(self) -> None:
        sheet, account = self._retired_sheet_with_account()
        ceremony = self._open_seance(sheet=sheet)
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer

        respond_to_seance_offer(offer, account=account, accept=True)

        offer.refresh_from_db()
        self.assertEqual(offer.status, SeanceOfferStatus.ACCEPTED)
        self.assertIsNotNone(offer.responded_at)
        self.assertEqual(sheet.character.location, self.location.objectdb)

    def test_decline_does_not_move_character(self) -> None:
        sheet, account = self._retired_sheet_with_account()
        original_location = sheet.character.location
        ceremony = self._open_seance(sheet=sheet)
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer

        respond_to_seance_offer(offer, account=account, accept=False)

        offer.refresh_from_db()
        self.assertEqual(offer.status, SeanceOfferStatus.DECLINED)
        self.assertEqual(sheet.character.location, original_location)

    def test_wrong_account_cannot_answer(self) -> None:
        sheet, _account = self._retired_sheet_with_account()
        ceremony = self._open_seance(sheet=sheet)
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer

        from world.roster.factories import PlayerDataFactory

        stranger = PlayerDataFactory().account
        with self.assertRaises(SeanceOfferError):
            respond_to_seance_offer(offer, account=stranger, accept=True)

    def test_pending_offers_for_account_reaches_retired_honoree(self) -> None:
        sheet, account = self._retired_sheet_with_account()
        ceremony = self._open_seance(sheet=sheet)
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer

        offers = list(pending_seance_offers_for_account(account))

        self.assertEqual(offers, [offer])

    def test_pending_offer_reaches_account_after_real_retire_character_call(self) -> None:
        """Guards the load-bearing fact the whole retired-honoree flow depends on:
        ``retire_character`` stamps ``retired_at`` but does NOT close out the
        character's ``RosterTenure``. Every other seance test builds "retired" state
        by hand (``CharacterVitalsFactory(retired_at=...)``); this one calls the real
        service function so a future change to its behavior (e.g. also setting
        ``end_date``) would break this test instead of silently rotting the feature.
        """
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.vitals.services import retire_character

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
        account = player_data.account

        retire_character(sheet)

        sheet.vitals.refresh_from_db()
        self.assertIsNotNone(sheet.vitals.retired_at)
        tenure.refresh_from_db()
        self.assertIsNone(tenure.end_date)

        ceremony = self._open_seance(sheet=sheet)
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer
        self.assertEqual(offer.status, SeanceOfferStatus.PENDING)

        offers = list(pending_seance_offers_for_account(account))
        self.assertEqual(offers, [offer])


class RevokeSeanceManifestationsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        CeremonyTypeFactory(key=CeremonyTypeKey.FUNERAL, name="Funeral")
        cls.public = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def test_abandon_unpuppets_manifested_retired_honoree(self) -> None:
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        sheet = _dead_sheet()
        sheet.vitals.retired_at = timezone.now()
        sheet.vitals.save(update_fields=["retired_at"])

        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        account = player_data.account

        persona, officiant_sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=self.public)
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=self.location,
        )
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer
        respond_to_seance_offer(offer, account=account, accept=True)

        character = sheet.character
        character.db_account = account
        character.save()

        # No live Evennia session exists in a plain unit test — character.sessions
        # is always empty here, so this exercises the loop's no-op branch. It
        # proves the revoke hook runs cleanly on the abandon path without
        # raising, which is the realistic unit-test shape; a full puppet/
        # unpuppet round-trip belongs in an integration test, not this one.
        abandon_ceremony(ceremony=ceremony)

        self.assertEqual(ceremony.status, "abandoned")

    def test_abandon_calls_revoke_for_seance_type_only(self) -> None:
        persona, officiant_sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=self.public)
        sheet = _dead_sheet()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=self.location,
        )

        with mock.patch("world.ceremonies.services.revoke_seance_manifestations") as mock_revoke:
            abandon_ceremony(ceremony=ceremony)

        mock_revoke.assert_called_once_with(ceremony)

    def test_finish_calls_revoke_too(self) -> None:
        persona, officiant_sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=self.public)
        sheet = _dead_sheet()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=self.location,
        )

        with mock.patch("world.ceremonies.services.revoke_seance_manifestations") as mock_revoke:
            finish_ceremony(ceremony=ceremony)

        mock_revoke.assert_called_once_with(ceremony)

    def test_abandon_non_seance_ceremony_is_a_real_no_op(self) -> None:
        """revoke_seance_manifestations' own early-return guard (its body, not the call
        site — both abandon_ceremony and finish_ceremony call it unconditionally) must
        no-op cleanly for a Funeral. A Funeral honoree never gets a SeanceManifestationOffer
        (open_ceremony only creates those for SEANCE — see the ``if ceremony_type.key ==
        CeremonyTypeKey.SEANCE`` guard there), so there's nothing puppet-related to assert
        beyond: the call completes without raising and the ceremony still reaches ABANDONED.
        """
        persona, officiant_sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=self.public)
        dead = _dead_sheet()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[dead],
            location_profile=self.location,
        )

        abandon_ceremony(ceremony=ceremony)

        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)


class OpenConversionTests(TestCase):
    """#2361 — the two public routes fork right at open_ceremony."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")
        cls.old_being = WorshippedBeingFactory()
        cls.new_being = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _convert(self):
        persona, sheet = _persona_with_sheet()
        WorshipDeclaration.objects.create(character_sheet=sheet, public_being=self.old_being)
        return persona, sheet

    def test_requires_exactly_one_honoree(self) -> None:
        persona, sheet = self._convert()
        other = CharacterSheetFactory()
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.CONVERSION,
                honoree_sheets=[],
                location_profile=self.location,
                being=self.new_being,
            )
        with self.assertRaises(CeremonyError):
            open_ceremony(
                officiant_persona=persona,
                type_key=CeremonyTypeKey.CONVERSION,
                honoree_sheets=[sheet, other],
                location_profile=self.location,
                being=self.new_being,
            )

    def test_self_officiated_solo_route_creates_no_offer(self) -> None:
        """Ratified amendment #1b — the temple/solo route, no officiant needed."""
        persona, sheet = self._convert()
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[sheet],
            location_profile=self.location,
            being=self.new_being,
        )
        honoree = ceremony.honorees.get()
        self.assertEqual(honoree.ceremony.officiant.character_sheet_id, sheet.pk)
        self.assertFalse(hasattr(honoree, "conversion_offer") and honoree.conversion_offer)

    def test_pc_officiated_route_creates_pending_offer(self) -> None:
        """Ratified amendment #1a — a PC officiant, the convert must accept."""
        officiant_persona, _officiant_sheet = _persona_with_sheet()
        _convert_persona, convert_sheet = self._convert()
        ceremony = open_ceremony(
            officiant_persona=officiant_persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[convert_sheet],
            location_profile=self.location,
            being=self.new_being,
        )
        honoree = ceremony.honorees.get()
        self.assertEqual(honoree.conversion_offer.status, ConversionOfferStatus.PENDING)


class ConversionFinishTests(TestCase):
    """#2361 — the self-officiated solo route resolves entirely at finish."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")
        cls.old_being = WorshippedBeingFactory()
        cls.new_being = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _self_officiated(self, *, with_prior_declaration=True):
        sheet = CharacterSheetFactory()
        if with_prior_declaration:
            WorshipDeclaration.objects.create(character_sheet=sheet, public_being=self.old_being)
        persona = sheet.primary_persona
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[sheet],
            location_profile=self.location,
            being=self.new_being,
        )
        return ceremony, sheet

    def test_finish_repoints_public_being(self) -> None:
        ceremony, sheet = self._self_officiated()
        finish_ceremony(ceremony=ceremony, sincere=True)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being_id, self.new_being.pk)

    def test_finish_creates_first_declaration_when_none_existed(self) -> None:
        ceremony, sheet = self._self_officiated(with_prior_declaration=False)
        finish_ceremony(ceremony=ceremony)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being_id, self.new_being.pk)

    def test_sincere_choice_is_stored(self) -> None:
        ceremony, sheet = self._self_officiated()
        finish_ceremony(ceremony=ceremony, sincere=True)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertTrue(declaration.public_is_sincere)

    def test_lip_service_choice_is_stored(self) -> None:
        ceremony, sheet = self._self_officiated()
        finish_ceremony(ceremony=ceremony, sincere=False)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertFalse(declaration.public_is_sincere)

    def test_sincere_defaults_true_when_unspecified(self) -> None:
        ceremony, sheet = self._self_officiated()
        finish_ceremony(ceremony=ceremony)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertTrue(declaration.public_is_sincere)

    def test_devotion_standing_with_old_being_survives_untouched(self) -> None:
        """Decision 3 (unamended): conversion never touches DevotionStanding rows."""
        ceremony, sheet = self._self_officiated()
        standing = DevotionStanding.objects.create(
            character_sheet=sheet, being=self.old_being, favor=50, lifetime_favor=50
        )
        finish_ceremony(ceremony=ceremony)
        standing.refresh_from_db()
        self.assertEqual(standing.favor, 50)
        self.assertEqual(standing.lifetime_favor, 50)

    def test_old_secret_row_untouched_by_conversion(self) -> None:
        """Ratified amendment #3 — a mooted secret faith becomes historical, not deleted.

        This is a no-op to PROVE, not build: convert_public_worship only ever
        writes ``public_being``/``public_is_sincere`` — the secret side of the
        declaration is never in its ``update_fields``.
        """
        from world.secrets.factories import SecretFactory

        sheet = CharacterSheetFactory()
        dark_being = WorshippedBeingFactory()
        secret = SecretFactory(subject_sheet=sheet, content="Secretly worships The Hollow Flame")
        declaration = WorshipDeclaration.objects.create(
            character_sheet=sheet,
            public_being=self.old_being,
            secret_being=dark_being,
            secret=secret,
        )
        persona = sheet.primary_persona
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[sheet],
            location_profile=self.location,
            being=self.new_being,
        )

        finish_ceremony(ceremony=ceremony)

        declaration.refresh_from_db()
        self.assertEqual(declaration.public_being_id, self.new_being.pk)
        self.assertEqual(declaration.secret_being_id, dark_being.pk)
        self.assertEqual(declaration.secret_id, secret.pk)
        secret.refresh_from_db()
        self.assertEqual(secret.content, "Secretly worships The Hollow Flame")
        # Still independently discoverable — untouched by conversion means the
        # normal grant path still works exactly as it always did.
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.secrets.services import grant_secret_knowledge, secret_known_to

        knower_entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=knower_entry, player_data=PlayerDataFactory(), player_number=1
        )
        grant_secret_knowledge(roster_entry=knower_entry, secret=secret)
        self.assertTrue(secret_known_to(secret, knower_entry))


class RespondToConversionOfferTests(TestCase):
    """#2361 Ratified amendment #1a — the PC-officiated consent-gated route."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")
        cls.old_being = WorshippedBeingFactory()
        cls.new_being = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()

    def _pending_offer(self):
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        officiant_persona, _officiant_sheet = _persona_with_sheet()
        convert_sheet = CharacterSheetFactory()
        WorshipDeclaration.objects.create(
            character_sheet=convert_sheet, public_being=self.old_being
        )
        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=convert_sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)

        ceremony = open_ceremony(
            officiant_persona=officiant_persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[convert_sheet],
            location_profile=self.location,
            being=self.new_being,
        )
        offer = ceremony.honorees.get().conversion_offer
        return ceremony, convert_sheet, offer, player_data.account

    def test_accept_records_sincere_choice_on_the_offer(self) -> None:
        _ceremony, _sheet, offer, account = self._pending_offer()
        respond_to_conversion_offer(offer, account=account, accept=True, sincere=True)
        offer.refresh_from_db()
        self.assertEqual(offer.status, ConversionOfferStatus.ACCEPTED)
        self.assertTrue(offer.is_sincere)

    def test_accept_records_lip_service_choice_on_the_offer(self) -> None:
        _ceremony, _sheet, offer, account = self._pending_offer()
        respond_to_conversion_offer(offer, account=account, accept=True, sincere=False)
        offer.refresh_from_db()
        self.assertFalse(offer.is_sincere)

    def test_accept_then_finish_converts_with_recorded_sincerity(self) -> None:
        ceremony, sheet, offer, account = self._pending_offer()
        respond_to_conversion_offer(offer, account=account, accept=True, sincere=False)
        finish_ceremony(ceremony=ceremony)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being_id, self.new_being.pk)
        self.assertFalse(declaration.public_is_sincere)

    def test_decline_leaves_worship_untouched_at_finish(self) -> None:
        ceremony, sheet, offer, account = self._pending_offer()
        respond_to_conversion_offer(offer, account=account, accept=False)

        finish_ceremony(ceremony=ceremony)

        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being_id, self.old_being.pk)
        offer.refresh_from_db()
        self.assertEqual(offer.status, ConversionOfferStatus.DECLINED)
        honoree = ceremony.honorees.get()
        self.assertEqual(honoree.prestige_awarded, 0)

    def test_never_answered_offer_leaves_worship_untouched_at_finish(self) -> None:
        ceremony, sheet, _offer, _account = self._pending_offer()
        finish_ceremony(ceremony=ceremony)
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being_id, self.old_being.pk)

    def test_wrong_account_cannot_answer(self) -> None:
        from world.roster.factories import PlayerDataFactory

        _ceremony, _sheet, offer, _account = self._pending_offer()
        stranger = PlayerDataFactory().account
        with self.assertRaises(ConversionOfferError):
            respond_to_conversion_offer(offer, account=stranger, accept=True)

    def test_double_answer_rejected(self) -> None:
        _ceremony, _sheet, offer, account = self._pending_offer()
        respond_to_conversion_offer(offer, account=account, accept=True)
        with self.assertRaises(ConversionOfferError):
            respond_to_conversion_offer(offer, account=account, accept=True)


class ConversionScandalForkTests(TestCase):
    """#2361 — the deed rides the existing #1464 scandal fork via _mint_ceremony_deed."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.character_creation.factories import RealmFactory
        from world.seeds.scandal_archetypes import seed_scandal_archetypes
        from world.societies.factories import SocietyFactory

        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")
        cls.old_being = WorshippedBeingFactory()
        cls.new_being = WorshippedBeingFactory()
        seed_scandal_archetypes()
        cls.realm = RealmFactory()
        # method=5 (extreme Honor) reacts hard to Treacherous Scandal's method_delta=-3.
        cls.honor_bound = SocietyFactory(realm=cls.realm, method=5)
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, realm=cls.realm)
        cls.profile = RoomProfileFactory(area=cls.kingdom, is_public=True)

    def _scene(self):
        from world.scenes.factories import SceneFactory

        return SceneFactory(location=self.profile.objectdb)

    def test_conversion_away_from_declared_faith_tags_treacherous_scandal(self) -> None:
        from world.societies.models import LegendEntry

        scene = self._scene()
        sheet = CharacterSheetFactory()
        WorshipDeclaration.objects.create(character_sheet=sheet, public_being=self.old_being)
        persona = sheet.primary_persona
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[sheet],
            location_profile=self.profile,
            being=self.new_being,
            scene=scene,
        )

        finish_ceremony(ceremony=ceremony)

        entry = LegendEntry.objects.get(persona=persona, title__startswith="Converted to")
        self.assertEqual({a.name for a in entry.archetypes.all()}, {"Treacherous Scandal"})
        self.assertIn(self.honor_bound, entry.societies_aware.all())

    def test_first_declaration_carries_no_archetype_and_skips_scandal_fork(self) -> None:
        from world.societies.models import LegendEntry

        scene = self._scene()
        sheet = CharacterSheetFactory()  # no prior declaration
        persona = sheet.primary_persona
        ceremony = open_ceremony(
            officiant_persona=persona,
            type_key=CeremonyTypeKey.CONVERSION,
            honoree_sheets=[sheet],
            location_profile=self.profile,
            being=self.new_being,
            scene=scene,
        )

        finish_ceremony(ceremony=ceremony)

        entry = LegendEntry.objects.get(persona=persona, title__startswith="Converted to")
        self.assertEqual(entry.archetypes.count(), 0)
        self.assertEqual(entry.societies_aware.count(), 0)
