"""GET /api/gm/discovery/: the web face of find_situations (#3564)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import (
    CheckTypeSituationFitFactory,
    ConsequencePoolGuideFactory,
    GMProfileFactory,
    SituationDifficultyGuideFactory,
    SituationKindFactory,
)
from world.gm.services import find_situations
from world.mechanics.factories import ChallengeTemplateFactory, SituationTemplateFactory
from world.scenes.action_constants import DifficultyChoice
from world.societies.constants import RenownRisk


class DiscoveryViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("gm:gm-discovery")
        cls.player = AccountFactory()
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm, level=GMLevel.STARTING)
        cls.staff = AccountFactory(is_staff=True)
        cls.chase = SituationKindFactory(name="Chase", description="Run them down")
        cls.heist = SituationKindFactory(name="Heist", minimum_gm_level=GMLevel.SENIOR)
        cls.sprint = CheckTypeFactory(name="Sprint")
        CheckTypeSituationFitFactory(
            situation_kind=cls.chase, check_type=cls.sprint, fit_notes="footspeed"
        )
        cls.guide = SituationDifficultyGuideFactory(
            situation_kind=cls.chase,
            risk=RenownRisk.HIGH,
            recommended_difficulty=DifficultyChoice.HARD,
            guidance_text="Real stakes",
        )
        cls.pool_guide = ConsequencePoolGuideFactory(situation_kind=cls.chase, is_default=True)
        cls.template = SituationTemplateFactory(name="Rooftop chase", description_template="Tiles")
        cls.challenge = ChallengeTemplateFactory(name="Chase the courier")

    def test_player_is_forbidden(self) -> None:
        self.client.force_authenticate(user=self.player)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_is_rejected(self) -> None:
        self.assertIn(
            self.client.get(self.url).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_gm_gets_the_structured_shape(self) -> None:
        self.client.force_authenticate(user=self.gm)
        response = self.client.get(self.url, {"q": "chase", "risk": RenownRisk.HIGH})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        data = response.data
        self.assertEqual([t["id"] for t in data["templates"]], [self.template.pk])
        self.assertEqual(data["templates"][0]["description_template"], "Tiles")
        self.assertEqual([c["id"] for c in data["challenges"]], [self.challenge.pk])
        self.assertEqual(len(data["kinds"]), 1)
        kind = data["kinds"][0]
        self.assertEqual(kind["id"], self.chase.pk)
        self.assertEqual(kind["name"], "Chase")
        self.assertEqual(kind["minimum_gm_level"], GMLevel.STARTING)
        self.assertEqual(
            kind["check_fits"][0]["check_type"], {"id": self.sprint.pk, "name": "Sprint"}
        )
        self.assertEqual(kind["check_fits"][0]["fit_notes"], "footspeed")
        self.assertEqual(kind["difficulty_guide"]["recommended_difficulty"], DifficultyChoice.HARD)
        self.assertEqual(kind["difficulty_guide"]["guidance_text"], "Real stakes")
        self.assertEqual([g["risk"] for g in kind["all_guides"]], [RenownRisk.HIGH])
        self.assertEqual(kind["pool_guides"][0]["pool"]["id"], self.pool_guide.pool_id)
        self.assertTrue(kind["pool_guides"][0]["is_default"])

    def test_no_risk_gives_null_guide(self) -> None:
        self.client.force_authenticate(user=self.gm)
        kind = self.client.get(self.url, {"q": "chase"}).data["kinds"][0]
        self.assertIsNone(kind["difficulty_guide"])

    def test_empty_query_returns_kinds_only(self) -> None:
        self.client.force_authenticate(user=self.gm)
        data = self.client.get(self.url).data
        self.assertEqual(data["templates"], [])
        self.assertEqual(data["challenges"], [])
        self.assertEqual([k["name"] for k in data["kinds"]], ["Chase"])

    def test_staff_without_profile_browses_at_full_breadth(self) -> None:
        self.client.force_authenticate(user=self.staff)
        data = self.client.get(self.url).data
        self.assertEqual([k["name"] for k in data["kinds"]], ["Chase", "Heist"])

    def test_invalid_risk_is_a_400(self) -> None:
        self.client.force_authenticate(user=self.gm)
        response = self.client.get(self.url, {"risk": "not-a-risk"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_web_and_service_agree(self) -> None:
        self.client.force_authenticate(user=self.gm)
        data = self.client.get(self.url, {"q": "chase"}).data
        found = find_situations(query="chase", risk=None, actor_level_index=0)
        self.assertEqual([k["id"] for k in data["kinds"]], [k.kind.pk for k in found.kinds])
        self.assertEqual([t["id"] for t in data["templates"]], [t.pk for t in found.templates])
