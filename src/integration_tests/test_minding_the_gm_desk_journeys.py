"""Journeys through the GM desk (#3657, tranche 11): ``gmtable``, ``gmtrust``,
``gm prompts`` / ``gm prompt``, ``moment`` and ``gemit``.

Hobb runs a table and answers what the game puts in front of him; Marrow is staff;
Ysmay and the others are the players it happens to. Each journey types what a person
types through the command handler and asserts what they were told and what the rows
hold.
"""

from __future__ import annotations

from unittest.mock import patch

from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel, GMPromptGroup, GMPromptKind, GMPromptStatus, GMTableStatus
from world.gm.factories import (
    GMLevelCapFactory,
    GMProfileFactory,
    GMPromptFactory,
    GMPromptFilterFactory,
)
from world.gm.models import GMLevelChange, GMPromptNarration, GMTable, GMTableMembership
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
)
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.narrative.constants import GemitReach
from world.narrative.models import Gemit
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory, SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction
from world.societies.constants import RenownRisk
from world.societies.factories import OrganizationFactory, SocietyFactory

NOT_HERE = "Could not find '{}'."


def staff(case: JourneyCase, character) -> None:
    account = case.account_of(character)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    account.permissions.add("Admin")


class KeepingATable(JourneyCase):
    """Hobb opens a table, seats Ysmay at it and lets her go; Marrow archives it."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        self.hobb_gm = GMProfileFactory(account=self.account_of(self.hobb))
        self.bram_gm = GMProfileFactory(account=self.account_of(self.bram))
        staff(self, self.marrow)

    def test_a_table_is_opened_seated_cleared_and_handed_on(self) -> None:
        self.assertIn("Only GMs may manage tables.", self.telnet(self.ysmay, "gmtable"))
        self.assertIn(
            "You own no tables. Create one with: gmtable create <name>",
            self.telnet(self.hobb, "gmtable"),
        )
        self.assertIn("Usage:", self.telnet(self.hobb, "gmtable frobnicate"))
        self.assertIn("Usage:", self.telnet(self.hobb, "gmtable create"))
        self.assertIn(
            "You need a GM profile to own a table.", self.telnet(self.marrow, "gmtable list")
        )

        told = self.telnet(self.hobb, "gmtable create Round Table=Weekly romp")
        table = GMTable.objects.get(name="Round Table")
        self.assertIn(f"Created table #{table.pk}: Round Table", told)
        self.assertEqual(table.gm_id, self.hobb_gm.pk)
        self.assertEqual(table.description, "Weekly romp")
        listed = strip_ansi(self.telnet(self.hobb, "gmtable list"))
        self.assertIn("Your GM tables:", listed)
        self.assertIn(f"#{table.pk} Round Table [{table.status}]", listed)
        self.assertIn("0 member(s)", listed)
        self.assertIn(
            f"Table #{table.pk} (Round Table) has no active members.",
            self.telnet(self.hobb, f"gmtable members {table.pk}"),
        )

        # Seating a persona, and the personas that cannot sit.
        told = self.telnet(self.hobb, f"gmtable invite {table.pk}=Ysmay")
        membership = GMTableMembership.objects.get(
            table=table, persona=self.ysmay.sheet_data.primary_persona, left_at__isnull=True
        )
        self.assertIn(f"Added Ysmay to #{table.pk} (Round Table)", told)
        self.assertIn(f"membership #{membership.pk}", told)
        members = strip_ansi(self.telnet(self.hobb, f"gmtable members {table.pk}"))
        self.assertIn(f"Members of #{table.pk} Round Table:", members)
        self.assertIn(f"membership #{membership.pk}: Ysmay", members)
        PersonaFactory(name="Masked One", persona_type=PersonaType.TEMPORARY)
        self.assertIn(
            "A temporary persona cannot join a GM table",
            self.telnet(self.hobb, f"gmtable invite {table.pk}=Masked One"),
        )
        self.assertIn(
            "No persona 'Nobody'.", self.telnet(self.hobb, f"gmtable invite {table.pk}=Nobody")
        )
        self.assertIn(
            "Table id must be a number.", self.telnet(self.hobb, "gmtable invite abc=Ysmay")
        )
        self.assertIn("Usage:", self.telnet(self.hobb, f"gmtable invite {table.pk}"))
        self.assertEqual(GMTableMembership.objects.filter(table=table).count(), 1)

        # Another GM's hands are kept off it.
        self.assertIn(
            "That is not your table.", self.telnet(self.bram, f"gmtable invite {table.pk}=Bram")
        )
        self.assertIn(
            "That is not your table.", self.telnet(self.bram, f"gmtable members {table.pk}")
        )
        self.assertIn(
            "That membership is not at your table.",
            self.telnet(self.bram, f"gmtable kick {membership.pk}"),
        )
        membership.refresh_from_db()
        self.assertIsNone(membership.left_at)

        # Letting her go, once.
        self.assertIn(
            f"Removed Ysmay from #{table.pk} (Round Table).",
            self.telnet(self.hobb, f"gmtable kick {membership.pk}"),
        )
        membership.refresh_from_db()
        self.assertIsNotNone(membership.left_at)
        self.assertIn(
            "That member has already left.", self.telnet(self.hobb, f"gmtable kick {membership.pk}")
        )
        self.assertIn("No such membership.", self.telnet(self.hobb, "gmtable kick 999999"))

        # Archive and transfer are staff's.
        self.assertIn(
            "Archiving a table is staff-only.",
            self.telnet(self.hobb, f"gmtable archive {table.pk}"),
        )
        self.assertIn(
            "Transferring a table is staff-only.",
            self.telnet(self.hobb, f"gmtable transfer {table.pk}=Bram"),
        )
        self.assertIn("No such table.", self.telnet(self.marrow, "gmtable archive 999999"))
        self.assertIn(
            "No GM with account 'nobody'.",
            self.telnet(self.marrow, f"gmtable transfer {table.pk}=nobody"),
        )
        bram_name = self.account_of(self.bram).username
        self.assertIn(
            f"Transferred #{table.pk} (Round Table) to {bram_name}.",
            self.telnet(self.marrow, f"gmtable transfer {table.pk}={bram_name}"),
        )
        table.refresh_from_db()
        self.assertEqual(table.gm_id, self.bram_gm.pk)
        self.assertIn(
            f"Archived #{table.pk} (Round Table).",
            self.telnet(self.marrow, f"gmtable archive {table.pk}"),
        )
        table.refresh_from_db()
        self.assertEqual(table.status, GMTableStatus.ARCHIVED)


class TrustingAGM(JourneyCase):
    """Hobb reads his own standing; Marrow reads anyone's, weighs the evidence and moves him."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        self.hobb_gm = GMProfileFactory(account=self.account_of(self.hobb), level=GMLevel.JUNIOR)
        GMLevelCapFactory(level=GMLevel.JUNIOR, max_beat_risk=RenownRisk.MODERATE)
        staff(self, self.marrow)
        self.hobb_name = self.account_of(self.hobb).username
        self.ysmay_name = self.account_of(self.ysmay).username

    def test_standing_is_read_and_changed_with_a_reason(self) -> None:
        self.assertIn("You are not a GM.", self.telnet(self.ysmay, "gmtrust show"))
        self.assertIn("Usage: gmtrust", self.telnet(self.hobb, "gmtrust frobnicate"))
        shown = self.telnet(self.hobb, "gmtrust show")
        self.assertIn(f"{self.hobb_name}: Junior GM", shown)
        self.assertIn("Max beat risk: Moderate", shown)
        self.assertIn("Custom stakes allowed: False", shown)

        # Looking at anyone else, the evidence and the ladder are staff's.
        staff_only = "Only staff may do that."
        self.assertIn(staff_only, self.telnet(self.hobb, f"gmtrust show {self.ysmay_name}"))
        self.assertIn(staff_only, self.telnet(self.hobb, f"gmtrust evidence {self.hobb_name}"))
        self.assertIn(
            staff_only, self.telnet(self.hobb, f"gmtrust promote {self.hobb_name}=gm reason=me")
        )
        self.hobb_gm.refresh_from_db()
        self.assertEqual(self.hobb_gm.level, GMLevel.JUNIOR)

        self.assertIn("Junior GM", self.telnet(self.marrow, f"gmtrust show {self.hobb_name}"))
        self.assertIn(
            "No account named 'nobody-here'.", self.telnet(self.marrow, "gmtrust show nobody-here")
        )
        self.assertIn(
            "That account has no GM profile.",
            self.telnet(self.marrow, f"gmtrust show {self.ysmay_name}"),
        )
        self.assertIn(
            "Usage: gmtrust evidence <account>.", self.telnet(self.marrow, "gmtrust evidence")
        )
        self.assertIn(
            "That account has no GM profile.",
            self.telnet(self.marrow, f"gmtrust evidence {self.ysmay_name}"),
        )
        evidence = self.telnet(self.marrow, f"gmtrust evidence {self.hobb_name}")
        self.assertIn(f"GM evidence for {self.hobb_name}:", evidence)
        self.assertIn("Stories running: 0", evidence)
        self.assertIn("Recent level changes: none", evidence)

        usage = "Usage: gmtrust promote <account>=<level> reason=<why>."
        self.assertIn(usage, self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}=gm"))
        self.assertIn(
            usage, self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}=gm reason=")
        )
        self.assertIn(usage, self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}"))
        self.assertIn(
            "Unknown GM level 'nonsense'. Valid levels: Starting GM, Junior GM, GM, "
            "Experienced GM, Senior GM.",
            self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}=nonsense reason=whatever"),
        )
        self.assertIn(
            "That account has no GM profile.",
            self.telnet(self.marrow, f"gmtrust promote {self.ysmay_name}=junior reason=a story"),
        )
        self.assertFalse(GMLevelChange.objects.exists())

        told = self.telnet(
            self.marrow,
            f"gmtrust promote {self.hobb_name}=Experienced GM reason=strong first story",
        )
        self.assertIn(f"Changed {self.hobb_name}: Junior GM", told)
        self.assertIn("Experienced GM.", told)
        self.hobb_gm.refresh_from_db()
        self.assertEqual(self.hobb_gm.level, GMLevel.EXPERIENCED)
        change = GMLevelChange.objects.get(profile=self.hobb_gm)
        self.assertEqual(
            (change.old_level, change.new_level), (GMLevel.JUNIOR, GMLevel.EXPERIENCED)
        )
        self.assertEqual(change.changed_by_id, self.account_of(self.marrow).pk)
        self.assertEqual(change.reason, "strong first story")

        # Down the ladder too, and never to the rung he is on.
        self.assertIn(
            "Changed",
            self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}=junior reason=too soon"),
        )
        self.hobb_gm.refresh_from_db()
        self.assertEqual(self.hobb_gm.level, GMLevel.JUNIOR)
        self.assertIn(
            "already at level",
            self.telnet(self.marrow, f"gmtrust promote {self.hobb_name}=junior reason=again"),
        )
        evidence = self.telnet(self.marrow, f"gmtrust evidence {self.hobb_name}")
        self.assertIn("Recent level changes:", evidence)
        self.assertIn("too soon", evidence)
        self.assertIn(f"by {self.account_of(self.marrow).username}", evidence)


class AnsweringAPrompt(JourneyCase):
    """Orla crosses; the game prompts Hobb, who narrates it, sends the authored lines, or
    lets them go out on their own."""

    def setUp(self) -> None:
        super().setUp()
        self.shrine = self.make_room("The Shrine")
        self.orla = self.make_player("Orla", room=self.shrine)
        self.hobb = self.make_player("Hobb", room=self.shrine)
        self.caddoc = self.make_player("Caddoc", room=self.shrine)
        self.watch(self.orla, self.caddoc)
        self.hobb_account = self.account_of(self.hobb)
        GMProfileFactory(account=self.hobb_account, level=GMLevel.GM)
        self.scene = SceneFactory(location=RoomProfileFactory(objectdb=self.shrine), is_active=True)
        SceneGMParticipationFactory(scene=self.scene, account=self.hobb_account)
        self.other_gm = GMProfileFactory().account

    def prompt_for(self, subject_sheet, *, addressed_to=None, private="", room=""):
        return GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=subject_sheet,
            addressed_to=addressed_to or self.hobb_account,
            moment_type=None,
            success_level=None,
            private_text=private,
            room_text=room,
        )

    def test_the_prompt_is_listed_and_its_lines_sent_once(self) -> None:
        prompt = self.prompt_for(
            self.orla.sheet_data, private="A door opens in your mind.", room="The candles gutter."
        )
        moment = GMPromptFactory(scene=self.scene)
        self.assertEqual("No GM prompts are waiting.", self.telnet(self.orla, "gm prompts").strip())
        listed = self.telnet(self.hobb, "gm prompts")
        self.assertIn(f"[{prompt.pk}] Crossing: Orla", listed)
        self.assertIn("private: A door opens in your mind.", listed)
        self.assertIn("room: The candles gutter.", listed)
        self.assertIn(f"gm prompt send {prompt.pk}", listed)
        self.assertIn(f"moment confirm {moment.pk} | moment dismiss {moment.pk}", listed)
        self.assertNotIn(f"gm prompt dismiss {moment.pk}", listed)
        self.assertIn("Narration prompts waiting: 1", self.telnet(self.hobb, "gm dashboard"))

        usage = "Usage: gm prompt send <id> | gm prompt dismiss <id> | gm prompt done <id>"
        self.assertIn(usage, self.telnet(self.hobb, "gm prompt frobnicate 1"))
        self.assertIn(usage, self.telnet(self.hobb, "gm prompt send abc"))

        with self.captureOnCommitCallbacks(execute=True):
            self.assertIn("Sent and closed.", self.telnet(self.hobb, f"gm prompt send {prompt.pk}"))
        self.assertTold(self.orla, "A door opens in your mind.")
        self.assertNotTold(self.caddoc, "A door opens in your mind.")
        self.assertTold(self.caddoc, "The candles gutter.")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 2)
        self.assertEqual(
            Interaction.objects.filter(content="A door opens in your mind.").count(), 1
        )
        self.assertEqual(Interaction.objects.filter(content="The candles gutter.").count(), 1)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertIn(
            "That prompt has already been dealt with.",
            self.telnet(self.hobb, f"gm prompt send {prompt.pk}"),
        )
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 2)

    def test_a_prompt_that_is_not_his_or_not_here(self) -> None:
        theirs = self.prompt_for(self.orla.sheet_data, addressed_to=self.other_gm, room="A wonder.")
        self.assertIn(
            "There is no such GM prompt.", self.telnet(self.hobb, f"gm prompt send {theirs.pk}")
        )
        self.assertEqual(GMPromptNarration.objects.filter(prompt=theirs).count(), 0)

        his = self.prompt_for(self.orla.sheet_data, private="A vision.", room="A hush.")
        elsewhere = self.make_room("The Road")
        self.hobb.location = elsewhere
        self.hobb.save()
        told = self.telnet(self.hobb, f"gm prompt send {his.pk}")
        self.assertIn("Narrate that prompt from the scene it happened in.", told)
        self.assertEqual(GMPromptNarration.objects.filter(prompt=his).count(), 0)
        his.refresh_from_db()
        self.assertEqual(his.status, GMPromptStatus.PENDING)

    def test_an_absent_subject_gets_the_private_line_when_the_prompt_closes(self) -> None:
        away_sheet = CharacterSheetFactory()
        self.watch(away_sheet.character)
        prompt = self.prompt_for(away_sheet, private="Only for you.", room="A hush falls.")
        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.hobb, f"gm prompt send {prompt.pk}")
        self.assertIn("isn't here; their private line goes out on its own", told)
        self.assertTold(self.caddoc, "A hush falls.")
        self.assertTold(away_sheet.character, "Only for you.")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 1)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)

    def test_dismissing_releases_the_authored_lines(self) -> None:
        prompt = self.prompt_for(self.orla.sheet_data, private="A vision.", room="A hush.")
        # A harness character has no session, and the released room line goes only to
        # non-web sessions; stand one in so the on-commit delivery has somewhere to land.
        on_telnet = patch(
            "world.scenes.interaction_services.non_web_sessions", return_value=[object()]
        )
        with on_telnet, self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.hobb, f"gm prompt dismiss {prompt.pk}")
        self.assertIn("Dismissed; the authored text goes out on its own.", told)
        self.assertTold(self.orla, "A vision.")
        self.assertTold(self.caddoc, "A hush.")
        self.assertEqual(Interaction.objects.filter(content="A hush.").count(), 1)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertEqual("No GM prompts are waiting.", self.telnet(self.hobb, "gm prompts").strip())

    def test_his_own_words_link_to_the_prompt_and_done_closes_it(self) -> None:
        prompt = self.prompt_for(self.orla.sheet_data, private="A vision.", room="A hush.")
        self.assertNotIn(
            "The floor groans.",
            self.telnet(self.orla, f"emit/prompt {prompt.pk} The floor groans."),
        )
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 0)

        self.telnet(self.hobb, f"emit/prompt {prompt.pk} The floor groans.")
        self.assertTold(self.caddoc, "The floor groans.")
        link = GMPromptNarration.objects.get(prompt=prompt)
        self.assertEqual(link.interaction.content, "The floor groans.")
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)
        self.assertIn(
            f"[{prompt.pk}] Crossing (narrated): Orla", self.telnet(self.hobb, "gm prompts")
        )
        self.assertIn("Narration prompts waiting: 1", self.telnet(self.hobb, "gm dashboard"))

        self.telnet(self.hobb, f"pemit/prompt {prompt.pk} Orla=A whisper only you hear.")
        self.assertTold(self.orla, "A whisper only you hear.")
        self.assertNotTold(self.caddoc, "A whisper only you hear.")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 2)

        with self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.hobb, f"gm prompt done {prompt.pk}")
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        # Both legs were his own words, so nothing authored goes out on close.
        self.assertNotTold(self.orla, "A vision.")
        self.assertNotTold(self.caddoc, "A hush.")


class SuggestingADramaticMoment(JourneyCase):
    """The game suggests Ysmay's moment to Hobb, who confirms, dismisses, or tags one himself."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.caddoc = self.make_player("Caddoc", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.hobb_account = self.account_of(self.hobb)
        GMProfileFactory(account=self.hobb_account, level=GMLevel.GM)
        self.scene = SceneFactory(
            location=RoomProfileFactory(objectdb=self.lantern), is_active=True
        )
        SceneGMParticipationFactory(scene=self.scene, account=self.hobb_account)
        self.steel = ResonanceFactory(name="Steel")
        CharacterResonanceFactory(character_sheet=self.ysmay.sheet_data, resonance=self.steel)
        CharacterResonanceFactory(character_sheet=self.caddoc.sheet_data, resonance=self.steel)
        self.flourish = DramaticMomentTypeFactory(
            label="A Flourish of Steel", resonance=self.steel, per_scene_cap=1, resonance_amount=15
        )
        self.suggestion = GMPromptFactory(
            moment_type=self.flourish, character_sheet=self.ysmay.sheet_data, scene=self.scene
        )

    def test_a_suggestion_is_listed_for_the_gm_alone_and_confirmed_once(self) -> None:
        usage = (
            "Usage: moment suggestions|confirm <id>|dismiss <id>|tag <character>=<type>|tag list"
        )
        self.assertIn(usage, self.telnet(self.hobb, "moment"))
        self.assertIn(usage, self.telnet(self.hobb, "moment frobnicate"))
        listed = strip_ansi(self.telnet(self.hobb, "moment suggestions"))
        self.assertIn("Pending dramatic-moment suggestions:", listed)
        self.assertIn(f"#{self.suggestion.pk}: A Flourish of Steel", listed)
        self.assertIn("Ysmay", listed)
        for player in (self.ysmay, self.caddoc):
            told = self.telnet(player, "moment suggestions")
            self.assertIn("No pending dramatic-moment suggestions in this scene.", told)
            self.assertNotIn(str(self.suggestion.pk), told)

        self.assertIn("Usage: moment confirm <id>", self.telnet(self.hobb, "moment confirm"))
        self.assertIn(
            "Only the scene's GM, owner, or staff may resolve dramatic-moment suggestions.",
            self.telnet(self.ysmay, f"moment confirm {self.suggestion.pk}"),
        )
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)
        self.assertIn(
            "You confirm the 'A Flourish of Steel' dramatic-moment suggestion.",
            self.telnet(self.hobb, f"moment confirm {self.suggestion.pk}"),
        )
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.CONFIRMED)
        self.assertIsNotNone(self.suggestion.confirmed_tag_id)
        self.assertIn(
            "already", self.telnet(self.hobb, f"moment confirm {self.suggestion.pk}").lower()
        )
        self.assertIn(
            "No pending dramatic-moment suggestions in this scene.",
            self.telnet(self.hobb, "moment suggestions"),
        )

    def test_a_suggestion_is_dismissed_and_a_narration_prompt_is_not_a_suggestion(self) -> None:
        self.assertIn(
            "Only the scene's GM, owner, or staff may resolve dramatic-moment suggestions.",
            self.telnet(self.ysmay, f"moment dismiss {self.suggestion.pk}"),
        )
        self.assertIn(
            "You dismiss the 'A Flourish of Steel' dramatic-moment suggestion.",
            self.telnet(self.hobb, f"moment dismiss {self.suggestion.pk}"),
        )
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.DISMISSED)
        self.assertIsNone(self.suggestion.confirmed_tag_id)

        crossing = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.ysmay.sheet_data,
            addressed_to=GMProfileFactory().account,
            moment_type=None,
            success_level=None,
            room_text="A wonder occurs.",
        )
        which = "Which suggestion? Provide a suggestion id."
        self.assertIn(which, self.telnet(self.hobb, f"moment confirm {crossing.pk}"))
        self.assertIn(which, self.telnet(self.hobb, f"moment dismiss {crossing.pk}"))
        crossing.refresh_from_db()
        self.assertEqual(crossing.status, GMPromptStatus.PENDING)
        self.assertNotIn(f"#{crossing.pk}:", self.telnet(self.hobb, "moment suggestions"))

    def test_a_muted_group_and_a_room_with_no_scene_show_nothing(self) -> None:
        GMPromptFilterFactory(
            account=self.hobb_account, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False
        )
        told = self.telnet(self.hobb, "moment suggestions")
        self.assertIn("No pending dramatic-moment suggestions in this scene.", told)
        self.assertNotIn(str(self.suggestion.pk), told)
        self.hobb.location = self.make_room("The Road")
        self.hobb.save()
        self.assertIn(
            "There is no active scene here.", self.telnet(self.hobb, "moment suggestions")
        )
        self.assertIn("There is no active scene here.", self.telnet(self.hobb, "moment tag list"))

    def test_the_gm_tags_a_moment_himself(self) -> None:
        self.assertIn(
            "Only the scene's GM, owner, or staff may list dramatic-moment types.",
            self.telnet(self.ysmay, "moment tag list"),
        )
        types = strip_ansi(self.telnet(self.hobb, "moment tag list"))
        self.assertIn("Available dramatic-moment types:", types)
        self.assertIn("A Flourish of Steel", types)
        self.assertIn("Steel (15)", types)
        usage = (
            "Usage: moment suggestions|confirm <id>|dismiss <id>|tag <character>=<type>|tag list"
        )
        self.assertIn(usage, self.telnet(self.hobb, "moment tag"))
        self.assertIn(usage, self.telnet(self.hobb, "moment tag Caddoc"))
        self.assertIn(
            "Only the scene's GM, owner, or staff may tag dramatic moments.",
            self.telnet(self.ysmay, "moment tag Caddoc=A Flourish of Steel"),
        )
        # Once, and typed with the structured frame, as every refusal is: the loud search
        # had sent Evennia's bare line and the command nothing of its own.
        box = self.mailbox(self.hobb)
        first_frame = len(box.calls)
        self.assertEqual(
            NOT_HERE.format("Nobody"),
            self.telnet(self.hobb, "moment tag Nobody=A Flourish of Steel").strip(),
        )
        self.assertEqual(
            box.calls[first_frame:],
            [
                (((NOT_HERE.format("Nobody"), {"type": "error"}),), {}),
                (
                    (None,),
                    {
                        "command_error": {
                            "error": NOT_HERE.format("Nobody"),
                            "command": "moment tag Nobody=A Flourish of Steel",
                        }
                    },
                ),
            ],
        )
        ObjectDBFactory(db_key="Pebble", location=self.lantern)
        self.assertIn(
            "That is not a character.",
            self.telnet(self.hobb, "moment tag Pebble=A Flourish of Steel"),
        )
        self.assertIn(
            "No dramatic-moment type named 'Nothing'. Available: A Flourish of Steel",
            self.telnet(self.hobb, "moment tag Caddoc=Nothing"),
        )
        self.assertFalse(
            DramaticMomentTag.objects.filter(character_sheet=self.caddoc.sheet_data).exists()
        )

        self.assertIn(
            "You tagged Caddoc with 'A Flourish of Steel'. 15 Steel and renown awarded.",
            self.telnet(self.hobb, "moment tag Caddoc=A Flourish of Steel"),
        )
        tag = DramaticMomentTag.objects.get(
            character_sheet=self.caddoc.sheet_data, moment_type=self.flourish
        )
        self.assertEqual(tag.tagged_by_id, self.hobb_account.pk)
        self.assertEqual(tag.scene_id, self.scene.pk)
        self.assertIn(
            "This dramatic moment has already been awarded its maximum times this scene.",
            self.telnet(self.hobb, "moment tag Caddoc=A Flourish of Steel"),
        )
        # Bram never claimed Steel: the renown lands, the resonance does not.
        told = self.telnet(self.hobb, "moment tag Bram=A Flourish of Steel")
        self.assertIn(
            "You tagged Bram with 'A Flourish of Steel'. Renown awarded; no resonance", told
        )
        # An explicit resonance names what the moment draws on.
        ember = ResonanceFactory(name="Ember")
        CharacterResonanceFactory(character_sheet=self.ysmay.sheet_data, resonance=ember)
        self.assertIn(
            "You tagged Ysmay with 'A Flourish of Steel'. 15 Ember and renown awarded.",
            self.telnet(self.hobb, "moment tag Ysmay=A Flourish of Steel resonance=Ember"),
        )
        self.assertIn(
            "No resonance named 'Nothing'.",
            self.telnet(self.hobb, "moment tag Ysmay=A Flourish of Steel resonance=Nothing"),
        )


class ProclaimingToTheRealm(JourneyCase):
    """Marrow, staff, sends a gemit game-wide, to a society, to an organization."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        staff(self, self.marrow)

    def test_a_gemit_goes_out_verbatim_to_its_reach(self) -> None:
        self.assertIn("is not available", self.telnet(self.ysmay, "gemit Hello."))
        self.assertIn("Usage:", self.telnet(self.marrow, "gemit"))
        self.assertIn(
            "Gemit sent game-wide.",
            self.telnet(self.marrow, "gemit |rWar|n has come to the realm."),
        )
        gemit = Gemit.objects.get()
        self.assertEqual(gemit.reach, GemitReach.GAME_WIDE)
        self.assertEqual(gemit.body, "|rWar|n has come to the realm.")

        society = SocietyFactory(name="The Compact")
        self.assertIn(
            "Gemit sent to the members of: The Compact.",
            strip_ansi(self.telnet(self.marrow, "gemit/society The Compact = The Compact stirs.")),
        )
        scoped = Gemit.objects.exclude(pk=gemit.pk).get()
        self.assertEqual(scoped.reach, GemitReach.SPECIFIED)
        self.assertEqual(list(scoped.reach_societies.all()), [society])
        self.assertEqual(scoped.body, "The Compact stirs.")

        wardens = OrganizationFactory(name="The Wardens")
        self.assertIn(
            "Gemit sent to the members of: The Wardens.",
            strip_ansi(self.telnet(self.marrow, "gemit/org The Wardens = Muster at dawn.")),
        )
        self.assertEqual(list(Gemit.objects.latest("pk").reach_organizations.all()), [wardens])

        self.assertIn(
            "No society named 'Nowhere'.",
            self.telnet(self.marrow, "gemit/society Nowhere = Hello."),
        )
        self.assertIn(
            "No organization named 'Nowhere'.",
            self.telnet(self.marrow, "gemit/org Nowhere = Hello."),
        )
        self.assertIn("Usage:", self.telnet(self.marrow, "gemit/society The Compact"))
        self.assertIn(
            "The gemit needs a message after the '='.",
            self.telnet(self.marrow, "gemit/society The Compact ="),
        )
        self.assertIn(
            "Name at least one target before the '='.",
            self.telnet(self.marrow, "gemit/society = Hello."),
        )
        self.assertEqual(Gemit.objects.count(), 3)
