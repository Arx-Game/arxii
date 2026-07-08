"""Tests for the MissionDeedRecord.legend_entries M2M + MissionRunTale (#2047)."""

from django.test import TestCase

from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionRunTale
from world.societies.factories import LegendEntryFactory


class MissionDeedRecordLegendEntriesTests(TestCase):
    """The legend_entries M2M links deeds to the LegendEntry rows they minted (#2047)."""

    def test_legend_entries_m2m_can_link_entries(self):
        template = MissionTemplateFactory()
        node = MissionNodeFactory(template=template)
        option = MissionOptionFactory(node=node)
        instance = MissionInstanceFactory(template=template)
        participant = MissionParticipantFactory(instance=instance)
        deed = MissionDeedRecordFactory(
            instance=instance,
            actor=participant.character,
            node=node,
            option=option,
        )
        entry = LegendEntryFactory()
        deed.legend_entries.add(entry)
        self.assertIn(entry, deed.legend_entries.all())
        self.assertIn(deed, entry.mission_deeds.all())


class MissionRunTaleModelTests(TestCase):
    """The MissionRunTale model — one tale per participant per instance (#2047)."""

    def test_one_tale_per_participant_upsert(self):
        instance = MissionInstanceFactory()
        participant = MissionParticipantFactory(instance=instance)
        tale = MissionRunTale.objects.create(
            instance=instance, participant=participant, text="first"
        )
        tale.text = "updated"
        tale.save()
        self.assertEqual(MissionRunTale.objects.count(), 1)
        self.assertEqual(MissionRunTale.objects.get().text, "updated")

    def test_two_participants_each_own_tale(self):
        instance = MissionInstanceFactory()
        p1 = MissionParticipantFactory(instance=instance)
        p2 = MissionParticipantFactory(instance=instance)
        MissionRunTale.objects.create(instance=instance, participant=p1, text="mine")
        MissionRunTale.objects.create(instance=instance, participant=p2, text="theirs")
        self.assertEqual(MissionRunTale.objects.count(), 2)

    def test_unique_constraint_prevents_duplicate(self):
        from django.db import IntegrityError

        instance = MissionInstanceFactory()
        participant = MissionParticipantFactory(instance=instance)
        MissionRunTale.objects.create(instance=instance, participant=participant, text="first")
        with self.assertRaises(IntegrityError):
            MissionRunTale.objects.create(instance=instance, participant=participant, text="second")
