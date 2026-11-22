"""Journeys through the personal anima ritual, which is never done alone (#5280).

A player in a scene asks someone else to take part in the ritual they were given at character
creation: by typing ``ritual anima <partner>`` or from the persona menu. Every door that names
no one else (the bare verb, the ritual's own name, her own name as the partner, the Rituals page
the web client posts to ``/api/magic/rituals/perform/``) is told to name someone, and nothing
changes for her. Numbers are worked out by hand: a Success pays an anima budget of 4, so Ysmay's
anima goes from 2 to 6.
"""

from __future__ import annotations

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
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
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CheckOutcome
from world.traits.services import ensure_canonical_check_outcome

PERFORM_URL = "/api/magic/rituals/perform/"
NEEDS_A_PARTNER = "Name someone else to take part in your ritual."


def anima_of(character) -> int:
    """The anima the database holds (``refresh_from_db`` is a no-op on idmapper rows)."""
    return (
        CharacterAnima.objects.filter(character_id=character.pk)
        .values_list("current", flat=True)
        .get()
    )


class _AnAnimaRitual(JourneyCase):
    """Ysmay has her anima ritual and stands at a table where a scene is running."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        # Every tier pays out something, so whichever band the dice land in restores anima
        # (a tier with no authored award would raise).
        for outcome in CheckOutcome.objects.all():
            AnimaRitualBudgetAward.objects.get_or_create(
                outcome_tier=outcome, defaults={"budget": 4}
            )
        self.success = ensure_canonical_check_outcome("Success")
        AnimaRitualBudgetAward.objects.get_or_create(
            outcome_tier=self.success, defaults={"budget": 4}
        )
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)
        CharacterAnimaFactory(character=self.sheet, current=2, maximum=10)
        self.ritual = self.give_ritual(self.ysmay, "Ysmay's Anima Ritual")
        self.scene = self.open_scene()

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
            ritual=ritual,
            check_type=CheckTypeFactory(name=f"{name} Check"),
            target_difficulty_level=0,
        )
        return ritual

    def open_scene(self):
        """A live scene at the room, the one everyone standing there is in."""
        scene = SceneFactory(location=RoomProfileFactory(objectdb=self.room), is_active=True)
        invalidate_active_scene_cache(self.room)
        return scene

    def telnet(self, character, line: str) -> str:
        """A typed line, with the after-commit sends it causes run: the private result lines
        are stored narrative messages sent once the transaction commits."""
        with self.captureOnCommitCallbacks(execute=True):
            return super().telnet(character, line)


class TheRitualNeverRunsAlone(_AnAnimaRitual):
    """Every door that names no one else is refused, with her anima where it was."""

    def assert_nothing_happened(self) -> None:
        self.assertEqual(anima_of(self.ysmay), 2)
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=self.ritual).exists())

    def test_the_bare_verb_is_told_to_name_someone_and_given_the_usage(self) -> None:
        with force_check_outcome(self.success):
            told = self.telnet(self.ysmay, "ritual anima")

        self.assertIn(f"{NEEDS_A_PARTNER} Usage: ritual anima <partner>", told)
        self.assert_nothing_happened()

    def test_the_rituals_own_name_is_told_to_name_someone(self) -> None:
        with force_check_outcome(self.success):
            told = self.telnet(self.ysmay, "ritual Ysmay's Anima Ritual")

        self.assertIn(NEEDS_A_PARTNER, told)
        self.assert_nothing_happened()

    def test_her_own_name_as_the_partner_is_told_to_name_someone_else(self) -> None:
        with force_check_outcome(self.success):
            told = self.telnet(self.ysmay, "ritual anima Ysmay")

        self.assertIn(NEEDS_A_PARTNER, told)
        self.assert_nothing_happened()

    def test_the_rituals_page_is_told_the_same(self) -> None:
        client = self.api(self.account_of(self.ysmay))

        with force_check_outcome(self.success):
            response = client.post(
                PERFORM_URL,
                {"character_sheet_id": self.sheet.pk, "ritual_id": self.ritual.pk},
                format="json",
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["detail"], NEEDS_A_PARTNER)
        self.assert_nothing_happened()


class AnotherPlayersRitual(_AnAnimaRitual):
    def test_it_is_not_hers_to_ask_a_partner_for(self) -> None:
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


class PerformingItWithAPartner(_AnAnimaRitual):
    """Ysmay asks Tobin, who is in the room; he agrees and her anima comes back."""

    def setUp(self) -> None:
        super().setUp()
        self.tobin = self.make_player("Tobin", room=self.room)
        for who in (self.ysmay, self.tobin):
            self.watch(who)
            self.connect_telnet(who)

    def test_she_asks_he_accepts_and_her_anima_comes_back(self) -> None:
        asked = self.telnet(self.ysmay, "ritual anima Tobin")

        self.assertIn("You ask Tobin to take part in your ritual.", asked)
        # Nothing has happened until he answers.
        self.assertEqual(anima_of(self.ysmay), 2)
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=self.ritual).exists())

        with force_check_outcome(self.success):
            self.telnet(self.tobin, "accept")

        self.assertEqual(anima_of(self.ysmay), 6)
        performance = AnimaRitualPerformance.objects.get(ritual=self.ritual, scene=self.scene)
        self.assertEqual(performance.target_character, self.tobin.sheet_data)

    def test_a_second_ritual_in_the_same_scene_is_refused(self) -> None:
        self.telnet(self.ysmay, "ritual anima Tobin")
        with force_check_outcome(self.success):
            self.telnet(self.tobin, "accept")

        told = self.telnet(self.ysmay, "ritual anima Tobin")

        self.assertIn("You have already performed your anima ritual in this scene.", told)
        self.assertEqual(anima_of(self.ysmay), 6)


class PerformingItWithNoRitual(JourneyCase):
    def test_she_is_told_to_name_someone_all_the_same(self) -> None:
        room = self.make_room("The Lantern")
        hobb = self.make_player("Hobb", room=room)

        told = self.telnet(hobb, "ritual anima")

        self.assertIn(f"{NEEDS_A_PARTNER} Usage: ritual anima <partner>", told)
