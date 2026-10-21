"""An item a mission grants becomes a trophy of the deed it was won on (#4530).

The link needs a deed minted in the same run and a Success or better outcome, in either
order: the route's renown deed already exists when the item is delivered at report time, and
the cron's Legend-points deed is minted later. A Partial Success or worse links nothing, and a
deed credited to someone else never links.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.items.factories import ItemTemplateFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionRewardQueueFactory,
)
from world.missions.services.cron import apply_mission_reward_batch
from world.missions.services.rewards import _route_line
from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendEntryFactory
from world.traits.factories import CheckOutcomeFactory


class MissionTrophyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)

    def _deliver(self, *, outcome, entry_for=None):
        recipient = CharacterSheetFactory()
        deed = MissionDeedRecordFactory(actor=recipient, outcome=outcome)
        deed.legend_entries.add(
            LegendEntryFactory(
                persona=entry_for or recipient.primary_persona, title="Rope across the gorge"
            )
        )
        line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=recipient,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            item_template=ItemTemplateFactory(),
        )
        _route_line(deed, line, [], [], [])
        line.refresh_from_db()
        return line, recipient

    def test_a_success_links_the_item_to_the_deed_and_makes_it_physical(self) -> None:
        line, _recipient = self._deliver(outcome=self.success)

        item = line.granted_item
        self.assertEqual([d.title for d in item.legend_deeds.all()], ["Rope across the gorge"])
        item.refresh_from_db()
        self.assertIsNotNone(item.game_object)

    def test_a_partial_success_links_nothing(self) -> None:
        line, _recipient = self._deliver(outcome=self.partial)

        self.assertIsNotNone(line.granted_item)
        self.assertFalse(line.granted_item.legend_deeds.exists())
        self.assertIsNone(line.granted_item.game_object)

    def test_a_branch_deed_with_no_outcome_links_nothing(self) -> None:
        line, _recipient = self._deliver(outcome=None)

        self.assertFalse(line.granted_item.legend_deeds.exists())

    def test_someone_elses_deed_never_links(self) -> None:
        line, _recipient = self._deliver(outcome=self.success, entry_for=PersonaFactory())

        self.assertFalse(line.granted_item.legend_deeds.exists())

    def test_the_legend_points_deed_minted_later_links_the_item_too(self) -> None:
        actor = CharacterSheetFactory()
        CharacterClassLevelFactory(character=actor, level=3, is_primary=True)
        deed = MissionDeedRecordFactory(actor=actor, outcome=self.success)
        template = deed.instance.template
        template.risk_tier = 5
        template.level_band_min = 2
        template.level_band_max = 3
        template.save(update_fields=["risk_tier", "level_band_min", "level_band_max"])
        item_line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=actor,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            item_template=ItemTemplateFactory(),
        )
        # The item arrives first, with no deed yet: nothing to link to.
        _route_line(deed, item_line, [], [], [])
        item_line.refresh_from_db()
        self.assertFalse(item_line.granted_item.legend_deeds.exists())

        lp_line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=actor,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=5_000,
        )
        MissionRewardQueueFactory(line=lp_line)
        apply_mission_reward_batch()

        (linked,) = item_line.granted_item.legend_deeds.all()
        self.assertEqual(linked.persona, actor.primary_persona)
        self.assertTrue(linked.title.startswith("Mission deed"))
