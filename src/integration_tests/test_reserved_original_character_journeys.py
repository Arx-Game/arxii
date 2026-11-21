"""Journeys for an original character reserved to its creator (#3055, ADR-3055).

The beta cutover leaves each player's original character on the Available shelf with its
tenure ended. Only the account that created it may take it up again, and that has to hold
on every way a player gets seated: the player's own apply request, the staff review queue,
the GM application queue and the admin action. A rival application filed before the
cutover is the dangerous one, because nothing stopped it being created, so each approval
path is shown refusing it and accepting the creator's own application for the same kind of
character. Every request goes through the real endpoint or the real admin changelist.
"""

from __future__ import annotations

from django.test import Client
from django.urls import reverse
from rest_framework import status

from evennia_extensions.factories import AccountFactory, EmailAddressFactory
from integration_tests.harness import JourneyCase
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication, RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType
from world.stories.factories import StoryFactory
from world.stories.models import StoryParticipation

RESERVED_CODE = "reserved_for_creator"
RESERVED_WORDS = "reserved for the player who created it"
APPLICATION_TEXT = "I would like to play this character because they seem interesting."


class ReservedOriginalCharacterJourneys(JourneyCase):
    """Ysmay made an original character; Corin tries to take it up on every path."""

    @classmethod
    def setUpTestData(cls) -> None:
        RosterFactory(roster_type=RosterType.AVAILABLE)
        RosterFactory(roster_type=RosterType.ACTIVE)
        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        cls.staff_data = PlayerDataFactory(account=cls.staff)
        cls.rival = AccountFactory()
        cls.rival_data = PlayerDataFactory(account=cls.rival)
        EmailAddressFactory(user=cls.rival, email=cls.rival.email, verified=True, primary=True)

    # -- helpers --------------------------------------------------------------

    def _creator(self):
        creator = AccountFactory()
        data = PlayerDataFactory(account=creator)
        EmailAddressFactory(user=creator, email=creator.email, verified=True, primary=True)
        return creator, data

    def _original_character(self, creator) -> RosterEntry:
        """An original character reserved to ``creator``, back on the Available shelf."""
        return RosterEntryFactory(
            roster=RosterFactory(roster_type=RosterType.AVAILABLE),
            creation_provenance=CreationProvenance.PLAYER,
            created_by_account=creator,
        )

    def _applications(self, entry, creator_data) -> tuple[RosterApplication, RosterApplication]:
        """The rival's application (filed before the reservation) and the creator's own."""
        sheet = entry.character_sheet
        return (
            RosterApplicationFactory(player_data=self.rival_data, character=sheet),
            RosterApplicationFactory(player_data=creator_data, character=sheet),
        )

    def _holders(self, entry) -> set[int]:
        return set(
            RosterTenure.objects.filter(roster_entry=entry, end_date__isnull=True).values_list(
                "player_data_id", flat=True
            )
        )

    def _status(self, application) -> str:
        return RosterApplication.objects.values_list("status", flat=True).get(pk=application.pk)

    # -- journeys -------------------------------------------------------------

    def test_only_the_creator_can_apply(self) -> None:
        creator, creator_data = self._creator()
        entry = self._original_character(creator)

        rival_view = self.api(self.rival).get(f"/api/roster/entries/{entry.pk}/")
        refused = self.api(self.rival).post(
            f"/api/roster/entries/{entry.pk}/apply/", {"message": APPLICATION_TEXT}, format="json"
        )
        creator_view = self.api(creator).get(f"/api/roster/entries/{entry.pk}/")
        accepted = self.api(creator).post(
            f"/api/roster/entries/{entry.pk}/apply/", {"message": APPLICATION_TEXT}, format="json"
        )

        self.assertEqual(rival_view.status_code, status.HTTP_200_OK, rival_view.content)
        self.assertFalse(rival_view.json()["can_apply"])
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn(RESERVED_CODE, refused.content.decode())
        self.assertTrue(creator_view.json()["can_apply"])
        self.assertEqual(accepted.status_code, status.HTTP_204_NO_CONTENT, accepted.content)
        self.assertEqual(
            list(
                RosterApplication.objects.filter(character_id=entry.character_sheet_id).values_list(
                    "player_data_id", flat=True
                )
            ),
            [creator_data.pk],
        )

    def test_the_staff_review_queue_refuses_the_rival_and_seats_the_creator(self) -> None:
        creator, creator_data = self._creator()
        entry = self._original_character(creator)
        rival_app, creator_app = self._applications(entry, creator_data)
        staff_api = self.api(self.staff)

        refused = staff_api.post(
            f"/api/roster/applications/{rival_app.pk}/review/", {"action": "approve"}, format="json"
        )
        accepted = staff_api.post(
            f"/api/roster/applications/{creator_app.pk}/review/",
            {"action": "approve"},
            format="json",
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn(RESERVED_CODE, refused.content.decode())
        self.assertEqual(self._status(rival_app), ApplicationStatus.PENDING)
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)
        self.assertEqual(self._status(creator_app), ApplicationStatus.APPROVED)
        self.assertEqual(self._holders(entry), {creator_data.pk})

    def test_the_gm_queue_refuses_the_rival_and_seats_the_creator(self) -> None:
        creator, creator_data = self._creator()
        entry = self._original_character(creator)
        rival_app, creator_app = self._applications(entry, creator_data)
        gm = GMProfileFactory()
        PlayerDataFactory(account=gm.account)
        StoryParticipation.objects.create(
            story=StoryFactory(primary_table=GMTableFactory(gm=gm)),
            character=entry.character_sheet,
            is_active=True,
        )
        gm_api = self.api(gm.account)

        refused = gm_api.post(f"/api/gm/queue/{rival_app.pk}/approve/", {}, format="json")
        accepted = gm_api.post(f"/api/gm/queue/{creator_app.pk}/approve/", {}, format="json")

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn(RESERVED_CODE, refused.content.decode())
        self.assertEqual(self._status(rival_app), ApplicationStatus.PENDING)
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)
        self.assertEqual(self._holders(entry), {creator_data.pk})

    def test_the_admin_action_refuses_the_rival_and_seats_the_creator(self) -> None:
        creator, creator_data = self._creator()
        entry = self._original_character(creator)
        rival_app, creator_app = self._applications(entry, creator_data)
        admin = Client()
        admin.force_login(self.staff)
        url = reverse("admin:arxii_rosterapplication_changelist")

        def approve(application) -> str:
            response = admin.post(
                url,
                {"action": "approve_applications", "_selected_action": [application.pk]},
                follow=True,
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return " ".join(str(message) for message in response.context["messages"])

        refused = approve(rival_app)
        accepted = approve(creator_app)

        self.assertIn(RESERVED_WORDS, refused)
        self.assertIn("Approved 0 applications", refused)
        self.assertEqual(self._status(rival_app), ApplicationStatus.PENDING)
        self.assertIn("Approved 1 applications", accepted)
        self.assertEqual(self._holders(entry), {creator_data.pk})
