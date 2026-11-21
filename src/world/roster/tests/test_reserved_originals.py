"""An original character is reserved to its creator on every path that seats a player (#3055)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterFactory,
)
from world.roster.models import ApplicationStatus, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.serializers import RosterEntrySerializer
from world.roster.services.activity import ReservedForCreatorError


class ReservedOriginalTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.creator = AccountFactory()
        cls.creator_data = PlayerDataFactory(account=cls.creator)
        cls.rival = AccountFactory()
        cls.rival_data = PlayerDataFactory(account=cls.rival)
        cls.staff_data = PlayerDataFactory(account=AccountFactory(is_staff=True))
        cls.original = RosterEntryFactory(
            roster=RosterFactory(roster_type=RosterType.AVAILABLE),
            creation_provenance=CreationProvenance.PLAYER,
            created_by_account=cls.creator,
        )
        cls.roster_character = RosterEntryFactory(
            roster=RosterFactory(roster_type=RosterType.AVAILABLE),
            creation_provenance=CreationProvenance.STAFF,
        )
        RosterFactory(roster_type=RosterType.ACTIVE)

    def test_approving_a_rival_application_is_refused_and_changes_nothing(self) -> None:
        # Filed before the reservation began: nothing stopped it being created.
        application = RosterApplicationFactory(
            player_data=self.rival_data, character=self.original.character_sheet
        )

        with self.assertRaises(ReservedForCreatorError):
            application.approve(self.staff_data)

        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.assertFalse(RosterTenure.objects.filter(roster_entry=self.original).exists())

    def test_the_creator_and_a_roster_character_applicant_are_approved(self) -> None:
        mine = RosterApplicationFactory(
            player_data=self.creator_data, character=self.original.character_sheet
        )
        open_to_all = RosterApplicationFactory(
            player_data=self.rival_data, character=self.roster_character.character_sheet
        )

        self.assertTrue(mine.approve(self.staff_data))
        self.assertTrue(open_to_all.approve(self.staff_data))

    def test_can_apply_is_false_for_everyone_but_the_creator(self) -> None:
        def can_apply(account, entry) -> bool:
            class Request:
                user = account

            return RosterEntrySerializer(entry, context={"request": Request()}).data["can_apply"]

        self.assertTrue(can_apply(self.creator, self.original))
        self.assertFalse(can_apply(self.rival, self.original))
        self.assertTrue(can_apply(self.rival, self.roster_character))
