"""Journeys through performing the personal anima ritual (#4451).

A player in a scene performs the ritual they were given at character creation:
on the Rituals page (the web client posts to ``/api/magic/rituals/perform/``)
or by typing ``ritual anima``. The roll rests on the ritual's own check; the
die is pinned (``ROLL_WELL``) because the roll is the one thing a journey
cannot drive and still be a journey.
"""

from __future__ import annotations

from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionInstanceFactory, SoulfrayTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
)
from world.magic.models import CharacterAnima
from world.magic.models.anima import AnimaRitualPerformance
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CheckOutcome

PERFORM_URL = "/api/magic/rituals/perform/"

# A roll of 95 lands in the top band of every chart CheckSystemSetupFactory builds.
ROLL_WELL = patch("world.checks.services.random.randint", return_value=95)


def anima_of(character) -> int:
    """The anima the database holds (``refresh_from_db`` is a no-op on idmapper rows)."""
    return (
        CharacterAnima.objects.filter(character_id=character.pk)
        .values_list("current", flat=True)
        .get()
    )


def severity_of(instance: ConditionInstance) -> int:
    return ConditionInstance.objects.filter(pk=instance.pk).values_list("severity", flat=True).get()


class _AnAnimaRitual(JourneyCase):
    """Ysmay has her anima ritual and stands at a table where a scene is running."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        # Every tier pays out something, so whichever band the pinned roll lands in
        # restores anima (a tier with no authored award would raise).
        for outcome in CheckOutcome.objects.all():
            AnimaRitualBudgetAward.objects.get_or_create(
                outcome_tier=outcome, defaults={"budget": 4}
            )
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)
        CharacterAnimaFactory(character=self.sheet, current=2, maximum=10)
        self.ritual = self.give_ritual(self.ysmay, "Ysmay's Anima Ritual")

    @staticmethod
    def give_ritual(character, name: str):
        ritual = RitualFactory(
            name=name,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=character.db_account,
        )
        RitualCheckConfigFactory(
            ritual=ritual, check_type=CheckTypeFactory(name=f"{name} Check"), target_difficulty=0
        )
        return ritual

    def open_scene(self):
        scene = SceneFactory(room=self.room)
        SceneParticipationFactory(scene=scene, account=self.account_of(self.ysmay))
        return scene


class PerformingItInAScene(_AnAnimaRitual):
    def setUp(self) -> None:
        super().setUp()
        self.scene = self.open_scene()

    def test_she_types_the_verb_and_her_anima_comes_back(self) -> None:
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "ritual anima")
        self.assertIn("You perform Ysmay's Anima Ritual:", told)
        self.assertIn("You recover", told)
        self.assertGreater(anima_of(self.ysmay), 2)
        self.assertTrue(
            AnimaRitualPerformance.objects.filter(ritual=self.ritual, scene=self.scene).exists()
        )

    def test_she_can_also_type_the_rituals_own_name(self) -> None:
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "ritual Ysmay's Anima Ritual")
        self.assertIn("You perform Ysmay's Anima Ritual:", told)

    def test_a_second_try_in_the_same_scene_is_refused(self) -> None:
        with ROLL_WELL:
            self.telnet(self.ysmay, "ritual anima")
        after_first = anima_of(self.ysmay)
        told = self.telnet(self.ysmay, "ritual anima")
        self.assertIn("You've already performed your ritual in this scene.", told)
        self.assertEqual(anima_of(self.ysmay), after_first)

    def test_the_web_client_posts_the_card_and_is_told_the_outcome(self) -> None:
        client = self.api(self.account_of(self.ysmay))
        with ROLL_WELL:
            response = client.post(
                PERFORM_URL,
                {"character_sheet_id": self.sheet.pk, "ritual_id": self.ritual.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("You perform Ysmay's Anima Ritual:", response.data["message"])
        self.assertGreater(response.data["result"]["anima_recovered"], 0)
        self.assertGreater(anima_of(self.ysmay), 2)

    def test_the_web_client_is_refused_the_second_try(self) -> None:
        client = self.api(self.account_of(self.ysmay))
        body = {"character_sheet_id": self.sheet.pk, "ritual_id": self.ritual.pk}
        with ROLL_WELL:
            client.post(PERFORM_URL, body, format="json")
        response = client.post(PERFORM_URL, body, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"], "You've already performed your ritual in this scene."
        )

    def test_soulfray_eases_before_anima_comes_back(self) -> None:
        soulfray = ConditionInstanceFactory(
            target=self.ysmay, condition=SoulfrayTemplateFactory(), severity=3
        )
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "ritual anima")
        self.assertIn("Your Soulfray eases by", told)
        self.assertLess(severity_of(soulfray), 3)

    def test_another_players_ritual_is_not_hers_to_perform(self) -> None:
        hobb = self.make_player("Hobb", room=self.room)
        hobbs = self.give_ritual(hobb, "Hobb's Anima Ritual")
        told = self.telnet(self.ysmay, "ritual Hobb's Anima Ritual")
        self.assertIn("You don't know how to perform 'Hobb's Anima Ritual'.", told)
        client = self.api(self.account_of(self.ysmay))
        response = client.post(
            PERFORM_URL,
            {"character_sheet_id": self.sheet.pk, "ritual_id": hobbs.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=hobbs).exists())


class PerformingItWithNoSceneRunning(_AnAnimaRitual):
    def test_she_is_told_she_cannot_right_now(self) -> None:
        told = self.telnet(self.ysmay, "ritual anima")
        self.assertIn("You cannot perform a ritual right now.", told)
        self.assertEqual(anima_of(self.ysmay), 2)

    def test_a_scene_she_has_not_joined_does_not_count(self) -> None:
        SceneFactory(room=self.room)
        told = self.telnet(self.ysmay, "ritual anima")
        self.assertIn("You cannot perform a ritual right now.", told)


class PerformingItWithNoRitual(JourneyCase):
    def test_she_is_told_she_has_none(self) -> None:
        room = self.make_room("The Lantern")
        hobb = self.make_player("Hobb", room=room)
        told = self.telnet(hobb, "ritual anima")
        self.assertIn("You don't know how to perform 'anima'.", told)
