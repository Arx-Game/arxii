"""Journeys for the stories tranche (#3657, tranche 4, step 2): a GM protecting what
her story depends on and another GM asking leave to harm it, two GMs crossing their
stories at one event, a GM pacing a running beat by its clock, and a player signing
off on a stake against something she treasures. Each types what a player types or
sends what the web client sends, and asserts what each of them was told."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.boundaries.constants import TreasuredSubjectKind
from world.boundaries.factories import TreasuredSubjectFactory
from world.events.factories import EventFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.items.factories import ItemInstanceFactory
from world.narrative.models import NarrativeMessageDelivery
from world.roster.models import RosterTenure
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction, Scene
from world.societies.constants import RenownRisk
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.stories.constants import (
    BeatKind,
    BeatOutcome,
    CrossoverInviteStatus,
    CustodyClearanceStatus,
    StakeSubjectKind,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import (
    CrossoverInvite,
    CustodyClearance,
    EpisodeScene,
    StoryProtectedSubject,
    TreasuredSignoff,
)


class _TwoTables(JourneyCase):
    """Ravenna leads "The Lantern Debt" for Ysmay from her table; Hobb leads "The Dock
    Ledger" from his own. Both are Junior GMs. Marrow is staff."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.ravenna = self.make_player("Ravenna", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        staff_account = self.marrow.db_account
        staff_account.is_staff = True
        staff_account.save()
        self.watch(self.ysmay, self.hobb, self.ravenna, self.marrow)

        self.ravenna_gm = GMProfileFactory(account=self.ravenna.db_account, level=GMLevel.JUNIOR)
        self.ravenna_table = GMTableFactory(gm=self.ravenna_gm, name="Ravenna's Table")
        # Ysmay sits at Ravenna's table, which is what makes Ravenna the GM of a scene
        # she starts with Ysmay present.
        GMTableMembershipFactory(
            table=self.ravenna_table, persona=self.ysmay.sheet_data.primary_persona
        )
        self.story = StoryFactory(
            title="The Lantern Debt",
            scope=StoryScope.CHARACTER,
            character_sheet=self.ysmay.sheet_data,
            primary_table=self.ravenna_table,
        )
        chapter = ChapterFactory(story=self.story, title="Debts", order=1, is_active=True)
        self.episode = EpisodeFactory(
            chapter=chapter, title="The First Knock", order=1, is_active=True
        )
        self.beat = BeatFactory(
            episode=self.episode,
            kind=BeatKind.SITUATION,
            player_hint="Find out who knocked",
            clock_size=2,
            risk=RenownRisk.LOW,
        )
        StoryProgressFactory(
            story=self.story, character_sheet=self.ysmay.sheet_data, current_episode=self.episode
        )

        self.hobb_gm = GMProfileFactory(account=self.hobb.db_account, level=GMLevel.JUNIOR)
        self.hobb_table = GMTableFactory(gm=self.hobb_gm, name="Hobb's Table")
        self.ledger = StoryFactory(
            title="The Dock Ledger",
            primary_table=self.hobb_table,
            owners=[self.hobb.db_account],
        )
        self.ledger_episode = EpisodeFactory(
            chapter__story=self.ledger, title="Counting the Crates", order=1, is_active=True
        )

    def queued_for(self, character, body: str) -> bool:
        """Whether ``character`` has a queued copy of the notification ``body`` (the
        live push goes to connected sessions, which a harness character has none of)."""
        return NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=character.sheet_data, message__body=body
        ).exists()


class ProtectingWhatTheStoryNeeds(_TwoTables):
    def test_another_gm_asks_leave_to_harm_her_and_is_refused_then_cleared_by_staff(  # noqa: PLR0915 - one clearance lifecycle, read top to bottom
        self,
    ) -> None:
        hobb_name = self.hobb.db_account.username
        ravenna_name = self.ravenna.db_account.username
        self.assertIn(
            "You do not own or lead this story.",
            self.telnet(self.hobb, f"story protect {self.story.pk} list"),
        )
        self.assertIn(
            "You do not own or lead this story.",
            self.telnet(self.hobb, f"story protect {self.story.pk} add personal_jeopardy=Ysmay"),
        )
        # Staff, and a plain owner of the story, stand where the Lead GM stands.
        empty = f"No protected subjects for story #{self.story.pk}."
        self.assertIn(empty, self.telnet(self.marrow, f"story protect {self.story.pk} list"))
        self.story.owners.add(self.ysmay.db_account)
        self.assertIn(empty, self.telnet(self.ysmay, f"story protect {self.story.pk} list"))
        self.story.owners.remove(self.ysmay.db_account)

        told = self.telnet(
            self.ravenna,
            f"story protect {self.story.pk} add personal_jeopardy=Ysmay notes=Hers to lose",
        )
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertIn(f"Protected #{protected.pk}: Ysmay (Personal jeopardy).", told)
        self.assertEqual(protected.subject_sheet_id, self.ysmay.sheet_data.pk)
        self.assertEqual(protected.notes, "Hers to lose")
        told = self.telnet(self.ravenna, f"story protect {self.story.pk} list")
        self.assertIn(f"Protected subjects for The Lantern Debt (#{self.story.pk}):", told)
        self.assertIn(f"  [{protected.pk}] Personal jeopardy: Ysmay (active)", told)

        self.assertIn(
            "You must have a GM profile to do that.",
            self.telnet(self.ysmay, "story clearance request personal_jeopardy=Ysmay scope=harm"),
        )
        told = self.telnet(
            self.hobb,
            "story clearance request personal_jeopardy=Ysmay scope=harm "
            f"story={self.ledger.pk} message=The ledger names her",
        )
        clearance = CustodyClearance.objects.get(protected_subject=protected)
        self.assertIn(f"Requested harm clearance (1 new):\n  [{clearance.pk}] Ysmay", told)
        self.assertEqual(clearance.requesting_story_id, self.ledger.pk)
        self.assertEqual(clearance.message, "The ledger names her")
        self.assertTrue(
            self.queued_for(self.ravenna, f"{hobb_name} has requested harm clearance for Ysmay.")
        )
        self.assertIn(
            "You already have a live clearance request for every matching subject at this scope.",
            self.telnet(self.hobb, "story clearance request personal_jeopardy=Ysmay scope=harm"),
        )

        row = f"  [{clearance.pk}] harm — Ysmay — pending (requested by {hobb_name})"
        self.assertIn(row, self.telnet(self.ravenna, "story clearance list pending"))
        self.assertIn(row, self.telnet(self.hobb, "story clearance list"))
        self.assertIn(
            "No custody clearances to show.", self.telnet(self.ysmay, "story clearance list")
        )

        self.assertIn(
            "Only the protecting story's Lead GM may decide this clearance.",
            self.telnet(self.hobb, f"story clearance grant {clearance.pk}"),
        )
        # Fresh and pending: not yet stale enough to go over the custodian's head.
        self.assertIn(
            "This clearance is not in a state that allows that action.",
            self.telnet(self.hobb, f"story clearance escalate {clearance.pk}"),
        )
        told = self.telnet(
            self.ravenna, f"story clearance deny {clearance.pk} note=Not in this chapter"
        )
        self.assertIn(f"Denied clearance #{clearance.pk} (harm).", told)
        clearance.refresh_from_db()
        self.assertEqual(clearance.response_note, "Not in this chapter")
        self.assertTrue(
            self.queued_for(
                self.hobb, f"{ravenna_name} denied your harm clearance request for Ysmay."
            )
        )
        # Denied, it leaves the pending list; staff see every row regardless.
        self.assertIn(
            "No custody clearances to show.", self.telnet(self.hobb, "story clearance list pending")
        )
        self.assertIn(
            f"  [{clearance.pk}] harm — Ysmay — denied",
            self.telnet(self.hobb, "story clearance list"),
        )
        self.assertIn(
            f"  [{clearance.pk}] harm — Ysmay — denied",
            self.telnet(self.marrow, "story clearance list"),
        )
        self.assertIn(
            "You must have a GM profile to do that.",
            self.telnet(self.marrow, f"story clearance grant {clearance.pk}"),
        )
        self.assertIn(
            "Only the requesting GM may escalate this clearance.",
            self.telnet(self.ravenna, f"story clearance escalate {clearance.pk}"),
        )
        self.assertIn(
            f"Escalated clearance #{clearance.pk} to staff review.",
            self.telnet(self.hobb, f"story clearance escalate {clearance.pk}"),
        )
        self.assertTrue(
            self.queued_for(
                self.ravenna,
                f"{hobb_name} escalated their harm clearance request for Ysmay to staff review.",
            )
        )
        self.assertIn(
            "Only staff may resolve an escalated custody clearance.",
            self.telnet(self.ravenna, f"story clearance resolve {clearance.pk} grant"),
        )
        self.assertIn(
            "Usage: story clearance resolve <id> grant|deny [note=<text>]",
            self.telnet(self.marrow, f"story clearance resolve {clearance.pk}"),
        )
        self.assertIn(
            f"Granted (staff) clearance #{clearance.pk} (harm).",
            self.telnet(self.marrow, f"story clearance resolve {clearance.pk} grant note=Ruled"),
        )
        clearance.refresh_from_db()
        self.assertEqual(clearance.status, CustodyClearanceStatus.GRANTED)
        self.assertEqual(clearance.staff_resolver_id, self.marrow.db_account.pk)
        self.assertTrue(
            self.queued_for(
                self.hobb,
                f"Staff ({self.marrow.db_account.username}) granted your escalated harm "
                "clearance request for Ysmay.",
            )
        )
        # The web reads the same row.
        response = self.api(self.hobb.db_account).get("/api/custody-clearances/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data["results"]}
        self.assertEqual(rows[clearance.pk]["status"], CustodyClearanceStatus.GRANTED)
        self.assertEqual(rows[clearance.pk]["response_note"], "Ruled")

        self.assertIn(
            "Only the protecting story's Lead GM or staff may revoke this clearance.",
            self.telnet(self.hobb, f"story clearance revoke {clearance.pk}"),
        )
        self.assertIn(
            f"Revoked clearance #{clearance.pk}.",
            self.telnet(self.ravenna, f"story clearance revoke {clearance.pk}"),
        )
        self.assertTrue(
            self.queued_for(self.hobb, f"{ravenna_name} revoked your harm clearance for Ysmay.")
        )
        self.assertIn(
            "This clearance is not in a state that allows that action.",
            self.telnet(self.ravenna, f"story clearance revoke {clearance.pk}"),
        )

        told = self.telnet(self.ravenna, f"story protect {self.story.pk} remove {protected.pk}")
        self.assertIn(f"Deactivated protection #{protected.pk} (Ysmay).", told)
        self.assertIn(
            f"  [{protected.pk}] Personal jeopardy: Ysmay (inactive)",
            self.telnet(self.ravenna, f"story protect {self.story.pk} list"),
        )
        self.assertIn(
            "No active protected subject matches that identity.",
            self.telnet(self.hobb, "story clearance request personal_jeopardy=Ysmay scope=appear"),
        )

    def test_the_refusals_name_what_was_wrong(self) -> None:
        self.assertIn("Usage:", self.telnet(self.ravenna, f"story protect {self.story.pk}"))
        self.assertIn(
            "No character found named 'Nobody'.",
            self.telnet(self.ravenna, f"story protect {self.story.pk} add npc_fate=Nobody"),
        )
        self.assertIn(
            "Provide exactly one subject kind",
            self.telnet(self.ravenna, f"story protect {self.story.pk} add notes=Nothing named"),
        )
        self.assertIn(
            "No protected subject with that ID exists for this story.",
            self.telnet(self.ravenna, f"story protect {self.story.pk} remove 999999"),
        )
        self.telnet(self.ravenna, f"story protect {self.story.pk} add custom=The Lantern's lamp")
        protected = StoryProtectedSubject.objects.get(story=self.story)
        self.assertEqual(protected.subject_kind, StakeSubjectKind.CUSTOM)

        self.assertIn(
            "scope is required and must be one of: appear, harm, remove.",
            self.telnet(self.hobb, f"story clearance request protected={protected.pk} scope=fly"),
        )
        self.assertIn(
            "Provide exactly one of protected=<id>, or a subject kind",
            self.telnet(self.hobb, "story clearance request scope=appear"),
        )
        self.assertIn(
            "Provide exactly one of protected=<id>, or a subject kind",
            self.telnet(
                self.hobb,
                f"story clearance request protected={protected.pk} custom=The Lantern's lamp "
                "scope=appear",
            ),
        )
        told = self.telnet(
            self.hobb, f"story clearance request protected={protected.pk} scope=appear"
        )
        clearance = CustodyClearance.objects.get(protected_subject=protected)
        self.assertIn(
            f"Requested appear clearance (1 new):\n  [{clearance.pk}] The Lantern's lamp", told
        )
        self.assertIn(
            "You already have a live clearance request for this subject at this scope.",
            self.telnet(
                self.hobb, f"story clearance request protected={protected.pk} scope=appear"
            ),
        )
        self.assertIn(
            "Usage: story clearance grant|deny <id> [note=<text>]",
            self.telnet(self.ravenna, "story clearance grant soon"),
        )
        self.assertIn(
            "No custody clearance with that ID exists.",
            self.telnet(self.ravenna, "story clearance grant 999999"),
        )
        self.assertIn(
            f"Granted clearance #{clearance.pk} (appear).",
            self.telnet(self.ravenna, f"story clearance grant {clearance.pk}"),
        )
        self.assertIn(
            "This clearance is not in a state that allows that action.",
            self.telnet(self.ravenna, f"story clearance deny {clearance.pk}"),
        )
        # Staff may take a granted clearance back in the custodian's place.
        self.assertIn(
            f"Revoked clearance #{clearance.pk}.",
            self.telnet(self.marrow, f"story clearance revoke {clearance.pk}"),
        )
        clearance.refresh_from_db()
        self.assertIsNotNone(clearance.revoked_at)

    def test_every_kind_of_subject_and_a_request_that_fans_out(self) -> None:
        lamp = ItemInstanceFactory()
        OrganizationFactory(name="The Silver Rose")
        SocietyFactory(name="The Undersea Court")
        OrganizationFactory(name="The Ashfall Concord")
        SocietyFactory(name="The Ashfall Concord")
        other_beat = BeatFactory(episode=self.ledger_episode)

        def add(args: str) -> str:
            return self.telnet(self.ravenna, f"story protect {self.story.pk} add {args}")

        self.assertIn("Protected #", add(f"item={lamp.pk}"))
        self.assertIn("No item instance with that ID exists.", add("item=999999"))
        self.assertIn("item=<subject-ref> must be an item instance ID.", add("item=lamp"))
        self.assertIn("The Silver Rose (Faction relationship).", add("faction=The Silver Rose"))
        self.assertIn(
            "The Undersea Court (Faction relationship).", add("faction=The Undersea Court")
        )
        self.assertIn(
            "No organization or society named 'The Nobodies'.", add("faction=The Nobodies")
        )
        self.assertIn(
            "'The Ashfall Concord' matches both an organization and a society — specify "
            "org=<name> or society=<name>.",
            add("faction=The Ashfall Concord"),
        )
        self.assertIn("Protected #", add("org=The Ashfall Concord"))
        self.assertIn("Protected #", add("society=The Ashfall Concord"))
        self.assertIn("No society named 'The Silver Rose'.", add("society=The Silver Rose"))
        self.assertIn("The Old Well (Location).", add("location=The Old Well"))
        self.assertIn("Provide exactly one subject kind", add("custom=Ring location=Well"))
        self.assertIn(
            "That beat does not belong to this story.",
            add(f"custom=A Ring beat={other_beat.pk}"),
        )
        self.assertIn("No beat with that ID exists.", add("custom=A Ring beat=999999"))
        told = add(f"custom=A Ring beat={self.beat.pk} notes=Load-bearing for the finale")
        ring = StoryProtectedSubject.objects.get(story=self.story, subject_label="A Ring")
        self.assertIn(f"Protected #{ring.pk}: A Ring (Custom (trust-gated)).", told)
        self.assertEqual(ring.beat_id, self.beat.pk)
        self.assertEqual(ring.notes, "Load-bearing for the finale")
        self.assertIn(
            f"  [{ring.pk}] Custom (trust-gated): A Ring beat=#{self.beat.pk} (active)",
            self.telnet(self.ravenna, f"story protect {self.story.pk} list"),
        )
        kinds = set(
            StoryProtectedSubject.objects.filter(story=self.story).values_list(
                "subject_kind", flat=True
            )
        )
        self.assertEqual(
            kinds,
            {
                StakeSubjectKind.ITEM,
                StakeSubjectKind.FACTION,
                StakeSubjectKind.LOCATION,
                StakeSubjectKind.CUSTOM,
            },
        )

        # Two stories protect the same person; one request by identity reaches both
        # custodians, and a second request skips the one already asked.
        self.telnet(self.ravenna, f"story protect {self.story.pk} add personal_jeopardy=Ysmay")
        asker = GMProfileFactory(account=self.marrow.db_account, level=GMLevel.JUNIOR)
        told = self.telnet(
            self.marrow, "story clearance request personal_jeopardy=Ysmay scope=appear"
        )
        self.assertIn("Requested appear clearance (1 new):", told)
        self.telnet(self.hobb, f"story protect {self.ledger.pk} add personal_jeopardy=Ysmay")
        told = self.telnet(
            self.marrow, "story clearance request personal_jeopardy=Ysmay scope=appear"
        )
        self.assertIn("Requested appear clearance (1 new):", told)
        self.assertIn("(1 already had a live request, skipped)", told)
        self.assertEqual(CustodyClearance.objects.filter(requested_by=asker).count(), 2)
        hobbs = CustodyClearance.objects.get(
            requested_by=asker, protected_subject__story=self.ledger
        )
        # Denied by its custodian, escalated, and refused by staff this time.
        self.telnet(self.hobb, f"story clearance deny {hobbs.pk} note=Not in my ledger")
        self.assertIn(
            f"Escalated clearance #{hobbs.pk} to staff review.",
            self.telnet(self.marrow, f"story clearance escalate {hobbs.pk}"),
        )
        # Marrow asked for it, so Marrow is also a requester here; staff still rule.
        self.assertIn(
            f"Denied (staff) clearance #{hobbs.pk} (appear).",
            self.telnet(self.marrow, f"story clearance resolve {hobbs.pk} deny note=Ruled against"),
        )
        hobbs.refresh_from_db()
        self.assertEqual(hobbs.status, CustodyClearanceStatus.DENIED)
        self.assertEqual(hobbs.response_note, "Ruled against")


class CrossingStoriesAtAnEvent(_TwoTables):
    def test_she_invites_his_story_to_her_event_and_he_declines_then_accepts(self) -> None:
        event = EventFactory(name="The Harvest Fair")
        scene = SceneFactory(event=event, room=self.lantern, is_active=True)
        self.assertIn(
            "You must have a GM profile to do that.",
            self.telnet(self.ysmay, f"story crossover invite {event.pk} story={self.ledger.pk}"),
        )
        self.assertIn(
            "No event with that ID exists.",
            self.telnet(self.ravenna, f"story crossover invite 999999 story={self.ledger.pk}"),
        )
        # An episode of her own story is not his to bring.
        self.assertIn(
            "This crossover invite is not in a state that allows that action.",
            self.telnet(
                self.ravenna,
                f"story crossover invite {event.pk} story={self.ledger.pk} "
                f"episode={self.episode.pk}",
            ),
        )

        told = self.telnet(
            self.ravenna,
            f"story crossover invite {event.pk} story={self.ledger.pk} "
            f"episode={self.ledger_episode.pk} message=Bring your crates",
        )
        invite = CrossoverInvite.objects.get(event=event)
        self.assertIn(
            f"Crossover invite #{invite.pk} sent: The Dock Ledger invited to event "
            '"The Harvest Fair" (status: pending).',
            told,
        )
        self.assertEqual(invite.message, "Bring your crates")
        self.assertIn(
            "This crossover invite is not in a state that allows that action.",
            self.telnet(self.ravenna, f"story crossover invite {event.pk} story={self.ledger.pk}"),
        )
        self.assertIn(
            f'  [{invite.pk}] sent — The Dock Ledger / event "The Harvest Fair" (pending)',
            self.telnet(self.ravenna, "story crossover list"),
        )
        self.assertIn(
            f'  [{invite.pk}] received — The Dock Ledger / event "The Harvest Fair" (pending)',
            self.telnet(self.hobb, "story crossover list pending"),
        )
        self.assertIn(
            "You have no crossover invites.", self.telnet(self.ysmay, "story crossover list")
        )

        self.assertIn(
            "You are not authorized to act on this crossover invite.",
            self.telnet(self.ravenna, f"story crossover accept {invite.pk}"),
        )
        self.assertIn(
            "You are not authorized to act on this crossover invite.",
            self.telnet(self.hobb, f"story crossover withdraw {invite.pk}"),
        )
        self.assertIn(
            f"Crossover invite #{invite.pk} declined.",
            self.telnet(self.hobb, f"story crossover decline {invite.pk} note=Not this week"),
        )
        invite.refresh_from_db()
        self.assertEqual(invite.status, CrossoverInviteStatus.DECLINED)
        self.assertEqual(invite.response_note, "Not this week")

        self.telnet(self.ravenna, f"story crossover invite {event.pk} story={self.ledger.pk}")
        second = CrossoverInvite.objects.get(event=event, status=CrossoverInviteStatus.PENDING)
        # No episode was proposed, so he has to name one.
        self.assertIn(
            "This crossover invite is not in a state that allows that action.",
            self.telnet(self.hobb, f"story crossover accept {second.pk}"),
        )
        told = self.telnet(
            self.hobb,
            f"story crossover accept {second.pk} episode={self.ledger_episode.pk} "
            "note=Crates it is",
        )
        self.assertIn(
            f"Crossover invite #{second.pk} accepted: The Dock Ledger linked to the shared event.",
            told,
        )
        # The event's scene is already running, so his episode is linked into it now.
        self.assertTrue(
            EpisodeScene.objects.filter(episode=self.ledger_episode, scene=scene).exists()
        )
        self.assertIn(
            "This crossover invite is not in a state that allows that action.",
            self.telnet(self.ravenna, f"story crossover withdraw {second.pk}"),
        )
        response = self.api(self.hobb.db_account).get("/api/crossover-invites/")
        self.assertEqual(response.status_code, 200)
        statuses = {row["id"]: row["status"] for row in response.data["results"]}
        self.assertEqual(statuses[invite.pk], CrossoverInviteStatus.DECLINED)
        self.assertEqual(statuses[second.pk], CrossoverInviteStatus.ACCEPTED)

    def test_she_takes_an_invitation_back(self) -> None:
        event = EventFactory(name="The Harvest Fair")
        self.telnet(self.ravenna, f"story crossover invite {event.pk} story={self.ledger.pk}")
        invite = CrossoverInvite.objects.get(event=event)
        self.assertIn(
            f"Crossover invite #{invite.pk} withdrawn.",
            self.telnet(self.ravenna, f"story crossover withdraw {invite.pk}"),
        )
        self.assertIn(
            f'  [{invite.pk}] received — The Dock Ledger / event "The Harvest Fair" (withdrawn)',
            self.telnet(self.hobb, "story crossover list"),
        )
        self.assertNotIn(f"[{invite.pk}]", self.telnet(self.hobb, "story crossover list pending"))
        self.assertIn(
            "This crossover invite is not in a state that allows that action.",
            self.telnet(self.hobb, f"story crossover accept {invite.pk}"),
        )
        self.assertIn(
            "No crossover invite with that ID exists.",
            self.telnet(self.hobb, "story crossover accept 999999"),
        )


class PacingABeatByItsClock(_TwoTables):
    def test_the_gm_spends_the_clock_and_the_beat_expires_when_it_fills(self) -> None:
        self.assertIn(
            "Only the scene's GM or staff can do that.", self.telnet(self.ravenna, "story clock")
        )
        # A line spoken before the scene begins is the case that broke this: the room
        # had cached "no scene", and the new scene went unseen by every lookup after.
        self.telnet(self.ysmay, "say Quiet in here.")
        self.telnet(self.ravenna, "scene start The Knock")
        scene = Scene.objects.get(name="The Knock")
        self.telnet(self.ysmay, "say Someone's at the door.")
        self.assertTrue(
            Interaction.objects.filter(scene=scene, content="Someone's at the door.").exists()
        )
        self.assertIn(
            "This scene has no clock to advance.", self.telnet(self.ravenna, "story clock")
        )
        run = self.web(self.ravenna, "run_beat", beat_id=self.beat.pk).detail
        self.assertTrue(run.success, run.message)
        self.assertEqual(run.data["clock"], {"size": 2, "filled": 0})

        self.assertIn(
            "Only the scene's GM or staff can do that.", self.telnet(self.ysmay, "story clock")
        )
        # Hobb owns a table too, but none of his players is here, so the scene is
        # not his to pace.
        self.assertIn(
            "Only the scene's GM or staff can do that.", self.telnet(self.hobb, "story clock")
        )
        self.assertIn(
            "Usage: story clock [n], n a whole number of at least 1.",
            self.telnet(self.ravenna, "story clock x"),
        )
        self.assertIn("The clock advances: 1/2.", self.telnet(self.ravenna, "story clock"))
        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.ravenna, "story clock")
        self.assertIn("The clock fills: 2/2. Time is up.", told)
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.EXPIRED)
        self.assertIn(
            f"[{self.beat.pk}] Find out who knocked (expired)",
            self.telnet(self.ysmay, f"story beats {self.episode.pk}"),
        )
        self.assertIn(
            "This scene has no clock to advance.", self.telnet(self.ravenna, "story clock")
        )


class SigningOffOnATreasure(_TwoTables):
    def test_she_signs_off_on_a_stake_against_the_lantern_before_the_beat_runs(self) -> None:
        tenure = RosterTenure.objects.get(
            roster_entry__character_sheet=self.ysmay.sheet_data, end_date=None
        )
        treasure = TreasuredSubjectFactory(
            owner=tenure, subject_kind=TreasuredSubjectKind.CUSTOM, subject_label="The Lantern"
        )
        StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="The Lantern",
            player_summary="The Lantern may burn.",
        )
        needed = (
            f"  [{self.beat.pk}] Find out who knocked (unsatisfied)\n"
            "      SIGN-OFF NEEDED: The Lantern"
        )
        self.assertIn(needed, self.telnet(self.ysmay, f"story beats {self.episode.pk}"))

        self.assertIn(
            "Usage: story signoff <beat-id> <subject> [withdraw].",
            self.telnet(self.ysmay, f"story signoff {self.beat.pk}"),
        )
        self.assertIn(
            "No beat with that ID exists.",
            self.telnet(self.ysmay, "story signoff 999999 The Lantern"),
        )
        # Not his treasure, so nothing of his is pending on the beat.
        self.assertIn(
            f"No pending sign-off for 'The Lantern' on beat {self.beat.pk}.",
            self.telnet(self.hobb, f"story signoff {self.beat.pk} The Lantern"),
        )
        self.assertIn(
            f"Signed off: The Lantern on beat {self.beat.pk}.",
            self.telnet(self.ysmay, f"story signoff {self.beat.pk} the lantern"),
        )
        signoff = TreasuredSignoff.objects.get(beat=self.beat)
        self.assertTrue(signoff.active)
        self.assertNotIn(
            "SIGN-OFF NEEDED", self.telnet(self.ysmay, f"story beats {self.episode.pk}")
        )
        # Nobody else can take her sign-off back, not even by its exact name.
        self.assertIn(
            f"No active sign-off for 'The Lantern' on beat {self.beat.pk}.",
            self.telnet(self.hobb, f"story signoff {self.beat.pk} The Lantern withdraw"),
        )
        signoff.refresh_from_db()
        self.assertTrue(signoff.active)

        self.assertIn(
            f"Withdrawn: The Lantern on beat {self.beat.pk}.",
            self.telnet(self.ysmay, f"story signoff {self.beat.pk} The Lantern withdraw"),
        )
        self.assertIn(needed, self.telnet(self.ysmay, f"story beats {self.episode.pk}"))
        self.assertIn(
            f"No active sign-off for 'The Lantern' on beat {self.beat.pk}.",
            self.telnet(self.ysmay, f"story signoff {self.beat.pk} The Lantern withdraw"),
        )

        # With her sign-off in place (this time by its id), running the beat locks
        # the stakes in for her.
        self.telnet(self.ravenna, "scene start The Knock")
        self.telnet(self.ysmay, "say I am here for it.")
        self.assertIn(
            f"Signed off: The Lantern on beat {self.beat.pk}.",
            self.telnet(self.ysmay, f"story signoff {self.beat.pk} {treasure.pk}"),
        )
        run = self.web(self.ravenna, "run_beat", beat_id=self.beat.pk).detail
        self.assertTrue(run.success, run.message)
        activation = run.data["stakes_activation"]
        # Everyone present who is not the GM commits to the run; she is among them.
        self.assertIn(self.ysmay.sheet_data.pk, activation["participant_sheet_ids"])
        self.assertNotIn(self.ravenna.sheet_data.pk, activation["participant_sheet_ids"])
