"""Ceremony action journeys via action.run() (#2289)."""

from django.test import TestCase
from django.utils import timezone
from evennia.utils import create as evennia_create

from actions.definitions.ceremonies import (
    AbandonCeremonyAction,
    CeremonyOfferingAction,
    FinishCeremonyAction,
    OpenCeremonyAction,
)
from actions.definitions.communication import EmitAction
from world.ceremonies.constants import CeremonyStatus, CeremonyTypeKey
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import Ceremony
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


def _make_room(key: str):
    return evennia_create.create_object(typeclass="typeclasses.rooms.Room", key=key, nohome=True)


def _make_account_for(sheet):
    from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory

    player_data = PlayerDataFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return player_data.account


class CeremonyActionJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        CeremonyTypeFactory(key=CeremonyTypeKey.FUNERAL, name="Funeral")
        cls.being = WorshippedBeingFactory()

        cls.officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=cls.officiant_sheet)
        WorshipDeclaration.objects.create(
            character_sheet=cls.officiant_sheet, public_being=cls.being
        )
        cls.officiant = cls.officiant_sheet.character

        cls.dead_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=cls.dead_sheet,
            life_state=CharacterLifeState.DEAD,
            # Died long ago: the IC-day window is closed, so only the funeral
            # container can open the ghost's voice.
            died_at=timezone.now() - timezone.timedelta(days=30),
        )
        cls.ghost = cls.dead_sheet.character

    def setUp(self) -> None:
        self.room = _make_room("Chapel")
        self.officiant.location = self.room
        self.ghost.location = self.room

    def _open_funeral(self):
        return OpenCeremonyAction().run(
            actor=self.officiant,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_names=[self.ghost.key],
        )

    def test_full_funeral_journey_with_ghost_window(self) -> None:
        # Before the funeral: the ghost's voice is spent (died 30 days ago).
        blocked = EmitAction().run(actor=self.ghost, text="...")
        self.assertFalse(blocked.success)

        result = self._open_funeral()
        self.assertTrue(result.success, result.message)
        ceremony = Ceremony.objects.get()
        self.assertEqual(ceremony.officiant.character_sheet, self.officiant_sheet)

        # The open funeral is a recognized container: the ghost may emit here.
        allowed = EmitAction().run(actor=self.ghost, text="A cold presence settles.")
        self.assertTrue(allowed.success, allowed.message)

        finish = FinishCeremonyAction().run(actor=self.officiant)
        self.assertTrue(finish.success, finish.message)
        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.COMPLETED)

        # Window closed again once the rite concludes.
        closed = EmitAction().run(actor=self.ghost, text="...")
        self.assertFalse(closed.success)

    def test_only_officiant_may_direct(self) -> None:
        self._open_funeral()
        bystander_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=bystander_sheet)
        bystander = bystander_sheet.character
        bystander.location = self.room
        result = FinishCeremonyAction().run(actor=bystander)
        self.assertFalse(result.success)
        self.assertIn("officiant", result.message)

    def test_offering_requires_reachable_item(self) -> None:
        self._open_funeral()
        result = CeremonyOfferingAction().run(
            actor=self.officiant, item_names=["nonexistent relic"]
        )
        self.assertFalse(result.success)

    def test_abandon_frees_location(self) -> None:
        self._open_funeral()
        result = AbandonCeremonyAction().run(actor=self.officiant)
        self.assertTrue(result.success, result.message)
        ceremony = Ceremony.objects.get()
        self.assertEqual(ceremony.status, CeremonyStatus.ABANDONED)
        # A new ceremony may open at the same location.
        again = self._open_funeral()
        self.assertTrue(again.success, again.message)

    def test_open_requires_recognized_type(self) -> None:
        result = OpenCeremonyAction().run(
            actor=self.officiant, type_key="coronation", honoree_names=[]
        )
        self.assertFalse(result.success)


class RespondSeanceOfferActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        cls.location = RoomProfileFactory()

        officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=officiant_sheet)
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)
        cls.officiant_persona = officiant_sheet.primary_persona

        cls.dead_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=cls.dead_sheet,
            life_state=CharacterLifeState.DEAD,
            retired_at=timezone.now(),
        )
        cls.player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=cls.dead_sheet)
        RosterTenureFactory(roster_entry=entry, player_data=cls.player_data)

        cls.ceremony = Ceremony.objects.none()  # replaced in setUp per-test to keep isolation

    def _open_seance(self):
        from world.ceremonies.services import open_ceremony

        return open_ceremony(
            officiant_persona=self.officiant_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[self.dead_sheet],
            location_profile=self.location,
        )

    def test_account_can_accept_own_retired_character_offer(self) -> None:
        from actions.definitions.ceremonies import RespondSeanceOfferAction

        ceremony = self._open_seance()
        offer = ceremony.honorees.get(honoree_sheet=self.dead_sheet).seance_offer

        result = RespondSeanceOfferAction().run(
            actor=None, account=self.player_data.account, offer_id=offer.pk, accept=True
        )

        self.assertTrue(result.success)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "accepted")

    def test_missing_offer_id_fails_cleanly(self) -> None:
        from actions.definitions.ceremonies import RespondSeanceOfferAction

        result = RespondSeanceOfferAction().run(
            actor=None, account=self.player_data.account, offer_id=None, accept=True
        )

        self.assertFalse(result.success)


class GhostWindowSeanceContainerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.vitals.constants import CharacterLifeState

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        cls.seance_room = _make_room("Seance Room")
        cls.location = RoomProfileFactory(objectdb=cls.seance_room)

        officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=officiant_sheet)
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)
        cls.officiant_persona = officiant_sheet.primary_persona

        cls.dead_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=cls.dead_sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now() - timezone.timedelta(days=30),
        )
        cls.ghost = cls.dead_sheet.character

    def test_ghost_may_emit_during_open_accepted_seance(self) -> None:
        from world.ceremonies.services import open_ceremony, respond_to_seance_offer

        ceremony = open_ceremony(
            officiant_persona=self.officiant_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[self.dead_sheet],
            location_profile=self.location,
        )
        offer = ceremony.honorees.get(honoree_sheet=self.dead_sheet).seance_offer
        account = _make_account_for(self.dead_sheet)
        respond_to_seance_offer(offer, account=account, accept=True)

        # Fetch the ghost fresh rather than reusing `self.ghost`: Django's
        # `TestCase.setUpTestData` hands out `copy.deepcopy` snapshots of class-level
        # fixtures on first per-test access (`django.test.testcases.TestData`), so
        # `self.ghost` would carry whatever in-memory `.location` it had *before*
        # `respond_to_seance_offer`'s `move_to` call, not the post-move DB state.
        from evennia.objects.models import ObjectDB

        ghost = ObjectDB.objects.get(pk=self.ghost.pk)
        result = EmitAction().run(actor=ghost, text="A voice from beyond.")

        self.assertTrue(result.success, result.message)

    def test_ghost_cannot_emit_without_accepted_offer(self) -> None:
        from world.ceremonies.services import open_ceremony

        open_ceremony(
            officiant_persona=self.officiant_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[self.dead_sheet],
            location_profile=self.location,
        )
        self.ghost.move_to(self.seance_room, quiet=True)

        result = EmitAction().run(actor=self.ghost, text="Silence.")

        self.assertFalse(result.success)

    def test_ghost_checks_offer_at_own_location_not_merely_the_newest_offer(self) -> None:
        """Regression for the ``_seance_container_open`` location bug (#2393 final review):
        the same honoree can have two ACCEPTED offers open at two different rooms (each
        room ran its own Seance). The query must match the offer at the ACTOR's location,
        not just whichever offer is newest (``SeanceManifestationOffer.Meta.ordering =
        ["-created_at"]`` previously made ``.first()`` pick the newest one regardless of
        where the actor actually stood).
        """
        from evennia.objects.models import ObjectDB

        from world.ceremonies.services import open_ceremony, respond_to_seance_offer

        # First seance: opens and is accepted at self.seance_room (the OLDER offer).
        first_ceremony = open_ceremony(
            officiant_persona=self.officiant_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[self.dead_sheet],
            location_profile=self.location,
        )
        first_offer = first_ceremony.honorees.get(honoree_sheet=self.dead_sheet).seance_offer
        account = _make_account_for(self.dead_sheet)
        respond_to_seance_offer(first_offer, account=account, accept=True)

        # Second seance: a different room, different officiant, honoring the SAME
        # retired sheet, opened and accepted AFTER the first — this is the NEWEST
        # offer by created_at.
        other_room = _make_room("Other Seance Room")
        from evennia_extensions.factories import RoomProfileFactory

        other_location = RoomProfileFactory(objectdb=other_room)
        other_officiant_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=other_officiant_sheet)
        other_being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(
            character_sheet=other_officiant_sheet, public_being=other_being
        )
        second_ceremony = open_ceremony(
            officiant_persona=other_officiant_sheet.primary_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[self.dead_sheet],
            location_profile=other_location,
        )
        second_offer = second_ceremony.honorees.get(honoree_sheet=self.dead_sheet).seance_offer
        respond_to_seance_offer(second_offer, account=account, accept=True)

        # The ghost stands at the FIRST (older) location, not the newest offer's room.
        ghost = ObjectDB.objects.get(pk=self.ghost.pk)
        ghost.move_to(self.seance_room, quiet=True)

        result = EmitAction().run(actor=ghost, text="A voice from the first room.")

        self.assertTrue(result.success, result.message)
