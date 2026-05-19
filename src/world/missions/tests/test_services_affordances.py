"""Tests for ``bindings_for_character`` (Phase 1, Task 1.3).

The service turns authored-once bindings into the concrete options an acting
character can take. Ownership is decided by the Phase 0 resolvers (reused, not
reimplemented). These tests build real factory objects (no ORM mocks) and
assert: only accepted affordances surface, only owned descriptors surface,
the flattened ``ResolvedOption`` fields are correct, ordering is
deterministic, and an empty accepted set yields nothing.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.missions.constants import OptionProduces
from world.missions.factories import AffordanceBindingFactory, AffordanceFactory
from world.missions.models import SOURCE_ACHIEVEMENT, SOURCE_CAPABILITY, SOURCE_DISTINCTION
from world.missions.services import bindings_for_character


class BindingsForCharacterTests(TestCase):
    """Owned-and-accepted bindings surface; others are excluded."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Three affordances; the challenge will accept all three.
        cls.aff_distraction = AffordanceFactory(name="distraction")
        cls.aff_lethal = AffordanceFactory(name="lethal")
        cls.aff_stealth = AffordanceFactory(name="stealth")
        # A fourth affordance the challenge will NOT accept.
        cls.aff_social = AffordanceFactory(name="social")

        # Descriptor 1 (owned): distinction → distraction, BRANCH.
        cls.dist_charming = DistinctionFactory(slug="charming")
        CharacterDistinctionFactory(character=cls.character, distinction=cls.dist_charming)
        cls.binding_distraction = AffordanceBindingFactory(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=cls.dist_charming,
            affordance=cls.aff_distraction,
            produces=OptionProduces.BRANCH,
            ic_framing="You charm the guard into looking away.",
        )

        # Descriptor 2 (owned): capability → lethal, CHECK + rider.
        cls.cap_killer = CapabilityTypeFactory(name="lethal-strike")
        cls.cap_grant_condition = ConditionTemplateFactory(name="Trained Killer")
        ConditionCapabilityEffectFactory(
            condition=cls.cap_grant_condition,
            capability=cls.cap_killer,
            value=10,
        )
        ConditionInstanceFactory(target=cls.character, condition=cls.cap_grant_condition)
        cls.check_type = CheckTypeFactory(name="Assassinate")
        cls.rider = ConsequenceFactory()
        cls.binding_lethal = AffordanceBindingFactory(
            source_kind=SOURCE_CAPABILITY,
            source_distinction=None,
            source_capability=cls.cap_killer,
            affordance=cls.aff_lethal,
            produces=OptionProduces.CHECK,
            check_type=cls.check_type,
            base_risk=7,
            ic_framing="You move to end it cleanly.",
            rider=cls.rider,
        )

        # Descriptor 3 (NOT owned): achievement → stealth. Excluded because
        # the character never earned the achievement.
        cls.ach_ghost = AchievementFactory(slug="ghost-walker")
        cls.binding_stealth = AffordanceBindingFactory(
            source_kind=SOURCE_ACHIEVEMENT,
            source_distinction=None,
            source_achievement=cls.ach_ghost,
            affordance=cls.aff_stealth,
            produces=OptionProduces.BRANCH,
            ic_framing="You melt into the shadows.",
        )

        # Descriptor 4 (owned) bound to a NOT-accepted affordance (social).
        cls.dist_orator = DistinctionFactory(slug="orator")
        CharacterDistinctionFactory(character=cls.character, distinction=cls.dist_orator)
        cls.binding_social = AffordanceBindingFactory(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=cls.dist_orator,
            affordance=cls.aff_social,
            produces=OptionProduces.BRANCH,
            ic_framing="You give a rousing speech.",
        )

        cls.accepted = {cls.aff_distraction, cls.aff_lethal, cls.aff_stealth}

    def test_only_owned_and_accepted_bindings_surface(self) -> None:
        options = bindings_for_character(self.character, self.accepted)
        # Owned: distraction (distinction) + lethal (capability). NOT stealth
        # (achievement unowned), NOT social (affordance not accepted).
        self.assertEqual(len(options), 2)
        surfaced = {opt.binding.pk for opt in options}
        self.assertEqual(
            surfaced,
            {self.binding_distraction.pk, self.binding_lethal.pk},
        )

    def test_deterministic_order_by_affordance_name_then_pk(self) -> None:
        options = bindings_for_character(self.character, self.accepted)
        # "distraction" < "lethal" alphabetically.
        self.assertEqual(options[0].binding.pk, self.binding_distraction.pk)
        self.assertEqual(options[1].binding.pk, self.binding_lethal.pk)

    def test_branch_option_fields_are_flattened(self) -> None:
        options = bindings_for_character(self.character, self.accepted)
        branch = options[0]
        self.assertEqual(branch.produces, OptionProduces.BRANCH)
        self.assertIsNone(branch.check_type)
        self.assertEqual(branch.base_risk, 0)
        self.assertEqual(branch.ic_framing, "You charm the guard into looking away.")
        self.assertIsNone(branch.rider)
        self.assertEqual(branch.owner, self.character)

    def test_check_option_fields_are_flattened(self) -> None:
        options = bindings_for_character(self.character, self.accepted)
        check = options[1]
        self.assertEqual(check.produces, OptionProduces.CHECK)
        self.assertEqual(check.check_type, self.check_type)
        self.assertEqual(check.base_risk, 7)
        self.assertEqual(check.rider, self.rider)
        self.assertEqual(check.owner, self.character)

    def test_binding_for_unaccepted_affordance_is_excluded(self) -> None:
        # Accept only "social" (which the char owns via orator) → surfaces;
        # but the other owned binding (distraction) must NOT appear.
        options = bindings_for_character(self.character, {self.aff_social})
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].binding.pk, self.binding_social.pk)

    def test_unowned_descriptor_is_excluded_even_when_accepted(self) -> None:
        # stealth is accepted but the ghost-walker achievement is unowned.
        options = bindings_for_character(self.character, {self.aff_stealth})
        self.assertEqual(options, [])

    def test_empty_accepted_set_returns_empty(self) -> None:
        self.assertEqual(bindings_for_character(self.character, set()), [])

    def test_owned_achievement_makes_its_binding_surface(self) -> None:
        # Grant the previously-unowned achievement; now stealth surfaces.
        CharacterAchievementFactory(
            character_sheet=self.sheet,
            achievement=self.ach_ghost,
        )
        options = bindings_for_character(self.character, {self.aff_stealth})
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].binding.pk, self.binding_stealth.pk)
