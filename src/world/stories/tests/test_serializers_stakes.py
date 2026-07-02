"""Serializer/API tests for the stakes-contract engine (#1770 PR1).

Mirrors test_serializers_beat_risk.py's APITestCase style. Covers the lock
(any write rejected while an open StakeContractActivation exists), the
custom-stake staff gate (template=null path), template risk-banding, and
template-driven subject_kind/severity defaulting.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.societies.constants import RenownRisk
from world.stories.constants import StakeSeverity, StakeSubjectKind
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StakeTemplateFactory,
    StoryFactory,
)
from world.stories.models import StakeContractActivation


class StakeLockTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.staff, cls.player])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="The town of Erenwold",
        )

    def test_update_rejected_while_activation_open(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat.risk,
            effective_risk=self.beat.risk,
            is_ready=True,
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": self.stake.pk}),
            {"player_summary": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())

    def test_update_allowed_without_open_activation(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": self.stake.pk}),
            {"player_summary": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_rejected_while_activation_open(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat.risk,
            effective_risk=self.beat.risk,
            is_ready=True,
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stake-list"),
            {
                "beat": self.beat.pk,
                "subject_kind": StakeSubjectKind.CUSTOM,
                "severity": StakeSeverity.COSTLY,
                "subject_label": "Another wager",
                "player_summary": "Also at stake.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())


class StakeCustomGateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.staff, cls.player])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)

    def _payload(self):
        return {
            "beat": self.beat.pk,
            "subject_kind": StakeSubjectKind.CUSTOM,
            "severity": StakeSeverity.COSTLY,
            "subject_label": "A custom wager",
            "player_summary": "Something dear is wagered.",
        }

    def test_non_staff_cannot_author_custom_stake(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template", resp.data)

    def test_staff_may_author_custom_stake(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["subject_kind"], StakeSubjectKind.CUSTOM)


class StakeTemplateBandingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            min_risk=RenownRisk.HIGH,
            max_risk=RenownRisk.EXTREME,
        )

    def test_template_outside_beat_risk_band_is_rejected(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stake-list"),
            {
                "beat": self.beat.pk,
                "template": self.template.pk,
                "subject_label": "A relic",
                "player_summary": "The relic is at stake.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template", resp.data)


class StakeTemplateDefaultingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            min_risk=RenownRisk.NONE,
            max_risk=RenownRisk.EXTREME,
        )

    def test_subject_kind_and_severity_default_from_template(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stake-list"),
            {
                "beat": self.beat.pk,
                "template": self.template.pk,
                "subject_label": "A relic",
                "player_summary": "The relic is at stake.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["subject_kind"], StakeSubjectKind.ITEM)
        self.assertEqual(resp.data["severity"], StakeSeverity.DIRE)


class StakeResolutionLockTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="The town of Erenwold",
        )

    def test_create_rejected_while_activation_open_via_stake_beat(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat.risk,
            effective_risk=self.beat.risk,
            is_ready=True,
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.stake.pk,
                "column": "win",
                "narrative_summary": "It goes well.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())

    def test_create_allowed_without_open_activation(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.stake.pk,
                "column": "win",
                "narrative_summary": "It goes well.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
