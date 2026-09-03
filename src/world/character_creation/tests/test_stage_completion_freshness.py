"""Reproduction: the stepper's stage badges must reflect the draft as just saved.

A player who completes Origin (and then Heritage) and clicks around the wizard
reported the finished stages still wearing the "incomplete" warning badge. The
badges render from ``CharacterDraftSerializer.stage_completion``, which comes
from ``CharacterDraft.get_stage_validation_errors()``.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import Stage
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    StartingAreaFactory,
)
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin

DRAFTS_URL = "/api/character-creation/drafts/"


class StageCompletionFreshnessTests(TestCase):
    """Each response must report completion for the draft's current state."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.area = StartingAreaFactory(name="Freshness Harbor")
        cls.beginnings = BeginningsFactory(starting_area=cls.area)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_origin_reads_complete_right_after_the_area_is_chosen(self):
        draft = CharacterDraftFactory(account=self.account, selected_area=None)
        detail_url = f"{DRAFTS_URL}{draft.id}/"

        # The player lands on the wizard: Origin is genuinely incomplete.
        first = self.client.get(detail_url)
        assert first.status_code == status.HTTP_200_OK
        assert first.json()["stage_completion"][str(Stage.ORIGIN.value)] is False

        # They pick a starting area — exactly what OriginStage PATCHes.
        patched = self.client.patch(detail_url, {"selected_area_id": self.area.id}, format="json")
        assert patched.status_code == status.HTTP_200_OK
        assert patched.json()["selected_area"]["id"] == self.area.id
        assert patched.json()["stage_completion"][str(Stage.ORIGIN.value)] is True

    def test_origin_still_reads_complete_when_the_player_clicks_around(self):
        draft = CharacterDraftFactory(account=self.account, selected_area=None)
        detail_url = f"{DRAFTS_URL}{draft.id}/"

        self.client.get(detail_url)
        self.client.patch(detail_url, {"selected_area_id": self.area.id}, format="json")

        # Clicking to another stage refetches the draft.
        revisited = self.client.get(detail_url)
        assert revisited.json()["stage_completion"][str(Stage.ORIGIN.value)] is True


class SubmitAfterCompletingLastStageTests(FinalizationTestMixin, APITestCase):
    """The submit gate reads the same completion data the stepper renders."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Freshness Submit", height_min=700, height_max=800)
        cls.account = AccountFactory()

    def test_submit_accepts_a_draft_completed_earlier_in_the_same_session(self) -> None:
        draft = self._create_base_draft(first_name="Aurelius")
        # Roll Appearance back so the player still has one stage left to finish.
        draft.build = None
        draft.save(update_fields=["build"])
        detail_url = f"{DRAFTS_URL}{draft.pk}/"
        self.client.force_authenticate(user=self.account)

        # The player is looking at the wizard with Appearance incomplete.
        looked = self.client.get(detail_url)
        assert looked.json()["stage_completion"][str(Stage.APPEARANCE.value)] is False

        # They finish it.
        patched = self.client.patch(detail_url, {"build_id": self.build.pk}, format="json")
        assert patched.status_code == status.HTTP_200_OK

        # ...and hit submit.
        submitted = self.client.post(
            f"{detail_url}submit/", {"submission_notes": "Ready."}, format="json"
        )
        assert submitted.status_code == status.HTTP_201_CREATED, submitted.content
