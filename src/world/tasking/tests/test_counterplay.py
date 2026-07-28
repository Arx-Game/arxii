"""Spy-vs-spy counterplay tests (#2820 phase 4)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.assets.factories import NPCAssetFactory
from world.assets.models import NPCAsset
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.locations.factories import LocationOwnershipFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.secrets.constants import SecretProvenance
from world.secrets.models import SecretKnowledge
from world.societies.factories import OrganizationFactory
from world.tasking.counterplay_services import (
    ConsentBlockedError,
    clear_room_listeners,
    detect_listeners,
    flip_listener,
    plant_red_herring,
    suppress_listener,
)
from world.tasking.listener_services import (
    collect_harvest,
    create_listener_post,
    listener_sweep,
)
from world.traits.factories import CheckOutcomeFactory


class CounterplayTestBase(TestCase):
    """An NPC-network listener (memberless org holds the agent) — always-on target."""

    @classmethod
    def setUpTestData(cls):
        CheckTypeFactory(name="Intimidation")
        CheckTypeFactory(name="Seduction")
        CheckTypeFactory(name="Perception")
        cls.room = RoomProfileFactory()
        cls.npc_org = OrganizationFactory()  # no PC members: staff-authored network
        cls.asset = NPCAssetFactory(promoter_persona=None, promoter_org=cls.npc_org)
        cls.handler = PersonaFactory()
        cls.actor = PersonaFactory()
        cls.win = CheckOutcomeFactory(name="counterplay win", success_level=2)
        cls.lose = CheckOutcomeFactory(name="counterplay lose", success_level=-1)

    def setUp(self):
        # Handler is an org... memberless org: use a persona-held sibling row
        # to authorize the posting instead. Simpler: post via a member-of-org
        # path is unavailable, so the handler personally co-owns the agent.
        self.handler_row = NPCAsset.objects.filter(
            promoter_persona=self.handler, asset_persona=self.asset.asset_persona
        ).first()
        if self.handler_row is None:
            self.handler_row = NPCAssetFactory(
                promoter_persona=self.handler, asset_persona=self.asset.asset_persona
            )
        self.post = create_listener_post(self.handler_row, self.room, self.handler)
        self._move(self.actor)

    def _move(self, persona):
        character = persona.character_sheet.character
        character.db_location = self.room.objectdb
        character.save()


class SuppressTests(CounterplayTestBase):
    def test_suppress_freezes_the_meter_silently(self):
        with force_check_outcome(self.win):
            self.assertTrue(suppress_listener(self.actor, self.post))
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.suppressed_until)
        listener_sweep()
        self.post.refresh_from_db()
        self.assertEqual(self.post.buzz, 0)
        self.assertIsNotNone(self.post.last_sweep_at)

    def test_failed_suppress_changes_nothing(self):
        with force_check_outcome(self.lose):
            self.assertFalse(suppress_listener(self.actor, self.post))
        self.post.refresh_from_db()
        self.assertIsNone(self.post.suppressed_until)


class FlipTests(CounterplayTestBase):
    def test_flip_grants_co_ownership_and_control(self):
        with force_check_outcome(self.win):
            self.assertTrue(flip_listener(self.actor, self.post))
        self.post.refresh_from_db()
        self.assertEqual(self.post.flipped_controller, self.actor)
        self.assertTrue(
            NPCAsset.objects.filter(
                promoter_persona=self.actor,
                asset_persona=self.asset.asset_persona,
            ).exists()
        )

    def test_flipped_post_delivers_planted_clue_not_real_catch(self):
        with force_check_outcome(self.win):
            flip_listener(self.actor, self.post)
        mark = RosterEntryFactory()
        clue = plant_red_herring(
            self.actor,
            self.post,
            subject_sheet=mark.character_sheet,
            content="PLACEHOLDER they meet a foreign paymaster at dusk.",
        )
        self.assertEqual(clue.target_secret.provenance, SecretProvenance.ACCUSATION)

        self.post.threshold = 1
        self.post.save(update_fields=["threshold"])
        listener_sweep()
        harvest = self.post.harvests.get()
        self.assertIsNone(harvest.secret)
        self.assertEqual(harvest.planted_clue, clue)

        handler_entry = RosterEntryFactory(character_sheet=self.handler.character_sheet)
        self._move(self.handler)
        collected = collect_harvest(self.post, self.handler)
        self.assertEqual(collected, clue)
        self.assertTrue(
            SecretKnowledge.objects.filter(
                roster_entry=handler_entry, secret=clue.target_secret
            ).exists()
        )

    def test_plant_requires_control(self):
        from world.tasking.counterplay_services import CounterplayError

        mark = RosterEntryFactory()
        with self.assertRaises(CounterplayError):
            plant_red_herring(
                self.actor,
                self.post,
                subject_sheet=mark.character_sheet,
                content="no control, no lies",
            )


class DetectAndClearTests(CounterplayTestBase):
    def test_detect_reveals_agent_name_only(self):
        with force_check_outcome(self.win):
            revealed = detect_listeners(self.actor, self.room)
        self.assertEqual(len(revealed), 1)
        self.assertEqual(revealed[0]["post_id"], self.post.pk)
        self.assertNotIn("handler", revealed[0])

    def test_failed_detect_reveals_nothing(self):
        with force_check_outcome(self.lose):
            self.assertEqual(detect_listeners(self.actor, self.room), [])

    def test_room_owner_clears_listeners(self):
        from world.tasking.counterplay_services import CounterplayError

        with self.assertRaises(CounterplayError):
            clear_room_listeners(self.actor, self.room)  # no standing
        LocationOwnershipFactory(on_room=True, room_profile=self.room, holder_persona=self.actor)
        cleared = clear_room_listeners(self.actor, self.room)
        self.assertEqual(cleared, 1)
        self.post.assignment.refresh_from_db()
        self.assertFalse(self.post.assignment.is_active)


class ConsentBoundaryTests(TestCase):
    """Moves against a PC-run network route through the espionage category."""

    @classmethod
    def setUpTestData(cls):
        from world.seeds.consent import seed_social_consent_categories

        seed_social_consent_categories()
        CheckTypeFactory(name="Intimidation")
        cls.room = RoomProfileFactory()
        # PC-owned listener: the owner has a live tenure (a real player).
        cls.owner_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=cls.owner_entry, player_number=1)
        cls.owner = cls.owner_entry.character_sheet.primary_persona
        cls.asset = NPCAssetFactory(promoter_persona=cls.owner)
        cls.post = create_listener_post(cls.asset, cls.room, cls.owner)
        cls.actor_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=cls.actor_entry, player_number=1)
        cls.actor = cls.actor_entry.character_sheet.primary_persona

    def test_default_opt_in_blocks_espionage_against_pc_network(self):
        character = self.actor.character_sheet.character
        character.db_location = self.room.objectdb
        character.save()
        with self.assertRaises(ConsentBlockedError):
            suppress_listener(self.actor, self.post)
