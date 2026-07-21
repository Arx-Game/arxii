"""Tests for ``build_option_list``.

A node surfaces AUTHORED options when their visibility predicate passes for
the acting character, and fans CHALLENGE-sourced options out per qualifying
ChallengeApproach. Real factory objects, no ORM mocks, single participant.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
)
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services import build_option_list


class BuildOptionListTests(TestCase):
    """AUTHORED visibility gating + stable order."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.template = MissionTemplateFactory(name="opt-list-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.participant = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )

        # An AUTHORED option gated by a visibility rule the char fails:
        # requires a distinction it does NOT have.
        cls.gate_dist = DistinctionFactory(slug="needs-this")
        cls.gated_option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            visibility_rule={"leaf": "has_distinction", "params": {"slug": "needs-this"}},
            authored_ic_framing="The gated way.",
        )
        # An ungated AUTHORED option (empty visibility_rule = always shown).
        cls.ungated_option = MissionOptionFactory(
            node=cls.node,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="The open way.",
        )

    def test_gated_option_hidden_when_predicate_fails(self) -> None:
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertNotIn(self.gated_option, {o.option for o in options})

    def test_gated_option_shown_when_predicate_passes(self) -> None:
        CharacterDistinctionFactory(character=self.sheet, distinction=self.gate_dist)
        options = build_option_list(self.instance, self.node, self.participant)
        gated = [o for o in options if o.option == self.gated_option]
        self.assertEqual(len(gated), 1)
        self.assertEqual(gated[0].ic_framing, "The gated way.")
        self.assertEqual(gated[0].owner, self.character)

    def test_empty_visibility_rule_authored_option_always_shown(self) -> None:
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertIn(self.ungated_option, {o.option for o in options})

    def test_order_is_stable_by_option_order(self) -> None:
        CharacterDistinctionFactory(character=self.sheet, distinction=self.gate_dist)
        options = build_option_list(self.instance, self.node, self.participant)
        # order=0 gated entry precedes order=1 ungated entry.
        self.assertEqual(
            [o.option for o in options],
            [self.gated_option, self.ungated_option],
        )

    def test_authored_check_option_field_flow(self) -> None:
        # An AUTHORED CHECK option's authored_check_type / authored_base_risk
        # / authored_ic_framing all flow onto the PresentedOption.
        check_type = CheckTypeFactory(name="opt-flow-lockpick")
        authored_check = MissionOptionFactory(
            node=self.node,
            order=2,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check_type,
            authored_base_risk=4,
            authored_ic_framing="Pick the lock.",
        )
        options = build_option_list(self.instance, self.node, self.participant)
        presented = next(o for o in options if o.option == authored_check)
        self.assertEqual(presented.check_type, check_type)
        self.assertEqual(presented.base_risk, 4)
        self.assertEqual(presented.ic_framing, "Pick the lock.")
        self.assertEqual(presented.kind, OptionKind.CHECK)
        self.assertEqual(presented.owner, self.character)


class BuildOptionListChallengeTests(TestCase):
    """A CHALLENGE-sourced option fans out per qualifying ChallengeApproach."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(name="ch-opt-list-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.participant = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )
        cls.challenge = ChallengeTemplateFactory(name="ChOptList Pit")
        cls.default_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            is_default=True,
            display_name="Bare-handed",
        )
        # A capability-keyed approach the character does NOT qualify for.
        cls.gated_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            application=ApplicationFactory(
                name="chopt-app",
                capability=CapabilityTypeFactory(name="chopt-cap"),
            ),
            display_name="Capability way",
        )
        cls.option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.CHALLENGE,
            challenge=cls.challenge,
        )

    def test_challenge_option_fans_out_to_qualifying_approaches(self) -> None:
        # The character holds no capabilities → only the is_default approach.
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertEqual(len(options), 1)
        presented = options[0]
        self.assertEqual(presented.option, self.option)
        self.assertEqual(presented.approach, self.default_approach)
        self.assertEqual(presented.check_type, self.default_approach.check_type)
        self.assertEqual(presented.owner, self.character)

    def test_challenge_and_authored_options_coexist(self) -> None:
        authored = MissionOptionFactory(
            node=self.node,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="The authored way.",
        )
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertEqual(
            {o.option.pk for o in options},
            {self.option.pk, authored.pk},
        )
