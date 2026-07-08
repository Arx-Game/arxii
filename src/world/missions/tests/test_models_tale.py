"""Tests for the MissionDeedRecord.legend_entries M2M surface (#2047)."""

from django.test import TestCase

from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
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
