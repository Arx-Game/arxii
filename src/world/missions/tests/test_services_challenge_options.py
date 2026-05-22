"""Tests for challenge_options_for_character (Phase A, Task A3).

A MissionNode's attached ChallengeTemplates contribute options: one per
ChallengeApproach the acting character qualifies for (they hold the
approach's Application.capability) plus every is_default approach (offered
to everyone, capability-independent). Capability ownership is granted the
standard way — an active condition carrying a ConditionCapabilityEffect —
mirroring test_resolvers.ConditionCapabilityResolverTests.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
)
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.services.challenge_options import challenge_options_for_character


class ChallengeOptionsForCharacterTests(TestCase):
    """Capability gating, is_default inclusion, and carried flags."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="co-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="n", is_entry=True)
        cls.challenge = ChallengeTemplateFactory(name="The Pit", severity=5)

        # char_with holds two capabilities, each granted by an active
        # condition; char_without holds none.
        cls.char_with = CharacterFactory()
        CharacterSheetFactory(character=cls.char_with)
        cls.cap_climb = CapabilityTypeFactory(name="co-climbing")
        climb_condition = ConditionTemplateFactory(name="co-Wall Crawler")
        ConditionCapabilityEffectFactory(
            condition=climb_condition, capability=cls.cap_climb, value=10
        )
        ConditionInstanceFactory(target=cls.char_with, condition=climb_condition)
        cls.cap_fly = CapabilityTypeFactory(name="co-flight")
        fly_condition = ConditionTemplateFactory(name="co-Winged")
        ConditionCapabilityEffectFactory(condition=fly_condition, capability=cls.cap_fly, value=10)
        ConditionInstanceFactory(target=cls.char_with, condition=fly_condition)

        cls.char_without = CharacterFactory()
        CharacterSheetFactory(character=cls.char_without)

        # Three approaches: capability-keyed, capability-keyed + auto-success,
        # and an is_default fallback anyone may attempt.
        cls.approach_climb = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            application=ApplicationFactory(name="co-app-climb", capability=cls.cap_climb),
            display_name="Scale the wall",
        )
        cls.approach_fly = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            application=ApplicationFactory(name="co-app-fly", capability=cls.cap_fly),
            auto_succeeds=True,
            display_name="Fly out",
        )
        cls.approach_default = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            is_default=True,
            display_name="Climb bare-handed",
        )
        cls.node.attached_challenges.add(cls.challenge)

    def test_character_with_capabilities_gets_every_approach(self) -> None:
        options = challenge_options_for_character(self.node, self.char_with)
        self.assertEqual(
            {o.approach.pk for o in options},
            {self.approach_climb.pk, self.approach_fly.pk, self.approach_default.pk},
        )

    def test_character_without_capabilities_gets_only_default(self) -> None:
        options = challenge_options_for_character(self.node, self.char_without)
        self.assertEqual([o.approach.pk for o in options], [self.approach_default.pk])

    def test_auto_succeeds_is_carried_and_gated_by_capability(self) -> None:
        # auto_succeeds rides onto the option; it does NOT bypass the
        # capability gate — only is_default does.
        with_options = {
            o.approach.pk: o for o in challenge_options_for_character(self.node, self.char_with)
        }
        self.assertTrue(with_options[self.approach_fly.pk].auto_succeeds)
        self.assertFalse(with_options[self.approach_climb.pk].auto_succeeds)
        without = challenge_options_for_character(self.node, self.char_without)
        self.assertNotIn(self.approach_fly.pk, {o.approach.pk for o in without})

    def test_difficulty_is_the_challenge_severity(self) -> None:
        options = challenge_options_for_character(self.node, self.char_with)
        self.assertTrue(options)
        self.assertTrue(all(o.difficulty == 5 for o in options))

    def test_option_carries_check_type_and_owner(self) -> None:
        [option] = challenge_options_for_character(self.node, self.char_without)
        self.assertEqual(option.approach, self.approach_default)
        self.assertEqual(option.check_type, self.approach_default.check_type)
        self.assertEqual(option.owner, self.char_without)

    def test_empty_when_no_default_and_no_capability_match(self) -> None:
        bare_node = MissionNodeFactory(template=self.template, key="bare")
        bare_challenge = ChallengeTemplateFactory(name="Sealed Vault")
        ChallengeApproachFactory(
            challenge_template=bare_challenge,
            application=ApplicationFactory(
                name="co-app-locked",
                capability=CapabilityTypeFactory(name="co-lockpicking"),
            ),
        )
        bare_node.attached_challenges.add(bare_challenge)
        self.assertEqual(challenge_options_for_character(bare_node, self.char_without), [])

    def test_no_attached_challenges_yields_no_options(self) -> None:
        lone_node = MissionNodeFactory(template=self.template, key="lone")
        self.assertEqual(challenge_options_for_character(lone_node, self.char_with), [])
