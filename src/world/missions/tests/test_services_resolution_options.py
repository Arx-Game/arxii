"""Tests for ``build_option_list`` (Phase 3, Task 3.1).

A node fans AFFORDANCE-sourced options out over the acting character's owned
descriptor bindings and includes AUTHORED options only when their visibility
predicate passes. Real factory objects, no ORM mocks, single participant.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
)
from world.missions.constants import OptionKind, OptionProduces, OptionSource
from world.missions.factories import (
    AffordanceBindingFactory,
    AffordanceFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import SOURCE_DISTINCTION
from world.missions.services import build_option_list


class BuildOptionListTests(TestCase):
    """Affordance fan-out + authored visibility gating + stable order."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.template = MissionTemplateFactory(slug="opt-list-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.participant = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )

        # One AFFORDANCE option accepting "infiltrate". Three tagged
        # distinctions; the character owns two of them.
        cls.aff = AffordanceFactory(name="infiltrate")
        cls.owned_a = DistinctionFactory(slug="owned-a")
        cls.owned_b = DistinctionFactory(slug="owned-b")
        cls.unowned = DistinctionFactory(slug="unowned-c")
        CharacterDistinctionFactory(character=cls.character, distinction=cls.owned_a)
        CharacterDistinctionFactory(character=cls.character, distinction=cls.owned_b)
        for dist, framing in (
            (cls.owned_a, "Slip past via owned-a."),
            (cls.owned_b, "Slip past via owned-b."),
            (cls.unowned, "Slip past via unowned-c."),
        ):
            AffordanceBindingFactory(
                source_kind=SOURCE_DISTINCTION,
                source_distinction=dist,
                affordance=cls.aff,
                produces=OptionProduces.BRANCH,
                ic_framing=framing,
            )
        cls.aff_option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AFFORDANCE,
        )
        cls.aff_option.accepted_affordances.add(cls.aff)

        # One AUTHORED option gated by a visibility rule the char fails:
        # requires a distinction it does NOT have.
        cls.gate_dist = DistinctionFactory(slug="needs-this")
        cls.authored_option = MissionOptionFactory(
            node=cls.node,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            visibility_rule={"leaf": "has_distinction", "params": {"slug": "needs-this"}},
            authored_ic_framing="The authored way.",
        )

    def test_affordance_fans_out_to_owned_bindings_only(self) -> None:
        options = build_option_list(self.instance, self.node, self.participant)
        # 2 owned affordance bindings; authored gate fails → not shown.
        self.assertEqual(len(options), 2)
        framings = {o.ic_framing for o in options}
        self.assertEqual(framings, {"Slip past via owned-a.", "Slip past via owned-b."})
        for o in options:
            self.assertEqual(o.option, self.aff_option)
            self.assertIsNotNone(o.binding)
            self.assertEqual(o.owner, self.character)
            self.assertEqual(o.kind, OptionKind.BRANCH)

    def test_authored_option_hidden_when_predicate_fails(self) -> None:
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertNotIn(self.authored_option, {o.option for o in options})

    def test_authored_option_shown_when_predicate_passes(self) -> None:
        CharacterDistinctionFactory(character=self.character, distinction=self.gate_dist)
        options = build_option_list(self.instance, self.node, self.participant)
        authored = [o for o in options if o.option == self.authored_option]
        self.assertEqual(len(authored), 1)
        self.assertIsNone(authored[0].binding)
        self.assertEqual(authored[0].ic_framing, "The authored way.")
        # 2 affordance + 1 authored.
        self.assertEqual(len(options), 3)

    def test_empty_visibility_rule_authored_option_always_shown(self) -> None:
        # An option with the default empty dict rule is ungated.
        MissionOptionFactory(
            node=self.node,
            order=2,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Ungated.",
        )
        options = build_option_list(self.instance, self.node, self.participant)
        self.assertIn("Ungated.", {o.ic_framing for o in options})

    def test_order_is_stable_by_option_order(self) -> None:
        CharacterDistinctionFactory(character=self.character, distinction=self.gate_dist)
        options = build_option_list(self.instance, self.node, self.participant)
        # order=0 affordance entries precede the order=1 authored entry.
        self.assertEqual(options[0].option, self.aff_option)
        self.assertEqual(options[1].option, self.aff_option)
        self.assertEqual(options[2].option, self.authored_option)


class BuildOptionListChallengeTests(TestCase):
    """A CHALLENGE-sourced option fans out per qualifying ChallengeApproach."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(slug="ch-opt-list-tmpl")
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
