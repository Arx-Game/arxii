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
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatKind,
    BeatPredicateType,
    CustodyClearanceStatus,
    CustodyScope,
    StakeSeverity,
    StakeSubjectKind,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    CustodyClearanceFactory,
    EpisodeFactory,
    StakeFactory,
    StakeResolutionFactory,
    StakeTemplateFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.models import StakeContractActivation

_CUSTODY_STAFF_MESSAGE = (
    "This subject is under another story's custody — request clearance "
    "from the story's GM via staff."
)


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


class StakeResolutionFieldExposureTests(APITestCase):
    """outcome_key and machine_match_lifecycle_state must round-trip via the API.

    Both fields (#1760) were added to the StakeResolution model but never
    added to StakeResolutionSerializer.Meta.fields, so authoring them via the
    API was silently a no-op. This proves they're now reachable.
    """

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory

        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.npc_sheet = CharacterSheetFactory()
        cls.stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=cls.npc_sheet,
            severity=StakeSeverity.GRAVE,
            subject_label="The NPC's fate",
        )

    def test_outcome_key_round_trips_through_create(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.stake.pk,
                "column": "loss",
                "outcome_key": "destroyed",
                "narrative_summary": "It is destroyed.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["outcome_key"], "destroyed")

    def test_machine_match_lifecycle_state_round_trips_through_create(self):
        from world.character_sheets.types import LifecycleState

        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.stake.pk,
                "column": "loss",
                "machine_match_lifecycle_state": LifecycleState.DEAD,
                "narrative_summary": "It matches the dead state.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["machine_match_lifecycle_state"], LifecycleState.DEAD)


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


# ---------------------------------------------------------------------------
# #1770 PR1 final review: ownership must also be checked on BOTH sides of a
# re-point (not just the lock). A user who owns only the old target, or only
# the new target, must be rejected either way; staff may re-point across
# foreign targets freely. Mirrors the RepointLock classes above, but for the
# ownership gate rather than the activation lock.
# ---------------------------------------------------------------------------


class StakeOwnershipRepointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner_a = AccountFactory(is_staff=False)
        cls.owner_b = AccountFactory(is_staff=False)
        cls.story_a = StoryFactory(owners=[cls.owner_a])
        cls.story_b = StoryFactory(owners=[cls.owner_b])
        cls.chapter_a = ChapterFactory(story=cls.story_a)
        cls.chapter_b = ChapterFactory(story=cls.story_b)
        cls.episode_a = EpisodeFactory(chapter=cls.chapter_a)
        cls.episode_b = EpisodeFactory(chapter=cls.chapter_b)
        cls.beat_a = BeatFactory(episode=cls.episode_a, risk=RenownRisk.LOW, target_level=2)
        cls.beat_b = BeatFactory(episode=cls.episode_b, risk=RenownRisk.LOW, target_level=2)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            min_risk=RenownRisk.NONE,
            max_risk=RenownRisk.EXTREME,
        )

    def _stake(self):
        return StakeFactory(
            beat=self.beat_a,
            template=self.template,
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.DIRE,
            subject_label="Wager A",
        )

    def test_owner_of_old_beat_only_cannot_repoint(self):
        stake = self._stake()
        self.client.force_authenticate(user=self.owner_a)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": stake.pk}),
            {"beat": self.beat_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission", str(resp.data).lower())

    def test_owner_of_new_beat_only_cannot_repoint(self):
        """Owning only the incoming beat is rejected too — but earlier than the
        serializer: DRF calls has_object_permission against the CURRENT (old)
        object on PATCH, so IsStakeBeatStoryOwnerOrStaff denies with 403 before
        validate()'s re-point check ever runs.
        """
        stake = self._stake()
        self.client.force_authenticate(user=self.owner_b)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": stake.pk}),
            {"beat": self.beat_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("permission", str(resp.data).lower())

    def test_staff_can_repoint_across_foreign_beats(self):
        stake = self._stake()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": stake.pk}),
            {"beat": self.beat_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class StakeResolutionOwnershipRepointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner_a = AccountFactory(is_staff=False)
        cls.owner_b = AccountFactory(is_staff=False)
        cls.story_a = StoryFactory(owners=[cls.owner_a])
        cls.story_b = StoryFactory(owners=[cls.owner_b])
        cls.chapter_a = ChapterFactory(story=cls.story_a)
        cls.chapter_b = ChapterFactory(story=cls.story_b)
        cls.episode_a = EpisodeFactory(chapter=cls.chapter_a)
        cls.episode_b = EpisodeFactory(chapter=cls.chapter_b)
        cls.beat_a = BeatFactory(episode=cls.episode_a, risk=RenownRisk.LOW, target_level=2)
        cls.beat_b = BeatFactory(episode=cls.episode_b, risk=RenownRisk.LOW, target_level=2)
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

    def _resolution(self):
        return StakeResolutionFactory(
            stake=self.stake_a, column="win", narrative_summary="Fine so far."
        )

    def test_owner_of_old_stake_only_cannot_repoint(self):
        resolution = self._resolution()
        self.client.force_authenticate(user=self.owner_a)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"stake": self.stake_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission", str(resp.data).lower())

    def test_owner_of_new_stake_only_cannot_repoint(self):
        """Owning only the incoming stake is rejected too — but earlier than the
        serializer: DRF calls has_object_permission against the CURRENT (old)
        object on PATCH, so IsStakeResolutionBeatStoryOwnerOrStaff denies with
        403 before validate()'s re-point check ever runs.
        """
        resolution = self._resolution()
        self.client.force_authenticate(user=self.owner_b)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"stake": self.stake_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("permission", str(resp.data).lower())

    def test_staff_can_repoint_across_foreign_stakes(self):
        resolution = self._resolution()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"stake": self.stake_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class BeatOwnershipRepointTests(APITestCase):
    """#1770 review fold-in: Beat's episode re-point shares the same ownership
    gate shape as Stake/StakeResolution — no activation lock applies to Beat
    itself, so this covers ownership only.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner_a = AccountFactory(is_staff=False)
        cls.owner_b = AccountFactory(is_staff=False)
        cls.story_a = StoryFactory(owners=[cls.owner_a])
        cls.story_b = StoryFactory(owners=[cls.owner_b])
        cls.chapter_a = ChapterFactory(story=cls.story_a)
        cls.chapter_b = ChapterFactory(story=cls.story_b)
        cls.episode_a = EpisodeFactory(chapter=cls.chapter_a)
        cls.episode_b = EpisodeFactory(chapter=cls.chapter_b)

    def _beat(self):
        return BeatFactory(episode=self.episode_a, risk=RenownRisk.NONE, target_level=1)

    def test_owner_of_old_episode_only_cannot_repoint(self):
        beat = self._beat()
        self.client.force_authenticate(user=self.owner_a)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat.pk}),
            {"episode": self.episode_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission", str(resp.data).lower())

    def test_owner_of_new_episode_only_cannot_repoint(self):
        """Owning only the incoming episode is rejected too — but earlier than
        the serializer: DRF calls has_object_permission against the CURRENT
        (old) object on PATCH, so IsBeatStoryOwnerOrStaff denies with 403
        before validate()'s re-point check ever runs.
        """
        beat = self._beat()
        self.client.force_authenticate(user=self.owner_b)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat.pk}),
            {"episode": self.episode_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("permission", str(resp.data).lower())

    def test_staff_can_repoint_across_foreign_episodes(self):
        beat = self._beat()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat.pk}),
            {"episode": self.episode_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


# ---------------------------------------------------------------------------
# #2001 Task 4: custody enforcement at stake authoring + writer fire time.
# ---------------------------------------------------------------------------


class StakeAuthoringCustodyGateTests(APITestCase):
    """StakeSerializer.validate's APPEAR-scope custody gate (#2001 Task 4)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory(is_staff=False)
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.npc_sheet = CharacterSheetFactory()
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.NPC_FATE,
            severity=StakeSeverity.GRAVE,
            min_risk=RenownRisk.NONE,
            max_risk=RenownRisk.EXTREME,
        )

    def _payload(self):
        return {
            "beat": self.beat.pk,
            "template": self.template.pk,
            "subject_sheet": self.npc_sheet.pk,
            "player_summary": "The NPC's fate hangs in the balance.",
        }

    def test_allowed_when_subject_not_protected(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_blocked_when_subject_protected_by_another_story(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_message_names_custodian_gm_when_known(self):
        gm_profile = GMProfileFactory()
        table = GMTableFactory(gm=gm_profile)
        other_story = StoryFactory()
        other_story.primary_table = table
        other_story.save(update_fields=["primary_table"])
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        expected = (
            "This subject is under another story's custody — request clearance "
            f"from GM {gm_profile.account.username}."
        )
        self.assertIn(expected, str(resp.data))

    def test_own_story_protection_never_blocks(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_participant_in_protecting_story_allowed(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        owner_sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=owner_sheet)
        player_data = PlayerDataFactory(account=self.owner)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        StoryParticipationFactory(story=other_story, character=owner_sheet.character)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_granted_appear_clearance_allows(self):
        other_story = StoryFactory()
        protection = StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        owner_gm_profile = GMProfileFactory(account=self.owner)
        CustodyClearanceFactory(
            protected_subject=protection,
            requested_by=owner_gm_profile,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_revoked_clearance_no_longer_allows(self):
        from django.utils import timezone

        other_story = StoryFactory()
        protection = StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        owner_gm_profile = GMProfileFactory(account=self.owner)
        CustodyClearanceFactory(
            protected_subject=protection,
            requested_by=owner_gm_profile,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
            revoked_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_staff_bypasses_custody_block(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("stake-list"), self._payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class StakeAuthoringCustodyPatchTests(APITestCase):
    """PATCH-path merge-to-instance fallback in ``_candidate_subject_identity`` (#2001 Task 4).

    ``StakeAuthoringCustodyGateTests`` only exercises the create path, where
    ``self.instance`` is always None and every field comes straight out of
    attrs. A partial update takes the other branch of ``_candidate_subject_identity``'s
    ``merged()`` helper — fields absent from attrs must fall back to the
    existing row rather than silently resolving to ``None``/unprotected.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.NPC_FATE,
            severity=StakeSeverity.GRAVE,
            min_risk=RenownRisk.NONE,
            max_risk=RenownRisk.EXTREME,
        )
        cls.protected_sheet = CharacterSheetFactory()
        cls.other_protected_sheet = CharacterSheetFactory()

        cls.protecting_story = StoryFactory()
        gm_profile_a = GMProfileFactory()
        table_a = GMTableFactory(gm=gm_profile_a)
        cls.protecting_story.primary_table = table_a
        cls.protecting_story.save(update_fields=["primary_table"])
        StoryProtectedSubjectFactory(story=cls.protecting_story, subject_sheet=cls.protected_sheet)
        cls.custodian_a_username = gm_profile_a.account.username

        cls.other_protecting_story = StoryFactory()
        gm_profile_b = GMProfileFactory()
        table_b = GMTableFactory(gm=gm_profile_b)
        cls.other_protecting_story.primary_table = table_b
        cls.other_protecting_story.save(update_fields=["primary_table"])
        StoryProtectedSubjectFactory(
            story=cls.other_protecting_story, subject_sheet=cls.other_protected_sheet
        )
        cls.custodian_b_username = gm_profile_b.account.username

        cls.stake = StakeFactory(
            beat=cls.beat,
            template=cls.template,
            subject_kind=StakeSubjectKind.NPC_FATE,
            severity=StakeSeverity.GRAVE,
            subject_sheet=cls.protected_sheet,
            subject_label="",
            player_summary="The NPC's fate hangs in the balance.",
        )

    def test_patch_unrelated_field_still_blocked_via_instance_identity(self):
        """attrs carries no subject fields — identity must fall back to the instance's row."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": self.stake.pk}),
            {"player_summary": "Edited summary only."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        expected = (
            "This subject is under another story's custody — request clearance "
            f"from GM {self.custodian_a_username}."
        )
        self.assertIn(expected, str(resp.data))

    def test_patch_repoint_subject_sheet_blocked_via_attrs_identity(self):
        """Re-pointing subject_sheet must derive the identity from attrs, not the stale instance.

        Both the original and the re-pointed sheet are protected, but by
        DIFFERENT stories with distinct named custodians — the blocked
        message must name the re-pointed sheet's custodian (story B), not
        the original row's (story A), proving the identity came from attrs.
        """
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            reverse("stake-detail", kwargs={"pk": self.stake.pk}),
            {"subject_sheet": self.other_protected_sheet.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        expected = (
            "This subject is under another story's custody — request clearance "
            f"from GM {self.custodian_b_username}."
        )
        self.assertIn(expected, str(resp.data))


class StakeResolutionWriterCustodyGateTests(APITestCase):
    """StakeResolutionSerializer.validate's HARM/REMOVE re-check (#2001 Task 4)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory(is_staff=False)
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.npc_sheet = CharacterSheetFactory()
        cls.npc_stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.NPC_FATE,
            severity=StakeSeverity.GRAVE,
            subject_sheet=cls.npc_sheet,
            subject_label="",
        )
        cls.item = ItemInstanceFactory(template=ItemTemplateFactory())
        cls.item_stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.ITEM,
            severity=StakeSeverity.GRAVE,
            subject_item=cls.item,
            subject_label="",
        )

    def test_appear_only_writer_not_rechecked_even_if_protected(self):
        """No writer raises the scope past APPEAR, already covered at authoring."""
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "win",
                "narrative_summary": "It goes well.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_harm_writer_blocked_when_protected(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "loss",
                "narrative_summary": "It goes badly.",
                "subject_standing_delta": -2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_win_column_with_pool_and_delta_still_derives_harm(self):
        """The delta branch has no column gate (#2001 Task 4 review).

        A WIN-column resolution carrying a consequence_pool would NOT alone
        raise the scope past APPEAR (``column == LOSS and consequence_pool
        is not None`` requires LOSS) — but a nonzero subject_standing_delta
        raises it to HARM regardless of column, so the combination must
        still be blocked.
        """
        from actions.factories import ConsequencePoolFactory

        pool = ConsequencePoolFactory()
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "win",
                "narrative_summary": "It goes well, mostly.",
                "consequence_pool": pool.pk,
                "subject_standing_delta": -2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_remove_writer_blocked_for_lifecycle_when_protected(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "loss",
                "narrative_summary": "It ends badly.",
                "sets_subject_lifecycle": "DEAD",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_remove_writer_blocked_for_forfeit_when_protected(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(
            story=other_story,
            subject_kind=StakeSubjectKind.ITEM,
            subject_sheet=None,
            subject_item=self.item,
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.item_stake.pk,
                "column": "loss",
                "narrative_summary": "It is lost.",
                "forfeits_subject_item": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_harm_writer_allowed_with_granted_clearance(self):
        other_story = StoryFactory()
        protection = StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        owner_gm_profile = GMProfileFactory(account=self.owner)
        CustodyClearanceFactory(
            protected_subject=protection,
            requested_by=owner_gm_profile,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "loss",
                "narrative_summary": "It goes badly.",
                "subject_standing_delta": -2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_appear_clearance_insufficient_for_remove_writer(self):
        """A clearance at a weaker scope than the writer needs still blocks."""
        other_story = StoryFactory()
        protection = StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        owner_gm_profile = GMProfileFactory(account=self.owner)
        CustodyClearanceFactory(
            protected_subject=protection,
            requested_by=owner_gm_profile,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "loss",
                "narrative_summary": "It ends badly.",
                "sets_subject_lifecycle": "DEAD",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_staff_bypasses_writer_custody_block(self):
        other_story = StoryFactory()
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)

        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {
                "stake": self.npc_stake.pk,
                "column": "loss",
                "narrative_summary": "It goes badly.",
                "subject_standing_delta": -2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class StakeResolutionWriterCustodyPatchTests(APITestCase):
    """PATCH-path merge-to-instance fallback in ``_writer_payload_scope`` (#2001 Task 4 review).

    ``StakeResolutionWriterCustodyGateTests`` only exercises the create path.
    A partial update on an EXISTING no-writer resolution must still re-derive
    the writer-payload scope from the merged (attrs + instance) payload and
    re-check custody when that PATCH alone raises the reach past APPEAR.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode, risk=RenownRisk.LOW, target_level=2)
        cls.npc_sheet = CharacterSheetFactory()
        cls.npc_stake = StakeFactory(
            beat=cls.beat,
            template=None,
            subject_kind=StakeSubjectKind.NPC_FATE,
            severity=StakeSeverity.GRAVE,
            subject_sheet=cls.npc_sheet,
            subject_label="",
        )
        cls.other_story = StoryFactory()
        cls.protection = StoryProtectedSubjectFactory(
            story=cls.other_story, subject_sheet=cls.npc_sheet
        )

    def test_outsider_patch_to_standing_delta_blocked_at_harm(self):
        """A no-writer resolution PATCHed to a HARM payload re-checks custody and blocks."""
        resolution = StakeResolutionFactory(
            stake=self.npc_stake, column="win", narrative_summary="Fine so far."
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"subject_standing_delta": -2},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(_CUSTODY_STAFF_MESSAGE, str(resp.data))

    def test_cleared_user_patch_to_standing_delta_allowed(self):
        """The same recheck ALLOWS once a HARM-scope clearance covers the acting GM."""
        resolution = StakeResolutionFactory(
            stake=self.npc_stake, column="win", narrative_summary="Fine so far."
        )
        owner_gm_profile = GMProfileFactory(account=self.owner)
        CustodyClearanceFactory(
            protected_subject=self.protection,
            requested_by=owner_gm_profile,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            reverse("stakeresolution-detail", kwargs={"pk": resolution.pk}),
            {"subject_standing_delta": -2},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
