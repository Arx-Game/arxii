"""Journeys for attested resonance (#5327): an act is marked, a witness proposes, a GM undoes.

A character gains resonance outside an authored choice only when her player marks an act her
character took, when another player's endorsement is accepted by the poser, or when a GM tags
her pose. Every sentence asserted here is a literal taken from the approved design or the spec,
never imported from the code that writes it. Two standing exceptions to the design's sample
text: a GM or staff member is never named by account name ("The scene's GM", "Staff", "A GM"),
and a character whose pronouns are not in hand is "they".

Daven, Hale, Ilsa, Marek (the scene's GM), Wren and Brannoc stand in The Lantern, in one live
scene. Staff set the numbers, which are examples:

* A Success is worth 10 when its act is marked, at the full share of the lowest strength.
* Cruelty is Abyssal ("gloat", gain fatigue 6), Mercy Celestial ("inspire", 5), Fury and Grief
  Primal ("blaze", 4). Abyssal tires the character the gain was taken from, the others tire the
  character who gains, and nobody pays when the target is a game-run opponent with no sheet.
* A fatigue pool holds 100 on a character given composure or stamina of 100. A payer with
  room r (capacity minus current minus 1) pays min(cost, r), and the gain shrinks to
  amount x r // cost, which is 10 x 3 // 6 = 5 at a room of 3 and 0 at a room of 0.
* The weekly table pays 100 percent from 0 gained and 50 percent from 10 gained, so a second
  mark in a week pays 10 x 50 // 100 = 5.

The acts are written the way a roll writes them (``award_scene_act``), except where a pool
other than social is needed, which is built directly.
"""

from __future__ import annotations

import html
import json
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from integration_tests.test_earning_kindled_deeds_journeys import _Gate
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_every_check_outcome
from world.consent.factories import SocialConsentCategoryFactory
from world.fatigue.services import get_fatigue_capacity, get_or_create_fatigue_pool
from world.fatigue.tests import setup_stat
from world.gm.constants import GMLevel, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.journals.models import JournalEntry
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    PoseResonanceReachFactory,
    RecordedActFactory,
    ResonanceFactory,
    WeeklyMarkReturnFactory,
    ensure_conversion_pairs,
    kindle_resonance,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterResonance,
    PoseEndorsement,
    RecordedAct,
    ResonanceGrant,
    SceneEntryEndorsement,
)
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.magic.services.gain import get_resonance_gain_config, settle_weekly_pot
from world.magic.services.kindling import award_scene_act
from world.narrative.models import NarrativeMessageDelivery
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PoseKind,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import TraitCategory
from world.traits.services import ensure_canonical_check_outcome

SUBMIT_POSE = "/api/interactions/submit-pose/"
JOURNAL_ENTRIES = "/api/journals/entries/"
POSE_ENDORSEMENTS = "/api/magic/pose-endorsements/"
RECORDED_ACTS = "/api/magic/recorded-acts/"
GRANTS = "/api/magic/resonance-grants/"
ONE_PLAYER_TIRED = "Daven marked Cruelty on what they did to you. You are wearier."
PICK_ON_THE_BELL = "sets the cracked bell back on its hook and does not look at the empty pew."


class _Attested(JourneyCase):
    """The Lantern, its live scene, six players and the numbers above."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        for affinity, verb, cost in (
            (self.abyssal, "gloat", 6),
            (self.celestial, "inspire", 5),
            (self.primal, "blaze", 4),
        ):
            affinity.claim_verb = verb
            affinity.gain_fatigue = cost
            affinity.save()
        Affinity.objects.clear_cache()
        self.cruelty = ResonanceFactory(name="Cruelty", affinity=self.abyssal)
        self.mercy = ResonanceFactory(name="Mercy", affinity=self.celestial)
        self.fury = ResonanceFactory(name="Fury", affinity=self.primal)
        self.grief = ResonanceFactory(name="Grief", affinity=self.primal)
        self.success = ensure_canonical_check_outcome("Success")
        KindledDeedAwardFactory(outcome_tier=self.success, amount=10)
        self.faint = KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=100)

        self.room = self.make_room("The Lantern")
        self.scene = SceneFactory(room=self.room, name="Supper at the Lantern")
        invalidate_active_scene_cache(self.room)
        self.daven = self.make_player("Daven", room=self.room)
        self.hale = self.make_player("Hale", room=self.room)
        self.ilsa = self.make_player("Ilsa", room=self.room)
        self.marek = self.make_player("Marek", room=self.room)
        self.wren = self.make_player("Wren", room=self.room)
        self.brannoc = self.make_player("Brannoc", room=self.room)
        for player in (self.daven, self.hale, self.wren, self.brannoc):
            SceneParticipationFactory(scene=self.scene, account=self.account_of(player))
        # Ilsa is a co-owner of the scene and not its GM; Marek is its GM.
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account_of(self.ilsa))
        SceneGMParticipationFactory(scene=self.scene, account=self.account_of(self.marek))
        GMProfileFactory(account=self.account_of(self.marek), level=GMLevel.GM)
        for player in (
            self.daven,
            self.hale,
            self.ilsa,
            self.marek,
            self.wren,
            self.brannoc,
        ):
            self.watch(player)
            self.connect_telnet(player)

    # -- building ---------------------------------------------------------------

    def telnet(self, character, line: str) -> str:
        """A typed line, with the lines the game sends once it commits sent too."""
        with self.captureOnCommitCallbacks(execute=True):
            return super().telnet(character, line)

    def client(self, character):
        return self.api(self.account_of(character))

    def notices(self, character) -> str:
        """Every private line the game sent ``character``'s player as a narrative message,
        oldest first, read from the delivery rows so an offline player's lines count too."""
        return "\n".join(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=character.sheet_data)
            .order_by("pk")
            .values_list("message__body", flat=True)
        )

    def take_act(self, actor, target, what: str) -> RecordedAct:
        """``actor`` takes an act the way a roll records it: a scene action, a Success, aimed at
        ``target`` (a played character) or at a game-run opponent (None). Returns the act."""
        award_scene_act(
            actor.sheet_data,
            target.sheet_data if target is not None else None,
            None,
            self.success,
            action_name=what,
        )
        return RecordedAct.objects.filter(character_sheet=actor.sheet_data).latest("pk")

    def give_capacity(self, character, category: str = ActionCategory.SOCIAL) -> int:
        """Make ``character``'s ``category`` pool hold 100 and return what it holds."""
        stat = "composure" if category == ActionCategory.SOCIAL else "stamina"
        trait_category = (
            TraitCategory.SOCIAL if category == ActionCategory.SOCIAL else TraitCategory.PHYSICAL
        )
        setup_stat(character, stat, 100, trait_category)
        return get_fatigue_capacity(character.sheet_data, category)

    def fatigue_of(self, character, category: str = ActionCategory.SOCIAL) -> int:
        return get_or_create_fatigue_pool(character.sheet_data).get_current(category)

    def leave_room_for(self, character, room: int) -> None:
        """Wear ``character``'s social pool until only ``room`` more can be added to it."""
        capacity = self.give_capacity(character)
        pool = get_or_create_fatigue_pool(character.sheet_data)
        pool.set_current(ActionCategory.SOCIAL, capacity - 1 - room)
        pool.save()

    def balance(self, character, resonance) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=character.sheet_data, resonance=resonance
        ).first()
        return row.balance if row is not None else 0

    def mark_by_telnet(self, character, resonance: str, act: RecordedAct, text: str) -> str:
        return self.telnet(character, f"pose/reach {resonance}:{act.pk}={text}")

    def frames(self, character, name: str) -> list[dict]:
        """The payload of each ``name`` frame the game sent ``character``'s browser."""
        return [
            kwargs[name][1] for _args, kwargs in self.mailbox(character).calls if name in kwargs
        ]

    def pose_row(self, viewer, pose_id: int) -> dict:
        """The pose as ``viewer``'s own feed read shows it."""
        response = self.client(viewer).get(f"/api/interactions/{pose_id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.json()

    def web_pose(self, character, text: str, **extra) -> dict:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client(character).post(
                SUBMIT_POSE,
                {
                    "persona_id": character.sheet_data.primary_persona.pk,
                    "scene_id": self.scene.pk,
                    "content": text,
                    "client_request_id": str(uuid.uuid4()),
                    **extra,
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()


class ListingAndMarkingActsByTelnet(_Attested):
    """``acts`` lists what Daven did, and ``pose/reach <resonance>:<id>=<text>`` marks one."""

    def test_acts_lists_the_newest_first_with_what_a_situation_suggested_and_pays_nothing(
        self,
    ) -> None:
        self.assertIn("You have no acts to mark.", self.telnet(self.daven, "acts"))
        searched = self.take_act(self.daven, None, "Searched the cellar")
        # Cruelty is kindled by a feeling Daven carries, so it is suggested beside what he does
        # next; nothing is paid for it.
        kindle_resonance(self.daven.sheet_data, self.cruelty, self.faint)
        intimidated = self.take_act(self.daven, self.hale, "Intimidated")

        told = self.telnet(self.daven, "acts")

        self.assertIn("Your acts you have not marked:", told)
        newest = told.index(f"{intimidated.pk}. Intimidated Hale (")
        older = told.index(f"{searched.pk}. Searched the cellar (")
        self.assertLess(newest, older)
        self.assertIn("Cruelty: You carry ", told)
        self.assertIn("No resonance suggested.", told)
        self.assertIn("Mark one with: pose/reach", told)
        self.assertFalse(ResonanceGrant.objects.exists())

    def test_marking_an_act_pays_him_privately_and_tires_the_target_and_the_room_sees_a_pose(
        self,
    ) -> None:
        capacity = self.give_capacity(self.hale)
        act = self.take_act(self.daven, self.hale, "Intimidated")

        told = self.mark_by_telnet(self.daven, "cruelty", act, "leans over Hale. He is smiling.")

        # What Daven reads: the affinity's verb and what grew, never a number of fatigue.
        self.assertIn("You gloat. Your Cruelty grows by 10.", told)
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        # Hale reads who marked what on him, and the target is the one who is wearier.
        self.assertIn(ONE_PLAYER_TIRED, self.notices(self.hale))
        self.assertEqual(self.fatigue_of(self.hale), 6)
        self.assertLess(self.fatigue_of(self.hale), capacity)
        # Ilsa reads the pose and none of it.
        self.assertTold(self.ilsa, "leans over Hale. He is smiling.")
        for private in ("gloat", "grows by", "wearier", "marked Cruelty"):
            self.assertNotTold(self.ilsa, private)
        # The marked act is off his list.
        self.assertNotIn("Intimidated Hale", self.telnet(self.daven, "acts"))

    def test_a_mark_in_an_ephemeral_scene_pays_nothing_and_says_so(self) -> None:
        road = self.make_room("The Road")
        SceneFactory(room=road, privacy_mode=ScenePrivacyMode.EPHEMERAL)
        invalidate_active_scene_cache(road)
        self.daven.move_to(road, quiet=True)
        act = self.take_act(self.daven, None, "Frightened the grave-wight")

        told = self.mark_by_telnet(self.daven, "cruelty", act, "snarls at the grave-wight.")

        self.assertIn(
            "This scene is ephemeral and stores nothing, so a mark here pays nothing.", told
        )
        self.assertEqual(self.balance(self.daven, self.cruelty), 0)
        self.assertIn("Frightened the grave-wight", self.telnet(self.daven, "acts"))

    def test_the_recorded_acts_list_shows_the_player_her_own_acts_with_suggestions_only(
        self,
    ) -> None:
        kindle_resonance(self.daven.sheet_data, self.cruelty, self.faint)
        act = self.take_act(self.daven, self.hale, "Intimidated")
        url = f"{RECORDED_ACTS}?character_sheet={self.daven.sheet_data.pk}"

        mine = self.client(self.daven).get(url)
        theirs = self.client(self.ilsa).get(url)

        self.assertEqual(mine.status_code, status.HTTP_200_OK, mine.content)
        (row,) = mine.json()["results"]
        self.assertEqual((row["id"], row["label"]), (act.pk, "Intimidated Hale"))
        self.assertEqual([s["resonance_name"] for s in row["suggestions"]], ["Cruelty"])
        # No strength or amount leaves the server.
        self.assertEqual(set(row["suggestions"][0]), {"resonance_id", "resonance_name", "reason"})
        self.assertEqual(theirs.json()["results"], [])


class DavenIntimidatesHaleAndMarksTheAct(_Attested):
    """The whole story on the real seams: a real social action, the act it leaves, the mark.

    Daven types ``intimidate Hale``, Hale accepts, the roll lands on a Success, and the game
    writes the act down with Cruelty suggested (it is kindled by a feeling he carries). Daven
    reads it in ``acts``, marks it with ``pose/reach`` and reads what he gained, and Hale reads
    that he is wearier. Nothing is paid until the mark.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ActionTemplateFactory(
            name="Intimidate",
            category="social",
            target_type=ActionTargetType.SINGLE,
            check_type=CheckTypeFactory(name="Intimidation"),
            consent_category=SocialConsentCategoryFactory(key="menace", name="Menace"),
        )
        kindle_resonance(self.daven.sheet_data, self.cruelty, self.faint)
        self.give_capacity(self.hale)

    def test_a_real_intimidation_leaves_an_act_that_a_mark_pays(self) -> None:
        asked = self.telnet(self.daven, "intimidate Hale")
        self.assertIn("You move to intimidate Hale. Awaiting their response", asked)
        with force_every_check_outcome(self.success):
            self.telnet(self.hale, "accept")

        # The roll wrote the act down and paid nothing, though Cruelty is kindled.
        act = RecordedAct.objects.get(character_sheet=self.daven.sheet_data)
        self.assertEqual(act.label, "Intimidate Hale")
        self.assertFalse(ResonanceGrant.objects.exists())
        listed = self.telnet(self.daven, "acts")
        self.assertIn(f"{act.pk}. Intimidate Hale (", listed)
        self.assertIn("Cruelty: You carry ", listed)

        told = self.mark_by_telnet(self.daven, "cruelty", act, "leans over Hale. He is smiling.")

        self.assertIn("You gloat. Your Cruelty grows by 10.", told)
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        self.assertIn(ONE_PLAYER_TIRED, self.notices(self.hale))
        self.assertNotIn("Intimidate Hale", self.telnet(self.daven, "acts"))


class MarkingByTheWebAndAJournalEntry(_Attested):
    """The same mark through a web pose and through a journal entry, and what each reads."""

    def test_a_web_pose_pays_the_same_mark_and_the_room_reads_a_chip_never_the_amount(
        self,
    ) -> None:
        self.give_capacity(self.hale)
        act = self.take_act(self.daven, self.hale, "Intimidated")

        posed = self.web_pose(
            self.daven,
            "leans over Hale until the lantern light shakes in his eyes.",
            reach_act_id=act.pk,
            reach_resonance_id=self.cruelty.pk,
        )

        self.assertEqual(posed["mark_line"], "You gloat. Your Cruelty grows by 10.")
        self.assertTrue(posed["mark_recorded"])
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        self.assertIn(ONE_PLAYER_TIRED, self.notices(self.hale))
        # The live frame is one frame for the whole room: it carries no mark and no waiting pick,
        # and each browser is told the pose changed so it refetches its own view.
        for watcher in (self.hale, self.ilsa, self.marek):
            (live,) = self.frames(watcher, "interaction")
            self.assertEqual((live["act_marks"], live["pending_picks"]), ([], []))
            self.assertIn(
                posed["id"],
                [f["interaction_id"] for f in self.frames(watcher, "interaction_changed")],
            )
        # Ilsa's refetch shows the chip: the resonance and the act, and no amount.
        chip = self.pose_row(self.ilsa, posed["id"])["act_marks"]
        self.assertEqual([(c["resonance_name"], c["undone"]) for c in chip], [("Cruelty", False)])
        self.assertEqual(chip[0]["act_label"], "Intimidated Hale")
        self.assertNotIn("amount", chip[0])
        self.assertFalse(chip[0]["can_undo"])

    def test_the_chip_names_the_target_as_each_reader_knows_them_and_a_mask_stays_a_mask(
        self,
    ) -> None:
        # Daven took the act while Hale wore his own face, so he knows the target as Hale.
        act = self.take_act(self.daven, self.hale, "Intimidated")
        self.assertEqual(act.label, "Intimidated Hale")
        # By the time the pose is read Hale wears the Owl Mask, which Ilsa has not seen through.
        self.assertIn("You don a mask: 'Owl Mask'", self.telnet(self.hale, "persona mask Owl Mask"))
        posed = self.web_pose(
            self.daven,
            "leans over the masked man.",
            reach_act_id=act.pk,
            reach_resonance_id=self.cruelty.pk,
        )

        daven_reads = self.pose_row(self.daven, posed["id"])["act_marks"][0]["act_label"]
        ilsa_reads = self.pose_row(self.ilsa, posed["id"])["act_marks"][0]["act_label"]

        # The actor reads the name she knows; everyone else reads the mask, never "Hale".
        self.assertEqual(daven_reads, "Intimidated Hale")
        self.assertEqual(ilsa_reads, "Intimidated Owl Mask")
        self.assertNotIn("Hale", json.dumps(self.pose_row(self.ilsa, posed["id"]), default=str))

    def test_a_target_with_no_sheet_keeps_its_name_for_every_reader(self) -> None:
        act = self.take_act(self.daven, None, "Frightened the grave-wight")

        posed = self.web_pose(
            self.daven,
            "snarls at the grave-wight.",
            reach_act_id=act.pk,
            reach_resonance_id=self.cruelty.pk,
        )

        for reader in (self.daven, self.ilsa, self.marek):
            chip = self.pose_row(reader, posed["id"])["act_marks"][0]
            self.assertEqual(chip["act_label"], "Frightened the grave-wight", reader.key)

    def test_a_journal_entry_pays_the_same_mark_and_carries_the_tiredness_of_a_celestial(
        self,
    ) -> None:
        self.give_capacity(self.wren)
        act = self.take_act(self.wren, None, "Tended the stranger")

        response = self.client(self.wren).post(
            JOURNAL_ENTRIES,
            {
                "title": "The stranger at the tollgate",
                "body": "I should have stopped sooner.",
                "is_public": False,
                "reach_act_id": act.pk,
                "reach_resonance_id": self.mercy.pk,
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.wren.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertEqual(
            response.json()["mark_line"],
            "You inspire. Your Mercy grows by 10, and you are wearier.",
        )
        self.assertTrue(response.json()["mark_recorded"])
        self.assertEqual(self.balance(self.wren, self.mercy), 10)
        self.assertEqual(self.fatigue_of(self.wren), 5)

    def test_a_journal_entry_whose_mark_is_refused_stays_posted_and_the_act_stays_listed(
        self,
    ) -> None:
        WeeklyMarkReturnFactory(gained_at_least=0, percent_paid=0)
        act = self.take_act(self.wren, None, "Tended the stranger")

        response = self.client(self.wren).post(
            JOURNAL_ENTRIES,
            {
                "title": "Too late",
                "body": "Nothing is paid.",
                "is_public": False,
                "reach_act_id": act.pk,
                "reach_resonance_id": self.mercy.pk,
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.wren.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        self.assertTrue(JournalEntry.objects.filter(title="Too late").exists())
        self.assertIn("so this one would pay nothing", response.json()["mark_line"])
        self.assertFalse(response.json()["mark_recorded"])
        self.assertEqual(self.balance(self.wren, self.mercy), 0)
        self.assertIn("Tended the stranger", self.telnet(self.wren, "acts"))


class WhoPaysTheFatigueOfAGain(_Attested):
    """Abyssal tires the target, the others the gainer, and a game-run opponent no one."""

    def test_a_target_with_little_left_pays_part_and_both_are_told_why(self) -> None:
        self.leave_room_for(self.hale, 3)
        act = self.take_act(self.daven, self.hale, "Intimidated")

        told = self.mark_by_telnet(self.daven, "cruelty", act, "leans over Hale.")

        self.assertIn(
            "You gloat. Your Cruelty grows by 5 instead of 10, because Hale had little left to "
            "give. Marks against Hale stay small until they have recovered.",
            told,
        )
        self.assertEqual(self.balance(self.daven, self.cruelty), 5)
        self.assertIn(
            f"{ONE_PLAYER_TIRED} You had little left to give, so it took only part.",
            self.notices(self.hale),
        )

    def test_a_target_with_nothing_left_refuses_the_gain_and_the_act_stays_on_the_list(
        self,
    ) -> None:
        self.leave_room_for(self.hale, 0)
        act = self.take_act(self.daven, self.hale, "Intimidated")

        told = self.mark_by_telnet(self.daven, "cruelty", act, "leans over Hale again.")

        self.assertIn(
            "Hale is too worn to pay for this, so your Cruelty does not grow. The act stays on "
            "your list. Mark it again once Hale has recovered, or mark another act.",
            told,
        )
        self.assertEqual(self.balance(self.daven, self.cruelty), 0)
        # The pose still posted, Hale is not wearier and told nothing, and the act is listed.
        self.assertTold(self.ilsa, "leans over Hale again.")
        self.assertNotIn("marked Cruelty", self.notices(self.hale))
        self.assertIn("Intimidated Hale", self.telnet(self.daven, "acts"))

    def test_a_game_run_opponent_pays_in_full_and_tires_no_one(self) -> None:
        self.give_capacity(self.hale)
        self.give_capacity(self.daven)
        act = self.take_act(self.daven, None, "Frightened the grave-wight")

        told = self.mark_by_telnet(self.daven, "cruelty", act, "snarls at the grave-wight.")

        self.assertIn("You gloat. Your Cruelty grows by 10.", told)
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        self.assertEqual((self.fatigue_of(self.hale), self.fatigue_of(self.daven)), (0, 0))

    def test_a_primal_gain_tires_the_character_who_gains_in_the_pool_of_the_act(self) -> None:
        self.give_capacity(self.daven, ActionCategory.PHYSICAL)
        act = RecordedActFactory(
            character_sheet=self.daven.sheet_data,
            outcome=self.success,
            label="Struck the raider",
            fatigue_category=ActionCategory.PHYSICAL,
        )

        told = self.mark_by_telnet(self.daven, "fury", act, "drives a shoulder into the raider.")

        self.assertIn("You blaze. Your Fury grows by 10, and you are wearier.", told)
        self.assertEqual(self.fatigue_of(self.daven, ActionCategory.PHYSICAL), 4)
        self.assertEqual(self.fatigue_of(self.daven), 0)


class TheWeeklyTableOfMarks(_Attested):
    """Each further mark in a game week pays less, and a row that pays 0 refuses the mark."""

    def test_a_second_mark_in_the_week_pays_the_reduced_percent_and_says_so(self) -> None:
        WeeklyMarkReturnFactory(gained_at_least=0, percent_paid=100)
        WeeklyMarkReturnFactory(gained_at_least=10, percent_paid=50)
        first = self.take_act(self.daven, None, "Frightened the grave-wight")
        second = self.take_act(self.daven, None, "Frightened the child")

        self.assertIn(
            "You gloat. Your Cruelty grows by 10.",
            self.mark_by_telnet(self.daven, "cruelty", first, "snarls."),
        )
        told = self.mark_by_telnet(self.daven, "cruelty", second, "snarls again.")

        self.assertIn(
            "You gloat. Your Cruelty grows by 5. This is your second mark this week, so it paid "
            "50 percent. Marks pay in full again next week.",
            told,
        )
        self.assertEqual(self.balance(self.daven, self.cruelty), 15)

    def test_a_row_that_pays_nothing_refuses_the_mark_and_the_act_stays_on_the_list(self) -> None:
        WeeklyMarkReturnFactory(gained_at_least=0, percent_paid=100)
        WeeklyMarkReturnFactory(gained_at_least=10, percent_paid=0)
        first = self.take_act(self.daven, None, "Frightened the grave-wight")
        second = self.take_act(self.daven, None, "Frightened the child")
        self.mark_by_telnet(self.daven, "cruelty", first, "snarls.")

        told = self.mark_by_telnet(self.daven, "cruelty", second, "snarls again.")

        self.assertIn(
            "Your marks this week have already paid all they will, so this one would pay "
            "nothing. The act stays on your list: mark it next week, when marks pay in full "
            "again.",
            told,
        )
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        self.assertIn("Frightened the child", self.telnet(self.daven, "acts"))


class AWitnessProposesAndThePoserDecides(_Attested):
    """On a pose that named no resonance, a witness picks from every resonance and the poser
    accepts. The pick can be changed and withdrawn until it pays."""

    def setUp(self) -> None:
        super().setUp()
        CharacterResonance.objects.create(
            character_sheet=self.brannoc.sheet_data, resonance=self.fury, balance=0
        )
        self.telnet(self.brannoc, f"pose {PICK_ON_THE_BELL}")

    def test_a_pick_waits_is_changed_is_accepted_and_pays_at_the_weekly_settlement(self) -> None:
        picked = self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=grief")
        self.assertIn(
            "You endorse Brannoc's pose #1 with Grief. It pays only if Brannoc accepts.", picked
        )
        self.assertIn(
            "Ilsa proposed Grief on your pose #1. "
            "Use endorse accept Ilsa #1 or endorse decline Ilsa #1.",
            self.notices(self.brannoc),
        )

        changed = self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=mercy")
        self.assertIn(
            "You change your pick on Brannoc's pose #1 from Grief to Mercy. "
            "It pays only if Brannoc accepts.",
            changed,
        )
        # Changing the pick does not message the poser again.
        self.assertEqual(self.notices(self.brannoc).count("proposed"), 1)
        self.assertEqual(PoseEndorsement.objects.get().resonance, self.mercy)

        # While it waits, the weekly settlement pays nothing and leaves the pick unsettled.
        settle_weekly_pot(self.ilsa.sheet_data)
        self.assertEqual(self.balance(self.brannoc, self.mercy), 0)
        self.assertIsNone(PoseEndorsement.objects.get().settled_at)

        accepted = self.telnet(self.brannoc, "endorse accept Ilsa #1")
        self.assertIn(
            "You accept Ilsa's Mercy on your pose #1. It pays at the weekly settlement.", accepted
        )
        settle_weekly_pot(self.ilsa.sheet_data)
        pot = get_resonance_gain_config().weekly_pot_per_character
        self.assertEqual(self.balance(self.brannoc, self.mercy), pot)
        # Neither Mercy nor Grief is in Brannoc's aura, and nothing Ilsa read named what is.
        self.assertNotIn("Fury", self.said(self.ilsa))

    def test_a_declined_pick_pays_nothing_and_a_withdrawn_one_is_gone(self) -> None:
        self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=grief")

        declined = self.telnet(self.brannoc, "endorse decline Ilsa #1")

        self.assertIn("You decline Ilsa's Grief on your pose #1. It pays nothing.", declined)
        self.assertFalse(PoseEndorsement.objects.exists())

        self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=mercy")
        withdrawn = self.telnet(self.ilsa, "endorse withdraw Brannoc #1")

        self.assertIn("You withdraw your Mercy endorsement of Brannoc's pose #1.", withdrawn)
        self.assertFalse(PoseEndorsement.objects.exists())
        # With nothing left to withdraw the command says so and changes nothing.
        again = self.telnet(self.ilsa, "endorse withdraw Brannoc #1")
        self.assertIn("You have no endorsement waiting on that pose of Brannoc.", again)
        settle_weekly_pot(self.ilsa.sheet_data)
        self.assertEqual(self.balance(self.brannoc, self.mercy), 0)

    def test_a_witness_cannot_answer_her_own_pick_and_a_stranger_cannot_withdraw_it(self) -> None:
        self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=grief")
        pick = PoseEndorsement.objects.get()

        # Only the witness's own player may withdraw over the web: another player's pick is a 404.
        hale_delete = self.client(self.hale).delete(f"{POSE_ENDORSEMENTS}{pick.pk}/")
        self.assertEqual(hale_delete.status_code, status.HTTP_404_NOT_FOUND)
        # She cannot accept the resonance she proposed herself.
        own = self.client(self.ilsa).post(f"{POSE_ENDORSEMENTS}{pick.pk}/accept/")
        self.assertIn(own.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND))
        pick.refresh_from_db()
        self.assertTrue(pick.awaiting_acceptance)

    def test_a_pick_the_poser_cannot_pay_for_this_week_stays_unsettled_and_pays_the_next(
        self,
    ) -> None:
        self.telnet(self.ilsa, "endorse pose Brannoc #1 resonance=mercy")
        self.telnet(self.brannoc, "endorse accept Ilsa #1")
        # Mercy is Celestial, so Brannoc pays for it, and she has nothing left this week.
        self.leave_room_for(self.brannoc, 0)

        with self.captureOnCommitCallbacks(execute=True):
            settle_weekly_pot(self.ilsa.sheet_data)

        self.assertIsNone(PoseEndorsement.objects.get().settled_at)
        self.assertEqual(self.balance(self.brannoc, self.mercy), 0)
        self.assertIn(
            "You were too worn to pay for this, so your Mercy does not grow from that "
            "endorsement. It will be tried again at next week's settlement.",
            self.notices(self.brannoc),
        )

        # Next week she has recovered, and the same endorsement pays.
        pool = get_or_create_fatigue_pool(self.brannoc.sheet_data)
        pool.set_current(ActionCategory.SOCIAL, 0)
        pool.save()
        settle_weekly_pot(self.ilsa.sheet_data)

        self.assertIsNotNone(PoseEndorsement.objects.get().settled_at)
        pot = get_resonance_gain_config().weekly_pot_per_character
        self.assertEqual(self.balance(self.brannoc, self.mercy), pot)
        self.assertEqual(self.fatigue_of(self.brannoc), 5)

    def test_over_the_web_each_viewer_reads_only_the_picks_that_are_theirs_to_see(self) -> None:
        pose = self.pose_row_id()
        picked = self.client(self.ilsa).post(
            POSE_ENDORSEMENTS,
            {"interaction": pose, "resonance": self.grief.pk},
            format="json",
        )
        self.assertEqual(picked.status_code, status.HTTP_201_CREATED, picked.content)
        self.assertTrue(picked.json()["awaiting_acceptance"])
        pick_id = picked.json()["id"]

        by = {name: self.pose_row(who, pose)["pending_picks"] for name, who in self.viewers()}
        # The witness reads her own pick as hers, the poser and the scene's GM read it as theirs
        # to answer, and Hale, who has no part in it, reads nothing.
        self.assertEqual(
            [
                (p["resonance_name"], p["endorser_name"], p["mine"], p["can_answer"])
                for p in by["ilsa"]
            ],
            [("Grief", "Ilsa", True, False)],
        )
        self.assertEqual([(p["mine"], p["can_answer"]) for p in by["brannoc"]], [(False, True)])
        self.assertEqual([(p["mine"], p["can_answer"]) for p in by["marek"]], [(False, True)])
        self.assertEqual(by["hale"], [])
        # A pick that is waiting is not counted among the pose's endorsers.
        self.assertEqual(self.pose_row(self.hale, pose)["pose_endorsers"], [])

        # The witness changes it; a stranger to the pick cannot answer it.
        changed = self.client(self.ilsa).post(
            f"{POSE_ENDORSEMENTS}{pick_id}/change/", {"resonance": self.mercy.pk}, format="json"
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK, changed.content)
        self.assertEqual(changed.json()["resonance"], self.mercy.pk)
        self.assertTrue(changed.json()["awaiting_acceptance"])
        refused = self.client(self.hale).post(f"{POSE_ENDORSEMENTS}{pick_id}/accept/")
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)

        # The poser accepts; it is now counted, and her player can no longer be asked.
        accepted = self.client(self.brannoc).post(f"{POSE_ENDORSEMENTS}{pick_id}/accept/")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)
        row = self.pose_row(self.hale, pose)
        self.assertEqual([e["resonance_id"] for e in row["pose_endorsers"]], [self.mercy.pk])
        self.assertEqual(row["pending_picks"], [])

    def test_a_decline_over_the_web_deletes_the_pick(self) -> None:
        pose = self.pose_row_id()
        picked = self.client(self.ilsa).post(
            POSE_ENDORSEMENTS, {"interaction": pose, "resonance": self.grief.pk}, format="json"
        )
        declined = self.client(self.brannoc).post(
            f"{POSE_ENDORSEMENTS}{picked.json()['id']}/decline/"
        )
        self.assertEqual(declined.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PoseEndorsement.objects.exists())

    def pose_row_id(self) -> int:
        """The id of Brannoc's pose, read from the scene feed as Ilsa sees it."""
        feed = self.client(self.ilsa).get(f"/api/interactions/?scene={self.scene.pk}")
        data = feed.json()
        rows = data["results"] if isinstance(data, dict) else data
        return next(row["id"] for row in rows if PICK_ON_THE_BELL in row["content"])

    def viewers(self):
        return (
            ("ilsa", self.ilsa),
            ("brannoc", self.brannoc),
            ("marek", self.marek),
            ("hale", self.hale),
        )


class EndorsingByTelnet(_Attested):
    """The endorsement commands a player types: ``poses``, ``endorse pose``, ``endorse entry``.

    Brannoc has two poses in the scene, a plain one (#1) and his entrance (#2), and holds Fury.
    """

    def setUp(self) -> None:
        super().setUp()
        CharacterResonanceFactory(
            character_sheet=self.brannoc.sheet_data,
            resonance=self.fury,
            balance=0,
            lifetime_earned=0,
        )
        persona = self.brannoc.sheet_data.primary_persona
        self.plain = InteractionFactory(
            scene=self.scene,
            persona=persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            content="polishes the cracked bell.",
        )
        self.entrance = InteractionFactory(
            scene=self.scene,
            persona=persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            pose_kind=PoseKind.ENTRY,
            content="walks in and shakes the rain from his coat.",
        )

    def test_poses_lists_each_pose_with_the_number_endorse_takes(self) -> None:
        told = self.telnet(self.ilsa, "poses Brannoc")

        self.assertIn("Endorseable poses from Brannoc in this scene:", told)
        self.assertIn("#1: polishes the cracked bell.", told)
        self.assertIn("#2: walks in and shakes the rain from his coat.", told)
        self.assertIn("Use: endorse pose <char> #N resonance=<name>", told)

    def test_a_number_picks_which_pose_and_the_pick_waits_for_the_poser(self) -> None:
        told = self.telnet(self.ilsa, "endorse pose Brannoc #2 resonance=fury")

        self.assertIn(
            "You endorse Brannoc's pose #2 with Fury. It pays only if Brannoc accepts.", told
        )
        pick = PoseEndorsement.objects.get()
        self.assertEqual((pick.interaction, pick.resonance), (self.entrance, self.fury))
        self.assertTrue(pick.awaiting_acceptance)

    def test_a_pose_that_named_its_resonance_is_previewed_then_confirmed_once(self) -> None:
        PoseResonanceReachFactory(interaction=self.plain, resonance=self.fury)

        preview = self.telnet(self.ilsa, "endorse pose Brannoc #1")
        self.assertIn("confirm", preview.lower())
        self.assertFalse(PoseEndorsement.objects.exists())

        confirmed = self.telnet(self.ilsa, "endorse pose Brannoc #1 confirm")
        self.assertIn(
            "You endorse the pose for Fury. It will count toward the weekly pot.", confirmed
        )
        self.assertFalse(PoseEndorsement.objects.get().awaiting_acceptance)

        again = self.telnet(self.ilsa, "endorse pose Brannoc #1 confirm")
        self.assertIn("Already endorsed this pose", again)
        self.assertEqual(PoseEndorsement.objects.count(), 1)

    def test_endorsing_an_entrance_pays_at_once(self) -> None:
        told = self.telnet(self.ilsa, "endorse entry Brannoc resonance=fury")

        self.assertIn(
            "You endorse Brannoc's scene entry for Fury. The grant fires immediately.", told
        )
        endorsement = SceneEntryEndorsement.objects.get()
        self.assertEqual(
            (endorsement.endorser_sheet, endorsement.endorsee_sheet, endorsement.scene),
            (self.ilsa.sheet_data, self.brannoc.sheet_data, self.scene),
        )
        self.assertEqual(
            self.balance(self.brannoc, self.fury), get_resonance_gain_config().scene_entry_grant
        )

    def test_outside_a_live_scene_poses_says_there_is_none(self) -> None:
        elsewhere = self.make_room("The Cellar")
        self.ilsa.move_to(elsewhere, quiet=True)
        self.brannoc.move_to(elsewhere, quiet=True)

        told = self.telnet(self.ilsa, "poses Brannoc")

        self.assertIn("There is no active scene here.", told)


class AMarkedPoseCannotBeEndorsedAndTheGMCanUndoIt(_Attested):
    """The scene's GM undoes a reward; a scene co-owner who is not the GM cannot."""

    def setUp(self) -> None:
        super().setUp()
        act = self.take_act(self.daven, None, "Frightened the child")
        self.posed = self.web_pose(
            self.daven,
            "catches the child by the collar and lets her see the knife.",
            reach_act_id=act.pk,
            reach_resonance_id=self.cruelty.pk,
        )
        self.grant = ResonanceGrant.objects.get(source=GainSource.MARKED_ACT)

    def test_each_viewer_reads_whether_they_may_undo_and_a_marked_pose_is_not_endorsable(
        self,
    ) -> None:
        reads = {
            name: self.pose_row(who, self.posed["id"])["act_marks"][0]
            for name, who in (("marek", self.marek), ("ilsa", self.ilsa), ("daven", self.daven))
        }

        self.assertEqual(
            {name: row["can_undo"] for name, row in reads.items()},
            {"marek": True, "ilsa": False, "daven": False},
        )
        endorsed = self.client(self.ilsa).post(
            POSE_ENDORSEMENTS,
            {"interaction": self.posed["id"], "resonance": self.cruelty.pk},
            format="json",
        )
        self.assertEqual(endorsed.status_code, status.HTTP_400_BAD_REQUEST, endorsed.content)

    def test_the_gm_undoes_it_and_the_player_reads_who_undid_what_and_how_much_it_fell(
        self,
    ) -> None:
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)

        with self.captureOnCommitCallbacks(execute=True):
            undone = self.client(self.marek).post(f"{GRANTS}{self.grant.pk}/undo/")

        self.assertEqual(undone.status_code, status.HTTP_200_OK, undone.content)
        self.assertEqual(undone.json()["id"], self.grant.pk)
        self.assertEqual(self.balance(self.daven, self.cruelty), 0)
        # The role is named, never the account.
        self.assertIn(
            "The scene's GM undid your Cruelty reward for Frightened the child. "
            "Your Cruelty falls by 10.",
            self.notices(self.daven),
        )
        self.assertNotIn("Marek", self.notices(self.daven))
        # The chip stays, struck through, naming the role; nobody can undo it twice.
        chip = self.pose_row(self.ilsa, self.posed["id"])["act_marks"][0]
        self.assertEqual((chip["undone"], chip["undone_by"], chip["can_undo"]), (True, "gm", False))
        again = self.client(self.marek).post(f"{GRANTS}{self.grant.pk}/undo/")
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST, again.content)
        # The act cannot be marked again.
        self.assertNotIn("Frightened the child", self.telnet(self.daven, "acts"))

    def test_a_scene_co_owner_who_is_not_the_gm_is_refused_and_nothing_changes(self) -> None:
        refused = self.client(self.ilsa).post(f"{GRANTS}{self.grant.pk}/undo/")

        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.balance(self.daven, self.cruelty), 10)
        self.grant.refresh_from_db()
        self.assertIsNone(self.grant.nullified_at)

    def test_another_players_account_cannot_undo_it_either(self) -> None:
        stranger = self.api(AccountFactory())

        refused = stranger.post(f"{GRANTS}{self.grant.pk}/undo/")

        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)


class AGMsTagNamesAResonanceOutsideHerAura(_Attested):
    """Marek, the scene's GM, tags Daven's pose and names Grief, which is not in Daven's aura.
    Only the scene's GM and staff name a resonance outside the aura: a co-owner's named
    resonance counts only when the character already has it. Nobody tags her own character."""

    def defiant_stand(self, resonance=None):
        return DramaticMomentTypeFactory(
            label="Defiant stand", resonance=resonance, resonance_amount=10, per_scene_cap=1
        )

    def test_a_co_owner_who_is_not_the_gm_names_a_resonance_outside_her_aura_and_gets_the_default(
        self,
    ) -> None:
        self.defiant_stand(self.fury)
        CharacterResonanceFactory(character_sheet=self.daven.sheet_data, resonance=self.fury)

        tagged = self.telnet(self.ilsa, "moment tag Daven=Defiant stand resonance=Grief")

        # Her named Grief is ignored, so the tag never says whether Daven has it; the type's own
        # Fury, which she holds, pays, and her player is told by whom, as a role.
        self.assertIn("You tagged Daven with 'Defiant stand'. 10 Fury and renown awarded.", tagged)
        self.assertEqual(
            (self.balance(self.daven, self.fury), self.balance(self.daven, self.grief)), (10, 0)
        )
        self.assertIn(
            "Someone tagged your pose: Defiant stand. It paid you Fury.",
            self.notices(self.daven),
        )
        self.assertNotIn("Ilsa", self.notices(self.daven))

    def test_nobody_tags_her_own_character_and_no_tag_is_written(self) -> None:
        self.defiant_stand(self.fury)

        refused = self.telnet(self.marek, "moment tag Marek=Defiant stand")

        self.assertIn("You cannot tag a moment for your own character.", refused)
        self.assertFalse(DramaticMomentTag.objects.exists())

    def test_a_character_who_is_not_part_of_the_scene_is_refused(self) -> None:
        self.defiant_stand(self.fury)
        elsewhere = self.make_room("The Cellar")
        self.make_player("Wolf", room=elsewhere)

        refused = self.telnet(self.marek, "moment tag Wolf=Defiant stand")

        self.assertIn("That character is not part of this scene.", refused)
        self.assertFalse(DramaticMomentTag.objects.exists())

    def test_a_gm_confirming_a_suggestion_for_her_own_character_is_refused(self) -> None:
        moment = self.defiant_stand(self.fury)
        suggestion = GMPromptFactory(
            moment_type=moment, character_sheet=self.marek.sheet_data, scene=self.scene
        )

        refused = self.telnet(self.marek, f"moment confirm {suggestion.pk}")

        self.assertIn("You cannot tag a moment for your own character.", refused)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, GMPromptStatus.PENDING)
        self.assertFalse(DramaticMomentTag.objects.exists())

    def test_a_tag_a_worn_payer_cannot_pay_is_refused_before_it_is_written(self) -> None:
        self.defiant_stand(self.fury)
        CharacterResonanceFactory(character_sheet=self.daven.sheet_data, resonance=self.fury)
        self.leave_room_for(self.daven, 0)

        refused = self.telnet(self.marek, "moment tag Daven=Defiant stand")

        self.assertIn(
            "Daven is too worn for this tag to pay. Tag another pose, or wait until Daven has "
            "recovered.",
            refused,
        )
        # Nothing was written, so the scene's cap on this moment is unspent.
        self.assertFalse(DramaticMomentTag.objects.exists())
        pool = get_or_create_fatigue_pool(self.daven.sheet_data)
        pool.set_current(ActionCategory.SOCIAL, 0)
        pool.save()
        paid = self.telnet(self.marek, "moment tag Daven=Defiant stand")
        self.assertIn("You tagged Daven with 'Defiant stand'. 10 Fury and renown awarded.", paid)

    def test_the_tag_pays_it_and_the_tagged_player_is_told_which_resonance_it_paid(self) -> None:
        self.defiant_stand()
        self.assertEqual(self.balance(self.daven, self.grief), 0)

        tagged = self.telnet(self.marek, "moment tag Daven=Defiant stand resonance=Grief")

        self.assertIn("You tagged Daven with 'Defiant stand'. 10 Grief and renown awarded.", tagged)
        self.assertEqual(self.balance(self.daven, self.grief), 10)
        self.assertIn(
            "The scene's GM tagged your pose: Defiant stand. It paid you Grief.",
            self.notices(self.daven),
        )
        self.assertNotIn("Marek", self.notices(self.daven))


class AMissionOptionThatNamesItsResonancePaysItAtOnce(_Gate):
    """The beat says what an option pays before she picks, and the roll pays it at once."""

    def setUp(self) -> None:
        super().setUp()
        celestial, primal, _abyssal = ensure_conversion_pairs()
        self.mercy = ResonanceFactory(name="Mercy", affinity=celestial)
        self.fury = ResonanceFactory(name="Fury", affinity=primal)

    def test_a_celestial_resonance_not_in_her_aura_is_shown_and_paid_with_no_pose(self) -> None:
        self.theme_row(
            self.captives,
            strength=2,
            resonance=self.mercy,
            theme_text="This option is about sparing them.",
        )
        self.check_option(self.captives)
        self.start()
        self.assertFalse(
            CharacterResonance.objects.filter(
                character_sheet=self.sheet, resonance=self.mercy
            ).exists()
        )

        beat = self.telnet(self.mira, f"mission beat {self.mission.pk}")
        self.take(1, self.success)

        self.assertIn("Pays you Mercy at once: This option is about sparing them.", beat)
        self.assertTold(self.mira, "You earned 10 Mercy.")
        self.assertNotTold(self.tomas, "You earned")
        row = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.mercy)
        self.assertEqual(row.balance, 10)

    def test_a_primal_resonance_she_does_not_have_is_neither_shown_nor_paid(self) -> None:
        self.theme_row(self.captives, strength=2, resonance=self.fury)
        self.check_option(self.captives)
        self.start()

        beat = self.telnet(self.mira, f"mission beat {self.mission.pk}")
        self.take(1, self.success)

        self.assertNotIn("Pays you Fury", beat)
        self.assertFalse(ResonanceGrant.objects.exists())
        self.assertNotTold(self.mira, "You earned")


class StaffSeeWhatMarksNeedBeforeTheyWork(JourneyCase):
    """The Required content page tells staff what to author for marks, in words, until they do."""

    WEEKLY_CONSEQUENCE = (
        "With no rows, a character's marks are never reduced within a week: the tenth mark "
        "of the week pays as much as the first, so marking every act is the best way to earn."
    )

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden5327", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def page(self) -> str:
        response = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(response.status_code, 200)
        return html.unescape(response.content.decode())

    def test_an_empty_weekly_table_reads_as_missing_with_its_consequence_until_a_row_is_added(
        self,
    ) -> None:
        self.assertIn("The weekly table of mark returns", self.page())
        self.assertIn(self.WEEKLY_CONSEQUENCE, self.page())

        WeeklyMarkReturnFactory(gained_at_least=9, percent_paid=85)

        self.assertNotIn(self.WEEKLY_CONSEQUENCE, self.page())

    def test_an_affinity_with_no_gain_fatigue_is_named_until_it_is_set(self) -> None:
        weightless = AffinityFactory(name="Weightless", gain_fatigue=0, claim_verb="relish")

        self.assertIn("A gain fatigue above 0 on every affinity", self.page())
        self.assertIn("Weightless", self.page())

        weightless.gain_fatigue = 4
        weightless.save()

        self.assertNotIn("Weightless", self.page())
