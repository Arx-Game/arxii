"""Tests for the threads namespace command (#1993)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.models.crossing import (
    CrossingOption,
    PendingCrossingOffer,
)


def _make_condition_template(name: str = "Test Buff", value: int = 5) -> object:
    """Create a ConditionTemplate with a ConditionModifierEffect for testing."""
    from world.conditions.factories import (
        ConditionModifierEffectFactory,
        ConditionTemplateFactory,
    )
    from world.mechanics.factories import ModifierTargetFactory

    template = ConditionTemplateFactory(name=name, default_duration_type="permanent")
    target = ModifierTargetFactory()
    ConditionModifierEffectFactory(
        condition=template,
        modifier_target=target,
        value=value,
    )
    return template


class CmdThreadsListTests(TestCase):
    """threads list shows the caller's active threads."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=10,
        )

    def test_list_shows_threads(self) -> None:
        from commands.threads import CmdThreads

        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = ""
        cmd.func()
        self.assertTrue(caller.msg.called)
        msg = caller.msg.call_args[0][0]
        self.assertIn("TRAIT", msg.upper())

    def test_list_no_threads(self) -> None:
        from commands.threads import CmdThreads
        from world.magic.models import Thread

        Thread.objects.filter(owner=self.sheet).delete()
        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = ""
        cmd.func()
        self.assertTrue(caller.msg.called)
        msg = caller.msg.call_args[0][0]
        self.assertIn("no active threads", msg.lower())


class CmdThreadsListRelationshipLabelQueryCountTests(TestCase):
    """`threads list` prefetches RELATIONSHIP_TRACK anchor labels (#3957 review Important 4).

    `_anchor_label_for` used to call `side.open_labels().first()` per thread — a fresh
    filtered query per RELATIONSHIP_TRACK thread listed. Pins the query count flat
    across N such threads.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.relationships.factories import RelationshipLabelFactory, RelationshipTypeFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.rel_type = RelationshipTypeFactory(name="Loyalty")
        cls.threads = []
        for _ in range(3):
            thread = ThreadFactory(
                owner=cls.sheet,
                resonance=cls.resonance,
                as_track_thread=True,
                level=2,
            )
            RelationshipLabelFactory(relationship=thread.target_relationship, type=cls.rel_type)
            cls.threads.append(thread)

    def _run_list(self) -> str:
        from commands.threads import CmdThreads

        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = ""
        cmd.func()
        return caller.msg.call_args[0][0]

    def test_query_count_flat_across_relationship_threads(self) -> None:
        # Baseline with a single thread.
        from world.magic.models import Thread

        Thread.objects.filter(owner=self.sheet).exclude(pk=self.threads[0].pk).delete()
        with self.assertNumQueries(2):
            msg_one = self._run_list()
        self.assertIn(self.rel_type.name, msg_one)

        # Restore all three threads and confirm the query count doesn't scale with N.
        Thread.objects.filter(owner=self.sheet).delete()
        for _ in range(3):
            from world.magic.factories import ThreadFactory
            from world.relationships.factories import RelationshipLabelFactory

            thread = ThreadFactory(
                owner=self.sheet,
                resonance=self.resonance,
                as_track_thread=True,
                level=2,
            )
            RelationshipLabelFactory(relationship=thread.target_relationship, type=self.rel_type)
        with self.assertNumQueries(2):
            msg_many = self._run_list()
        self.assertEqual(msg_many.count(self.rel_type.name), 3)


class CmdThreadsCrossingTests(TestCase):
    """threads crossing list / choose dispatches to the action."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, ThreadFactory
        from world.traits.factories import TraitFactory

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind="TRAIT",
            target_trait=cls.trait,
            level=3,
        )
        cls.condition_template = _make_condition_template()
        cls.option = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            crossing_level=3,
            name="Burning vigor",
            condition_template=cls.condition_template,
        )
        PendingCrossingOffer.objects.create(thread=cls.thread, crossing_level=3)

    def test_crossing_list_shows_offers(self) -> None:
        from commands.threads import CmdThreads

        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = "crossing list"
        cmd.func()
        self.assertTrue(caller.msg.called)
        # At least one msg call should contain the option name
        all_msgs = [str(call[0][0]) for call in caller.msg.call_args_list]
        self.assertTrue(any("Burning vigor" in m for m in all_msgs))

    def test_crossing_list_no_offers(self) -> None:
        from commands.threads import CmdThreads

        PendingCrossingOffer.objects.filter(thread=self.thread).delete()
        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = "crossing list"
        cmd.func()
        self.assertTrue(caller.msg.called)
        msg = caller.msg.call_args[0][0]
        self.assertIn("no pending crossing offers", msg.lower())

    def test_crossing_choose_resolves_offer(self) -> None:
        from commands.threads import CmdThreads

        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = f"crossing choose {self.option.pk}"
        with patch("actions.definitions.crossing.ResolveCrossingOfferAction") as mock_action_cls:
            mock_result = MagicMock()
            mock_result.message = "Success"
            mock_action_cls.return_value.run.return_value = mock_result
            cmd.func()
            mock_action_cls.return_value.run.assert_called_once()

    def test_crossing_choose_invalid_id(self) -> None:
        from commands.threads import CmdThreads

        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = "crossing choose notanumber"
        cmd.func()
        self.assertTrue(caller.msg.called)
        msg = caller.msg.call_args[0][0]
        self.assertIn("must be a number", msg.lower())

    def test_crossing_choose_no_offer(self) -> None:
        from commands.threads import CmdThreads

        PendingCrossingOffer.objects.filter(thread=self.thread).delete()
        caller = MagicMock()
        caller.sheet_data = self.sheet
        caller.msg = MagicMock()
        cmd = CmdThreads()
        cmd.caller = caller
        cmd.args = f"crossing choose {self.option.pk}"
        cmd.func()
        self.assertTrue(caller.msg.called)
        msg = caller.msg.call_args[0][0]
        self.assertIn("no pending crossing offer", msg.lower())
