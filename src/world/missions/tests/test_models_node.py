"""Tests for MissionNode + MissionOption (Phase 2, Task 2.2).

Covers the node/option graph invariants: one entry node per template,
JOINT-mode coupling of conflict_mode/joint_combine/joint_count, the
per-template unique key, and the option source/kind invariants (including
the M2M ``accepted_affordances`` rule enforced at the service layer because
M2M cannot be validated in ``model.clean()`` before save).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.mechanics.factories import ChallengeTemplateFactory
from world.missions.constants import (
    ConflictMode,
    JointCombine,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    AffordanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionNode, MissionOption
from world.missions.services import validate_mission_option


class MissionNodeInvariantTests(TestCase):
    """Entry-node uniqueness, key uniqueness, JOINT-mode coupling."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="node-tmpl")
        cls.entry = MissionNodeFactory(
            template=cls.template,
            key="start",
            is_entry=True,
        )

    def test_node_round_trips(self) -> None:
        fetched = MissionNode.objects.get(pk=self.entry.pk)
        self.assertEqual(fetched.key, "start")
        self.assertTrue(fetched.is_entry)
        self.assertEqual(fetched.conflict_mode, ConflictMode.COINFLIP)
        self.assertEqual(str(fetched), "node-tmpl:start")

    def test_second_entry_node_rejected(self) -> None:
        second = MissionNodeFactory.build(
            template=self.template,
            key="other",
            is_entry=True,
            conflict_mode=ConflictMode.COINFLIP,
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_non_entry_node_allowed_alongside_entry(self) -> None:
        node = MissionNodeFactory(template=self.template, key="mid", is_entry=False)
        node.full_clean()  # should not raise
        self.assertFalse(node.is_entry)

    def test_duplicate_key_per_template_rejected(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            MissionNode.objects.create(
                template=self.template,
                key="start",
                is_entry=False,
                conflict_mode=ConflictMode.COINFLIP,
            )

    def test_same_key_different_template_allowed(self) -> None:
        other_tmpl = MissionTemplateFactory(slug="other-tmpl")
        node = MissionNodeFactory(template=other_tmpl, key="start", is_entry=True)
        self.assertEqual(node.key, "start")

    def test_joint_mode_requires_joint_combine(self) -> None:
        node = MissionNodeFactory.build(
            template=self.template,
            key="j1",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=None,
        )
        with self.assertRaises(ValidationError):
            node.full_clean()

    def test_joint_count_combine_requires_joint_count(self) -> None:
        node = MissionNodeFactory.build(
            template=self.template,
            key="j2",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.COUNT,
            joint_count=None,
        )
        with self.assertRaises(ValidationError):
            node.full_clean()

    def test_joint_any_with_combine_set_round_trips(self) -> None:
        node = MissionNodeFactory(
            template=self.template,
            key="j3",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        node.full_clean()
        self.assertEqual(node.joint_combine, JointCombine.ANY)

    def test_joint_count_with_count_round_trips(self) -> None:
        node = MissionNodeFactory(
            template=self.template,
            key="j4",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.COUNT,
            joint_count=2,
        )
        node.full_clean()
        self.assertEqual(node.joint_count, 2)

    def test_non_joint_with_joint_fields_rejected(self) -> None:
        node = MissionNodeFactory.build(
            template=self.template,
            key="nj",
            conflict_mode=ConflictMode.VOTE,
            joint_combine=JointCombine.ALL,
        )
        with self.assertRaises(ValidationError):
            node.full_clean()

    def test_save_enforces_single_entry_node(self) -> None:
        # Regression (I1): clean() must run on the real create()/factory
        # write path. Before the save() override a second entry node for the
        # same template persisted silently.
        with self.assertRaises(ValidationError):
            MissionNodeFactory(
                template=self.template,
                key="second-entry",
                is_entry=True,
            )

    def test_save_enforces_joint_mode_coupling(self) -> None:
        with self.assertRaises(ValidationError):
            MissionNodeFactory(
                template=self.template,
                key="save-joint",
                conflict_mode=ConflictMode.JOINT,
                joint_combine=None,
            )


class MissionOptionInvariantTests(TestCase):
    """Source/kind invariants + the service-level M2M affordance rule."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="opt-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="n", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.template, key="t")
        cls.check_type = CheckTypeFactory(name="Lockpick")
        cls.affordance = AffordanceFactory(name="stealth")

    def test_authored_branch_option_round_trips(self) -> None:
        option = MissionOptionFactory(
            node=self.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            branch_target=self.target,
        )
        fetched = MissionOption.objects.get(pk=option.pk)
        self.assertEqual(fetched.option_kind, OptionKind.BRANCH)
        self.assertEqual(fetched.branch_target, self.target)
        self.assertEqual(fetched.visibility_rule, {})

    def test_authored_check_requires_check_type(self) -> None:
        option = MissionOptionFactory.build(
            node=self.node,
            order=1,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=None,
        )
        with self.assertRaises(ValidationError):
            option.full_clean()

    def test_branch_option_rejects_check_fields(self) -> None:
        option = MissionOptionFactory.build(
            node=self.node,
            order=2,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        with self.assertRaises(ValidationError):
            option.full_clean()

    def test_affordance_option_forbids_authored_fields(self) -> None:
        option = MissionOptionFactory.build(
            node=self.node,
            order=3,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AFFORDANCE,
            authored_check_type=self.check_type,
        )
        with self.assertRaises(ValidationError):
            option.full_clean()

    def test_affordance_option_requires_accepted_affordance(self) -> None:
        # M2M cannot be validated in model.clean() before save; the rule is
        # enforced by the service helper. An AFFORDANCE option with no
        # accepted affordances must fail validate_mission_option().
        option = MissionOptionFactory(
            node=self.node,
            order=4,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AFFORDANCE,
        )
        with self.assertRaises(ValidationError):
            validate_mission_option(option)

        # Once an affordance is attached, the service validation passes.
        option.accepted_affordances.add(self.affordance)
        validate_mission_option(option)  # should not raise

    def test_save_enforces_scalar_kind_invariant(self) -> None:
        # Regression (I1): the scalar clean() rule (BRANCH option forbids a
        # check type) must run on the real create()/factory write path, NOT
        # only via explicit full_clean(). This is the scalar clean() rule,
        # NOT the M2M accepted_affordances rule (that stays in the service).
        with self.assertRaises(ValidationError):
            MissionOptionFactory(
                node=self.node,
                order=6,
                option_kind=OptionKind.BRANCH,
                source_kind=OptionSource.AUTHORED,
                authored_check_type=self.check_type,
            )

    def test_authored_check_option_with_check_type_round_trips(self) -> None:
        option = MissionOptionFactory(
            node=self.node,
            order=5,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
            authored_base_risk=4,
            authored_ic_framing="pick the lock",
        )
        fetched = MissionOption.objects.get(pk=option.pk)
        self.assertEqual(fetched.authored_check_type, self.check_type)
        self.assertEqual(fetched.authored_base_risk, 4)


class MissionNodeAttachedChallengesTests(TestCase):
    """MissionNode.attached_challenges M2M to mechanics.ChallengeTemplate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="attach-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="n", is_entry=True)
        cls.challenge = ChallengeTemplateFactory(name="Pit Climb")

    def test_attached_challenges_defaults_empty(self) -> None:
        self.assertEqual(list(self.node.attached_challenges.all()), [])

    def test_attach_challenge(self) -> None:
        self.node.attached_challenges.add(self.challenge)
        fetched = MissionNode.objects.get(pk=self.node.pk)
        self.assertIn(self.challenge, fetched.attached_challenges.all())

    def test_attached_challenges_cached(self) -> None:
        node = MissionNodeFactory(template=self.template, key="cached", is_entry=False)
        node.attached_challenges.add(self.challenge)
        self.assertEqual(node.attached_challenges_cached, [self.challenge])
