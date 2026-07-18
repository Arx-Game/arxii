"""Tests for the staff-contact petition system (#2288)."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.player_submissions.constants import (
    PetitionCategory,
    SubmissionCategory,
    SubmissionStatus,
)
from world.player_submissions.factories import PetitionFactory, PlayerFeedbackFactory
from world.player_submissions.models import Petition, SubmitterStanding
from world.player_submissions.services import (
    StaffContactError,
    kudos_total_for,
    resolve_petition,
    sender_context,
    set_ignored,
    standing_for,
    submit_petition,
)
from world.staff_inbox.services import get_staff_inbox


class SubmitPetitionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="petitioner")

    def test_submit_creates_open_petition(self) -> None:
        petition = submit_petition(
            self.account,
            category=PetitionCategory.OTHER_EMERGENCY,
            description="Everything is on fire.",
        )
        self.assertEqual(petition.status, SubmissionStatus.OPEN)
        self.assertEqual(petition.account, self.account)

    def test_one_open_petition_per_account(self) -> None:
        PetitionFactory(account=self.account)
        with self.assertRaises(StaffContactError):
            submit_petition(
                self.account,
                category=PetitionCategory.OTHER_EMERGENCY,
                description="Second emergency.",
            )

    def test_resolved_petition_frees_the_slot(self) -> None:
        PetitionFactory(account=self.account, status=SubmissionStatus.REVIEWED)
        petition = submit_petition(
            self.account,
            category=PetitionCategory.OTHER_EMERGENCY,
            description="New emergency.",
        )
        self.assertEqual(Petition.objects.filter(account=self.account).count(), 2)
        self.assertEqual(petition.status, SubmissionStatus.OPEN)

    def test_category_requires_reference(self) -> None:
        with self.assertRaises(StaffContactError):
            submit_petition(
                self.account,
                category=PetitionCategory.UNFAIR_DEATH,
                description="My character died unfairly.",
            )

    def test_category_reference_satisfied(self) -> None:
        character = CharacterFactory(db_key="DeadGuy")
        petition = submit_petition(
            self.account,
            category=PetitionCategory.UNFAIR_DEATH,
            description="My character died unfairly.",
            subject_character=character,
        )
        self.assertEqual(petition.subject_character, character)

    def test_description_truncated_to_limit(self) -> None:
        petition = submit_petition(
            self.account,
            category=PetitionCategory.OTHER_EMERGENCY,
            description="x" * 2000,
        )
        self.assertEqual(len(petition.description), 1000)


class StandingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="tracked")

    def test_resolve_reviewed_stamps_actioned(self) -> None:
        petition = PetitionFactory(account=self.account)
        resolve_petition(petition, status=SubmissionStatus.REVIEWED, staff_notes="handled")
        standing = standing_for(self.account)
        self.assertEqual(standing.actioned_count, 1)
        self.assertEqual(standing.dismissed_count, 0)
        petition.refresh_from_db()
        self.assertEqual(petition.status, SubmissionStatus.REVIEWED)
        self.assertIsNotNone(petition.resolved_at)

    def test_resolve_dismissed_stamps_dismissed(self) -> None:
        petition = PetitionFactory(account=self.account)
        resolve_petition(petition, status=SubmissionStatus.DISMISSED)
        standing = standing_for(self.account)
        self.assertEqual(standing.dismissed_count, 1)

    def test_resolve_twice_rejected(self) -> None:
        petition = PetitionFactory(account=self.account)
        resolve_petition(petition, status=SubmissionStatus.REVIEWED)
        with self.assertRaises(StaffContactError):
            resolve_petition(petition, status=SubmissionStatus.DISMISSED)

    def test_set_ignored_flips_bit_and_counts(self) -> None:
        standing = set_ignored(self.account, ignored=True)
        self.assertTrue(standing.is_ignored)
        self.assertEqual(standing.ignored_count, 1)
        standing = set_ignored(self.account, ignored=False)
        self.assertFalse(standing.is_ignored)
        self.assertEqual(standing.ignored_count, 1)

    def test_kudos_total_defaults_to_zero(self) -> None:
        self.assertEqual(kudos_total_for(self.account), 0)

    def test_sender_context_shape(self) -> None:
        set_ignored(self.account, ignored=True)
        ctx = sender_context(self.account)
        self.assertEqual(ctx["kudos_total"], 0)
        self.assertTrue(ctx["is_ignored"])
        self.assertIn("actioned_count", ctx)
        self.assertIn("dismissed_count", ctx)


class StaffInboxPetitionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sender = AccountFactory(username="urgent")
        cls.ignored_sender = AccountFactory(username="cried_wolf")
        SubmitterStanding.objects.create(account=cls.ignored_sender, is_ignored=True)
        cls.petition = PetitionFactory(account=cls.sender)
        cls.ignored_petition = PetitionFactory(account=cls.ignored_sender)

    def test_open_petitions_surface_with_sender_context(self) -> None:
        items = get_staff_inbox(categories=[SubmissionCategory.PETITION])
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.source_pk, self.petition.pk)
        self.assertIsNotNone(item.sender_context)
        self.assertEqual(item.sender_context["kudos_total"], 0)

    def test_ignored_sender_excluded_by_default(self) -> None:
        items = get_staff_inbox(categories=[SubmissionCategory.PETITION])
        pks = {i.source_pk for i in items}
        self.assertNotIn(self.ignored_petition.pk, pks)

    def test_include_ignored_reveals(self) -> None:
        items = get_staff_inbox(
            categories=[SubmissionCategory.PETITION],
            include_ignored=True,
        )
        pks = {i.source_pk for i in items}
        self.assertIn(self.ignored_petition.pk, pks)
        revealed = next(i for i in items if i.source_pk == self.ignored_petition.pk)
        self.assertTrue(revealed.sender_context["is_ignored"])

    def test_resolved_petitions_do_not_surface(self) -> None:
        resolve_petition(self.petition, status=SubmissionStatus.REVIEWED)
        items = get_staff_inbox(categories=[SubmissionCategory.PETITION])
        self.assertEqual(items, [])


class PetitionViewSetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = AccountFactory(username="vsplayer")
        cls.other = AccountFactory(username="vsother")
        cls.staff = AccountFactory(username="vsstaff", is_staff=True)

    def _client(self, account) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_create_files_petition(self) -> None:
        response = self._client(self.player).post(
            "/api/player-submissions/petitions/",
            {
                "category": PetitionCategory.OTHER_EMERGENCY,
                "description": "Emergency!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        petition = Petition.objects.get()
        self.assertEqual(petition.account, self.player)

    def test_create_second_open_rejected_with_safe_message(self) -> None:
        PetitionFactory(account=self.player)
        response = self._client(self.player).post(
            "/api/player-submissions/petitions/",
            {
                "category": PetitionCategory.OTHER_EMERGENCY,
                "description": "Another emergency!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("open petition", response.data["detail"])

    def test_list_scopes_to_own_petitions(self) -> None:
        mine = PetitionFactory(account=self.player)
        PetitionFactory(account=self.other)
        response = self._client(self.player).get("/api/player-submissions/petitions/")
        self.assertEqual(response.status_code, 200)
        pks = [row["id"] for row in response.data["results"]]
        self.assertEqual(pks, [mine.pk])

    def test_staff_sees_all(self) -> None:
        PetitionFactory(account=self.player)
        PetitionFactory(account=self.other)
        response = self._client(self.staff).get("/api/player-submissions/petitions/")
        self.assertEqual(len(response.data["results"]), 2)

    def test_resolve_requires_staff(self) -> None:
        petition = PetitionFactory(account=self.player)
        response = self._client(self.player).post(
            f"/api/player-submissions/petitions/{petition.pk}/resolve/",
            {"status": SubmissionStatus.REVIEWED},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_resolve_stamps_standing(self) -> None:
        petition = PetitionFactory(account=self.player)
        response = self._client(self.staff).post(
            f"/api/player-submissions/petitions/{petition.pk}/resolve/",
            {"status": SubmissionStatus.DISMISSED, "staff_notes": "not an emergency"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        petition.refresh_from_db()
        self.assertEqual(petition.status, SubmissionStatus.DISMISSED)
        self.assertEqual(standing_for(self.player).dismissed_count, 1)


class FeedbackResolutionStampTests(TestCase):
    """Staff resolving feedback stamps the submitter's track record (#2288)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.reporter = AccountFactory(username="fbreporter")
        cls.staff = AccountFactory(username="fbstaff", is_staff=True)
        cls.feedback = PlayerFeedbackFactory(reporter_account=cls.reporter)

    def test_status_update_stamps_standing(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/player-submissions/feedback/{self.feedback.pk}/",
            {"status": SubmissionStatus.REVIEWED},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(standing_for(self.reporter).actioned_count, 1)


class PetitionStaffContextTests(TestCase):
    """Staff-only sender context + the silent perma-ignore action (#2288)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = AccountFactory(username="ctxplayer")
        cls.staff = AccountFactory(username="ctxstaff", is_staff=True)
        cls.petition = PetitionFactory(account=cls.player)

    def _client(self, account) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_staff_detail_carries_sender_context(self) -> None:
        response = self._client(self.staff).get(
            f"/api/player-submissions/petitions/{self.petition.pk}/"
        )
        self.assertEqual(response.data["sender_context"]["kudos_total"], 0)

    def test_owner_detail_hides_sender_context(self) -> None:
        """The ignore bit must stay silent — owners never see their own standing."""
        response = self._client(self.player).get(
            f"/api/player-submissions/petitions/{self.petition.pk}/"
        )
        self.assertIsNone(response.data["sender_context"])

    def test_ignore_sender_flips_and_reveals_nothing_to_player(self) -> None:
        response = self._client(self.staff).post(
            f"/api/player-submissions/petitions/{self.petition.pk}/ignore-sender/",
            {"ignored": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["sender_context"]["is_ignored"])
        self.assertTrue(SubmitterStanding.objects.get(account=self.player).is_ignored)

    def test_ignore_sender_requires_staff(self) -> None:
        response = self._client(self.player).post(
            f"/api/player-submissions/petitions/{self.petition.pk}/ignore-sender/",
            {"ignored": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
