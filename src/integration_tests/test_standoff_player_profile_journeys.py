"""Journeys for slice 5 of the standoffs feature (#4441, #4121): a player gives their own
character drives and a cause, opts in to being read and pressed, and another player's
character then reads and presses them in a standoff. Each types what a player types and
asserts what the game told them and what rows now exist."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.conditions.factories import ConditionTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.standoffs.constants import (
    PROFILE_LOCKED_MESSAGE,
    DriveStrength,
    StandoffGroupState,
)
from world.standoffs.factories import (
    CreatureDriveFactory,
    StandoffApproachFactory,
    StandoffGroupFactory,
)
from world.standoffs.models import CharacterStandoffProfile, StandoffConfig
from world.standoffs.services.state import open_standoff
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"


def forced(level: int) -> SimpleNamespace:
    outcome = CheckOutcomeFactory(name=f"Profile tier {level}", success_level=level)
    return SimpleNamespace(success_level=level, outcome=outcome, chart=None)


class PlayersReadAndPressEachOther(JourneyCase):
    """Maud's player opts her in and gives her a drive and a cause; Ysmay reads and presses
    her at a gate; Hobb never opted in and cannot be reached; a story NPC needs no consent."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()
        self.gate = self.make_room("The River Gate")
        self.ysmay = self.make_player("Ysmay", room=self.gate)
        self.maud = self.make_player("Maud", room=self.gate)
        self.hobb = self.make_player("Hobb", room=self.gate)
        self.greedy = PropertyFactory(name="Greedy (journey)")
        CreatureDriveFactory(creature_template=CreatureTemplateFactory(), property=self.greedy)
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.terms_check_type = CheckTypeFactory()
        config.pass_condition = ConditionTemplateFactory()
        config.save()
        self.bribe = StandoffApproachFactory(name="Bribe (journey)")
        self.encounter = CombatEncounterFactory(room=self.gate)
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.ysmay.sheet_data)

    def stand(self, character) -> None:
        """Stand ``character`` as an opponent, the way a GM's add-opponent does."""
        CombatOpponentFactory(
            encounter=self.encounter,
            persona=character.sheet_data.primary_persona,
            name=character.key,
        )

    def test_a_player_opts_in_and_sets_a_profile_on_telnet_and_the_web(self) -> None:
        told = self.telnet(self.maud, "standoff profile")
        self.assertIn("cannot read and press you", told)
        self.assertIn("You have no drives.", told)

        self.assertIn(
            "may now read and press you", self.telnet(self.maud, "standoff profile optin")
        )
        self.assertIn(
            "Your cause is now Orders",
            self.telnet(self.maud, "standoff profile cause orders"),
        )
        self.assertIn(
            "Your drives are updated",
            self.telnet(self.maud, "standoff profile drive Greedy (journey) major"),
        )
        told = self.telnet(self.maud, "standoff profile")
        self.assertIn("can read and press you", told)
        self.assertIn("Cause: Orders.", told)
        self.assertIn("Greedy (journey) (Major)", told)

        profile = CharacterStandoffProfile.objects.get(sheet=self.maud.sheet_data)
        self.assertTrue(profile.opted_in)
        self.assertEqual(profile.cause, CauseKind.ORDERS)
        self.assertEqual(profile.drives.get().strength, DriveStrength.MAJOR)

        # The sheet reads the same rows over the API, to the owner alone.
        url = f"/api/character-sheets/{self.maud.sheet_data.pk}/standoff-profile/"
        read = self.api(self.account_of(self.maud)).get(url)
        self.assertEqual(read.status_code, 200, read.content)
        body = read.json()
        self.assertTrue(body["opted_in"])
        self.assertEqual(body["cause"], CauseKind.ORDERS)
        self.assertEqual([d["name"] for d in body["drives"]], ["Greedy (journey)"])
        self.assertIn("Greedy (journey)", [p["label"] for p in body["properties"]])
        self.assertEqual(self.api(self.account_of(self.ysmay)).get(url).status_code, 404)

        # The web action is the same one the telnet line dispatches to.
        dropped = self.web(
            self.maud, "standoff_profile", change="drop_drive", property_id=self.greedy.pk
        )
        self.assertTrue(dropped.detail.success)
        refused = self.web(self.maud, "standoff_profile", change="drop_drive")
        self.assertFalse(refused.detail.success)
        self.web(self.maud, "standoff_profile", change="drive", property_id=self.greedy.pk)

        # A web change goes through the same rule, and a stranger cannot make it.
        response = self.api(self.account_of(self.maud)).post(
            url, {"change": "drop_drive", "property_id": self.greedy.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["drives"], [])
        response = self.api(self.account_of(self.ysmay)).post(
            url, {"change": "opt_out"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_a_drive_nobody_can_have_and_a_bad_cause_are_named_back(self) -> None:
        self.assertIn(
            "is not a drive anyone can have",
            self.telnet(self.maud, "standoff profile drive Invented Longing"),
        )
        self.assertIn("No cause 'wrath'", self.telnet(self.maud, "standoff profile cause wrath"))
        self.assertIn("Usage: standoff profile", self.telnet(self.maud, "standoff profile pose"))
        self.assertIn(
            "You do not have that drive",
            self.telnet(self.maud, "standoff profile drop Greedy (journey)"),
        )

    def test_an_opted_in_player_is_read_and_pressed_and_the_profile_sets_the_grade(self) -> None:
        self.telnet(self.maud, "standoff profile optin")
        self.telnet(self.maud, "standoff profile drive Greedy (journey) defining")
        self.stand(self.maud)
        groups = open_standoff(self.encounter)
        self.assertEqual([g.persona for g in groups], [self.maud.sheet_data.primary_persona])

        told = self.telnet(self.ysmay, "standoff")
        self.assertIn("Maud", told)
        with patch(CHECK, return_value=forced(2)):
            told = self.telnet(self.ysmay, "standoff read Maud")
        self.assertIn("Greedy (journey)", told)
        with patch(CHECK, return_value=forced(1)):
            told = self.telnet(self.ysmay, "standoff press Bribe (journey) Maud")
        self.assertIn("Success", told)

        # Her own profile is locked while she stands in it.
        self.assertIn(PROFILE_LOCKED_MESSAGE, self.telnet(self.maud, "standoff profile optout"))
        self.assertTrue(CharacterStandoffProfile.objects.get(sheet=self.maud.sheet_data).opted_in)

    def test_a_player_who_has_not_opted_in_cannot_be_read_or_pressed(self) -> None:
        self.stand(self.hobb)
        self.assertEqual(open_standoff(self.encounter), [])
        # Even a group made some other way refuses every verb, with no roll.
        group = StandoffGroupFactory(
            encounter=self.encounter,
            creature_template=None,
            persona=self.hobb.sheet_data.primary_persona,
        )
        with patch(CHECK, return_value=forced(2)) as roll:
            told = self.telnet(self.ysmay, "standoff read Hobb")
            result = self.web(
                self.ysmay, "standoff_press", group_id=group.pk, approach_id=self.bribe.pk
            )
        self.assertIn("has not agreed to be read or pressed", told)
        self.assertFalse(result.detail.success)
        roll.assert_not_called()

    def test_you_cannot_read_yourself(self) -> None:
        self.telnet(self.ysmay, "standoff profile optin")
        self.stand(self.ysmay)
        group = StandoffGroupFactory(
            encounter=self.encounter,
            creature_template=None,
            persona=self.ysmay.sheet_data.primary_persona,
        )
        told = self.telnet(self.ysmay, "standoff read Ysmay")
        self.assertIn("You cannot do that to yourself.", told)
        self.assertEqual(group.state, StandoffGroupState.OPEN)

    def test_a_story_npc_a_gm_holds_needs_no_consent(self) -> None:
        npc = self.make_player("Corporal Vey", room=self.gate)
        entry = npc.sheet_data.roster_entry
        entry.roster = RosterFactory(roster_type=RosterType.NPC, name="NPCs (journey)")
        entry.save(update_fields=["roster"])
        self.stand(npc)
        groups = open_standoff(self.encounter)
        self.assertEqual([g.name for g in groups], ["Corporal Vey"])
        with patch(CHECK, return_value=forced(2)):
            told = self.telnet(self.ysmay, "standoff read Corporal Vey")
        self.assertNotIn("has not agreed", told)
        self.assertNotIn("cannot do that", told)
