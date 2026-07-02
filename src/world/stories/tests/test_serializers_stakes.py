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
from world.stories.constants import BeatKind, BeatPredicateType, StakeSeverity, StakeSubjectKind
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StakeResolutionFactory,
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


# ---------------------------------------------------------------------------
# #1770 PR1 review: create-path ownership enforcement (serializer-layer).
#
# DRF never calls has_object_permission on create — IsStakeBeatStoryOwnerOrStaff
# / IsStakeResolutionBeatStoryOwnerOrStaff / IsBeatStoryOwnerOrStaff only require
# authentication at that point. Ownership must be enforced in validate().
# ---------------------------------------------------------------------------


class StakeOwnershipGateTests(APITestCase):
    """Uses a StakeTemplate (not template=None) so the payload never trips the
    unrelated custom-stake staff gate — isolates the ownership check on its own.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner = AccountFactory(is_staff=False)
        cls.non_owner = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            min_risk=RenownRisk.NONE,
            max_risk=RenownRisk.EXTREME,
        )
        cls.stake = StakeFactory(
            beat=cls.beat,
            template=cls.template,
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            subject_label="The town of Erenwold",
        )

    def _stake_payload(self):
        return {
            "beat": self.beat.pk,
            "template": self.template.pk,
            "subject_label": "Another wager",
            "player_summary": "Also at stake.",
        }

    def _resolution_payload(self):
        return {
            "stake": self.stake.pk,
            "column": "win",
            "narrative_summary": "It goes well.",
        }

    def test_non_owner_cannot_create_stake_on_foreign_beat(self):
        self.client.force_authenticate(user=self.non_owner)
        resp = self.client.post(reverse("stake-list"), self._stake_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_create_stake(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._stake_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_staff_can_create_stake_on_foreign_beat(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("stake-list"), self._stake_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_non_owner_cannot_create_resolution_on_foreign_stake(self):
        self.client.force_authenticate(user=self.non_owner)
        resp = self.client.post(
            reverse("stakeresolution-list"), self._resolution_payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_create_resolution(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"), self._resolution_payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_staff_can_create_resolution_on_foreign_stake(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"), self._resolution_payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class BeatOwnershipGateTests(APITestCase):
    """#1770 PR1 review fold-in: BeatSerializer shares the identical create-path hole."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner = AccountFactory(is_staff=False)
        cls.non_owner = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _payload(self):
        return {
            "episode": self.episode.pk,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "kind": BeatKind.SITUATION,
            "advances": True,
            "risk": RenownRisk.NONE,
            "internal_description": "x",
        }

    def test_non_owner_cannot_create_beat_on_foreign_episode(self):
        self.client.force_authenticate(user=self.non_owner)
        resp = self.client.post(reverse("beat-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_create_beat(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("beat-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_staff_can_create_beat_on_foreign_episode(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("beat-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


# ---------------------------------------------------------------------------
# #1770 PR1 review: lock-gate must check BOTH sides on re-point, not just the
# incoming beat/stake.
# ---------------------------------------------------------------------------


class StakeRepointLockTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat_a = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.beat_b = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)

    def test_repoint_from_locked_beat_to_unlocked_beat_rejected(self):
        StakeContractActivation.objects.create(
            beat=self.beat_a,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat_a.risk,
            effective_risk=self.beat_a.risk,
            is_ready=True,
        )
        stake = StakeFactory(
            beat=self.beat_a,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="Wager A",
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": stake.pk}),
            {"beat": self.beat_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())

    def test_repoint_from_unlocked_beat_to_locked_beat_rejected(self):
        StakeContractActivation.objects.create(
            beat=self.beat_b,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat_b.risk,
            effective_risk=self.beat_b.risk,
            is_ready=True,
        )
        stake = StakeFactory(
            beat=self.beat_a,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="Wager A",
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": stake.pk}),
            {"beat": self.beat_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())


class StakeResolutionRepointLockTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat_a = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.beat_b = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.stake_a = StakeFactory(
            beat=cls.beat_a,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="Wager A",
        )
        cls.stake_b = StakeFactory(
            beat=cls.beat_b,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="Wager B",
        )

    def test_repoint_from_locked_stake_to_unlocked_stake_rejected(self):
        StakeContractActivation.objects.create(
            beat=self.beat_a,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat_a.risk,
            effective_risk=self.beat_a.risk,
            is_ready=True,
        )
        resolution = StakeResolutionFactory(
            stake=self.stake_b, column="win", narrative_summary="Fine so far."
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"stake": self.stake_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())

    def test_repoint_from_unlocked_stake_to_locked_stake_rejected(self):
        StakeContractActivation.objects.create(
            beat=self.beat_b,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=self.beat_b.risk,
            effective_risk=self.beat_b.risk,
            is_ready=True,
        )
        resolution = StakeResolutionFactory(
            stake=self.stake_a, column="win", narrative_summary="Fine so far."
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"stake": self.stake_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data).lower())
