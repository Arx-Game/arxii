from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.missions.constants import MissionVisibility
from world.missions.factories import MissionTemplateFactory
from world.societies.constants import RenownRisk
from world.stories.constants import BeatKind, BeatPredicateType
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.models import StakeContractActivation


class BeatRiskGateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.staff, cls.player])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _payload(self, risk):
        return {
            "episode": self.episode.pk,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "kind": BeatKind.SITUATION,
            "advances": True,
            "risk": risk,
            "internal_description": "x",
        }

    def test_non_staff_cannot_author_risk_above_none(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(
            reverse("beat-list"), self._payload(RenownRisk.MODERATE), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_non_staff_may_author_risk_none(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(reverse("beat-list"), self._payload(RenownRisk.NONE), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["kind"], BeatKind.SITUATION)

    def test_staff_may_author_any_risk(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("beat-list"), self._payload(RenownRisk.EXTREME), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["risk"], RenownRisk.EXTREME)

    def _create_beat(self, risk):
        """Staff-authored beat at the given risk (staff may author any risk)."""
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(reverse("beat-list"), self._payload(risk), format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return resp.data["id"]

    def test_non_staff_patch_raising_risk_is_gated(self):
        beat_id = self._create_beat(RenownRisk.NONE)
        self.client.force_authenticate(user=self.player)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"risk": RenownRisk.MODERATE},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_non_staff_patch_unrelated_field_on_risk_none_beat_ok(self):
        # Snapshot-merge carries stored risk=NONE through, so the gate does not fire.
        beat_id = self._create_beat(RenownRisk.NONE)
        self.client.force_authenticate(user=self.player)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"internal_description": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_non_staff_patch_unrelated_field_on_risk_high_beat_is_gated(self):
        # Intentional behavior lock-in: a non-staff owner cannot PATCH ANY
        # field of a staff-authored risk>NONE beat — the snapshot-merge carries
        # the stored risk=EXTREME through, so merged["risk"] != NONE and not
        # is_staff trips the gate even though `risk` was not sent. This 400 is
        # deliberate, not a bug.
        beat_id = self._create_beat(RenownRisk.EXTREME)
        self.client.force_authenticate(user=self.player)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"internal_description": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_staff_patch_raising_risk_is_allowed(self):
        beat_id = self._create_beat(RenownRisk.NONE)
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": beat_id}),
            {"risk": RenownRisk.HIGH},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["risk"], RenownRisk.HIGH)


class BeatRiskGMLevelCapTests(APITestCase):
    """#2000 Task 3: non-staff risk ceiling reads GMLevelCap, not staff-only."""

    @classmethod
    def setUpTestData(cls):
        cls.caps = seed_default_gm_level_caps()
        cls.gm_account = AccountFactory(is_staff=False)
        GMProfileFactory(account=cls.gm_account, level=GMLevel.GM)  # cap: HIGH
        cls.no_profile_account = AccountFactory(is_staff=False)
        cls.story = StoryFactory(owners=[cls.gm_account, cls.no_profile_account])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _payload(self, risk):
        return {
            "episode": self.episode.pk,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "kind": BeatKind.SITUATION,
            "advances": True,
            "risk": risk,
            "internal_description": "x",
        }

    def test_gm_level_can_author_at_its_cap(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.post(reverse("beat-list"), self._payload(RenownRisk.HIGH), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["risk"], RenownRisk.HIGH)

    def test_gm_level_cannot_author_above_its_cap(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.post(
            reverse("beat-list"), self._payload(RenownRisk.EXTREME), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)

    def test_no_gm_profile_still_refused_above_none(self):
        self.client.force_authenticate(user=self.no_profile_account)
        resp = self.client.post(reverse("beat-list"), self._payload(RenownRisk.LOW), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk", resp.data)


class BeatSerializerRequiredMissionCapTests(APITestCase):
    """#3562: non-staff ``required_mission`` is capped to ``scenario_scope_q``.

    A GM may only assign a mission the missions Studio scope already lets
    them author into: their own StoryScenario, or an OPEN template within
    their GM level's risk ceiling. RESTRICTED catalog templates they don't
    own are out of scope regardless of risk tier.
    """

    @classmethod
    def setUpTestData(cls):
        cls.caps = seed_default_gm_level_caps()
        cls.gm_account = AccountFactory(is_staff=False)
        GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.gm_account, cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.restricted_template = MissionTemplateFactory(
            name="beat-cap-restricted", visibility=MissionVisibility.RESTRICTED, risk_tier=1
        )
        cls.open_template = MissionTemplateFactory(
            name="beat-cap-open", visibility=MissionVisibility.OPEN, risk_tier=1
        )

    def setUp(self):
        self.beat = BeatFactory(episode=self.episode, risk=RenownRisk.NONE)

    def test_non_staff_out_of_scope_template_rejected(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": self.beat.pk}),
            {"required_mission": self.restricted_template.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("required_mission", resp.data)

    def test_non_staff_open_template_within_cap_accepted(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": self.beat.pk}),
            {"required_mission": self.open_template.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["required_mission"], self.open_template.pk)

    def test_staff_any_template_accepted(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": self.beat.pk}),
            {"required_mission": self.restricted_template.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)


class BeatSerializerStakeLockTests(APITestCase):
    """#3562: an open StakeContractActivation locks the priced fields on the beat.

    Mirrors ``_check_stake_beat_lock``'s no-staff-bypass posture (the Stake
    lock has none either - a locked contract is locked for everyone until
    resolved), reusing ``_STAKES_LOCKED_MESSAGE``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def setUp(self):
        self.beat = BeatFactory(
            episode=self.episode, risk=RenownRisk.HIGH, target_level=5, agm_eligible=False
        )
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=5,
            declared_target_level=5,
            declared_risk=RenownRisk.HIGH,
            effective_risk=RenownRisk.HIGH,
            is_ready=True,
        )

    def test_patch_risk_locked(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": self.beat.pk}),
            {"risk": RenownRisk.LOW},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("risk", resp.data)

    def test_patch_unrelated_field_ok(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("beat-detail", kwargs={"pk": self.beat.pk}),
            {"internal_description": "still fine to edit"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
