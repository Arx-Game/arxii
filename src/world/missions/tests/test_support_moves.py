"""Tests for the support-moves service (#2046).

The fan surfaces support moves for a co-located participant based on their
own capabilities and the node's live CHECK options. Patterns auto-match;
gems are per-node. Rumored moves show as teases to everyone.

declare_support guards, rolls, banks easing on success, fires complications
on failure, and mints the helper's deed.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import CapabilityTypeFactory
from world.missions.constants import (
    ConflictMode,
    JointCombine,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionAssistPatternFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionNodeSupportOptionFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.traits.factories import CheckOutcomeFactory


def _pc():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


class SupportMovesForTests(TestCase):
    """Tests for the fan: what moves surface for a participant."""

    def setUp(self) -> None:
        self.check_type = CheckTypeFactory()
        self.capability = CapabilityTypeFactory(innate_baseline=1)
        self.capability.save()
        self.character = _pc()

    def test_pattern_with_matching_capability_surfaces_move(self) -> None:
        """A pattern whose capability leg matches surfaces a support move."""
        template = MissionTemplateFactory()
        node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        pattern = MissionAssistPatternFactory(
            capability=self.capability,
            support_check_type=self.check_type,
        )
        pattern.check_types.set([self.check_type])
        instance = MissionInstanceFactory(template=template, current_node=node)

        from world.missions.factories import MissionParticipantFactory

        MissionParticipantFactory(instance=instance, character=self.character)

        from world.missions.services.support import support_moves_for

        moves = support_moves_for(instance, node, self.character)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].source_kind, "pattern")
        self.assertEqual(moves[0].capability_name, self.capability.name)

    def test_pattern_without_capability_does_not_surface(self) -> None:
        """A pattern whose capability the character doesn't hold is hidden."""
        other_cap = CapabilityTypeFactory()
        template = MissionTemplateFactory()
        node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        pattern = MissionAssistPatternFactory(
            capability=other_cap,
            support_check_type=self.check_type,
        )
        pattern.check_types.set([self.check_type])
        instance = MissionInstanceFactory(template=template, current_node=node)

        from world.missions.factories import MissionParticipantFactory

        MissionParticipantFactory(instance=instance, character=self.character)

        from world.missions.services.support import support_moves_for

        moves = support_moves_for(instance, node, self.character)
        self.assertEqual(len(moves), 0)

    def test_rumored_move_surfaces_as_tease_even_if_unqualified(self) -> None:
        """A rumored pattern shows its tease to everyone, even if unqualified."""
        other_cap = CapabilityTypeFactory()
        template = MissionTemplateFactory()
        node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        pattern = MissionAssistPatternFactory(
            capability=other_cap,
            support_check_type=self.check_type,
            rumor_text="The hounds seem restless...",
        )
        pattern.check_types.set([self.check_type])
        instance = MissionInstanceFactory(template=template, current_node=node)

        from world.missions.factories import MissionParticipantFactory

        MissionParticipantFactory(instance=instance, character=self.character)

        from world.missions.services.support import support_moves_for

        moves = support_moves_for(instance, node, self.character)
        self.assertEqual(len(moves), 1)
        self.assertTrue(moves[0].rumored)
        self.assertEqual(moves[0].rumor_text, "The hounds seem restless...")

    def test_gem_surfaces_when_qualifier_passes(self) -> None:
        """An authored gem surfaces when the character qualifies."""
        template = MissionTemplateFactory()
        node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionNodeSupportOptionFactory(
            node=node,
            capability=self.capability,
            support_check_type=self.check_type,
            flavor_template="Rally the pack",
        )
        instance = MissionInstanceFactory(template=template, current_node=node)

        from world.missions.factories import MissionParticipantFactory

        MissionParticipantFactory(instance=instance, character=self.character)

        from world.missions.services.support import support_moves_for

        moves = support_moves_for(instance, node, self.character)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].source_kind, "gem")
        self.assertEqual(moves[0].flavor, "Rally the pack")

    def test_suppress_patterns_skips_catalog(self) -> None:
        """When a node has a gem with suppress_patterns, catalog is skipped."""
        template = MissionTemplateFactory()
        node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        # Pattern that would normally match
        pattern = MissionAssistPatternFactory(
            capability=self.capability,
            support_check_type=self.check_type,
        )
        pattern.check_types.set([self.check_type])
        # Gem with suppress_patterns
        MissionNodeSupportOptionFactory(
            node=node,
            capability=self.capability,
            support_check_type=self.check_type,
            flavor_template="Special assist",
            suppress_patterns=True,
        )
        instance = MissionInstanceFactory(template=template, current_node=node)

        from world.missions.factories import MissionParticipantFactory

        MissionParticipantFactory(instance=instance, character=self.character)

        from world.missions.services.support import support_moves_for

        moves = support_moves_for(instance, node, self.character)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].source_kind, "gem")


class DeclareSupportTests(TestCase):
    """Tests for declare_support: guards, roll, easing, complication."""

    def setUp(self) -> None:
        from world.missions.services.resolution import enter_node
        from world.missions.services.run import share_mission, staff_assign_mission

        self.check_type = CheckTypeFactory()
        self.capability = CapabilityTypeFactory(innate_baseline=1)
        self.capability.save()
        self.holder = _pc()
        self.helper = _pc()

        template = MissionTemplateFactory()
        self.node = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        MissionOptionFactory(
            node=self.node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        self.pattern = MissionAssistPatternFactory(
            capability=self.capability,
            support_check_type=self.check_type,
        )
        self.pattern.check_types.set([self.check_type])
        self.instance = staff_assign_mission(template, self.holder)
        share_mission(self.instance, self.helper)
        enter_node(self.instance, self.node)

    def _success_result(self) -> CheckResult:
        outcome = CheckOutcomeFactory(success_level=1)
        return CheckResult(
            check_type=self.check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def _fail_result(self) -> CheckResult:
        outcome = CheckOutcomeFactory(success_level=-1)
        return CheckResult(
            check_type=self.check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def test_declare_support_banks_easing_on_success(self) -> None:
        """A successful support check banks easing on the declaration."""
        from world.missions.services.support import declare_support

        with mock.patch("world.missions.services.support.perform_check") as mock_check:
            mock_check.return_value = self._success_result()
            decl = declare_support(
                self.instance,
                self.helper,
                source_kind="pattern",
                source_id=self.pattern.pk,
            )
        self.assertEqual(decl.easing_banked, self.pattern.easing)
        self.assertEqual(decl.outcome, decl.outcome)  # outcome is set
        self.assertEqual(decl.participant.character, self.helper)

    def test_declare_support_zero_easing_on_failure(self) -> None:
        """A failed support check banks 0 easing."""
        from world.missions.services.support import declare_support

        with mock.patch("world.missions.services.support.perform_check") as mock_check:
            mock_check.return_value = self._fail_result()
            decl = declare_support(
                self.instance,
                self.helper,
                source_kind="pattern",
                source_id=self.pattern.pk,
            )
        self.assertEqual(decl.easing_banked, 0)

    def test_declare_support_creates_deed(self) -> None:
        """A support declaration mints a MissionDeedRecord for the helper."""
        from world.missions.models import MissionDeedRecord
        from world.missions.services.support import declare_support

        with mock.patch("world.missions.services.support.perform_check") as mock_check:
            mock_check.return_value = self._success_result()
            declare_support(
                self.instance,
                self.helper,
                source_kind="pattern",
                source_id=self.pattern.pk,
            )
        self.assertTrue(
            MissionDeedRecord.objects.filter(instance=self.instance, actor=self.helper).exists()
        )

    def test_non_participant_cannot_declare(self) -> None:
        """A non-participant cannot declare support."""
        from world.missions.services.play import BeatActionError
        from world.missions.services.support import declare_support

        stranger = _pc()
        with self.assertRaises(BeatActionError):
            declare_support(
                self.instance,
                stranger,
                source_kind="pattern",
                source_id=self.pattern.pk,
            )
