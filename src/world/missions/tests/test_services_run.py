"""Tests for the Phase-5a accept/share services.

``accept_mission`` is the canonical "create live run from offered template"
service: it creates the instance, the holder participant, enters the entry
node (Phase-3 ``enter_node``), and sets the giver cooldown so subsequent
``offer_missions`` calls exclude the same template until the cooldown
elapses. ``share_mission`` adds non-holder participants — sharees never get
their own cooldown row (design §10).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionGiverStanding,
    MissionInstance,
    MissionNodeSnapshot,
    MissionParticipant,
)
from world.missions.services.availability import offer_missions
from world.missions.services.run import accept_mission, share_mission


def _make_character(level: int = 1) -> "object":
    """A Character ObjectDB with a CharacterSheet at the given level."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    if level > 0:
        CharacterClassLevelFactory(
            character=character,
            character_class=CharacterClassFactory(),
            level=level,
        )
        sheet.invalidate_class_level_cache()
    return character


class AcceptMissionTests(TestCase):
    """accept_mission creates the run, holder, entry-node snapshot, and cooldown."""

    def setUp(self) -> None:
        self.giver = MissionGiverFactory()
        self.template = MissionTemplateFactory(name="accept-t", cooldown=timedelta(days=2))
        self.entry_node = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.giver.templates.add(self.template)
        self.character = _make_character()

    def test_accept_creates_instance_holder_and_snapshot(self) -> None:
        instance = accept_mission(self.giver, self.template, self.character)

        self.assertEqual(instance.template, self.template)
        self.assertEqual(instance.status, MissionStatus.ACTIVE)
        # current_node was set by enter_node.
        self.assertEqual(instance.current_node, self.entry_node)

        participants = list(MissionParticipant.objects.filter(instance=instance))
        self.assertEqual(len(participants), 1)
        self.assertTrue(participants[0].is_contract_holder)
        self.assertEqual(participants[0].character, self.character)

        snaps = MissionNodeSnapshot.objects.filter(instance=instance, node=self.entry_node)
        self.assertEqual(snaps.count(), 1)

    def test_accept_starts_cooldown_and_excludes_template_from_offers(self) -> None:
        # Before accept: offer surfaces this template.
        self.assertIn(self.template, offer_missions(self.giver, self.character, count=5))

        accept_mission(self.giver, self.template, self.character)

        # Cooldown row exists with future available_at.
        cd = MissionGiverStanding.objects.get(giver=self.giver, character=self.character)
        self.assertGreater(cd.available_at, timezone.now())

        # offer_missions now returns no offers from this giver for this char.
        self.assertEqual(offer_missions(self.giver, self.character, count=5), [])

    def test_accept_uses_upsert_for_existing_cooldown_row(self) -> None:
        # Pre-existing cooldown (e.g. from a prior, expired run on this giver).
        MissionGiverStanding.objects.create(
            giver=self.giver,
            character=self.character,
            available_at=timezone.now() - timedelta(days=1),
        )
        accept_mission(self.giver, self.template, self.character)
        rows = MissionGiverStanding.objects.filter(giver=self.giver, character=self.character)
        self.assertEqual(rows.count(), 1)
        self.assertGreater(rows.first().available_at, timezone.now())


class ShareMissionTests(TestCase):
    """share_mission adds a non-holder participant; no cooldown side effect."""

    def setUp(self) -> None:
        self.giver = MissionGiverFactory()
        self.template = MissionTemplateFactory(name="share-t")
        MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.giver.templates.add(self.template)
        self.holder = _make_character()
        self.instance = accept_mission(self.giver, self.template, self.holder)

    def test_share_adds_non_holder_participant(self) -> None:
        other = _make_character()
        added = share_mission(self.instance, other)

        self.assertEqual(added.character, other)
        self.assertFalse(added.is_contract_holder)
        self.assertEqual(added.instance, self.instance)

        participants = MissionParticipant.objects.filter(instance=self.instance)
        self.assertEqual(participants.count(), 2)
        holders = participants.filter(is_contract_holder=True)
        self.assertEqual(holders.count(), 1)
        self.assertEqual(holders.first().character, self.holder)

    def test_sharee_gets_no_giver_cooldown(self) -> None:
        sharee = _make_character()
        share_mission(self.instance, sharee)

        # Holder has a cooldown from the accept; sharee MUST NOT.
        self.assertTrue(
            MissionGiverStanding.objects.filter(giver=self.giver, character=self.holder).exists()
        )
        self.assertFalse(
            MissionGiverStanding.objects.filter(giver=self.giver, character=sharee).exists()
        )


class AcceptIntegrationWithEnterNodeTests(TestCase):
    """accept_mission relies on Phase-3 enter_node; verify the seam."""

    def test_no_entry_node_raises(self) -> None:
        giver = MissionGiverFactory()
        template = MissionTemplateFactory(name="no-entry-t")
        giver.templates.add(template)
        character = _make_character()
        with self.assertRaises(Exception) as ctx:
            accept_mission(giver, template, character)
        # Authoring error: a template with no entry node cannot be accepted.
        self.assertIn("does not exist", str(ctx.exception).lower())
        # No instance should have been created — atomic transaction rolled back.
        self.assertFalse(MissionInstance.objects.filter(template=template).exists())
