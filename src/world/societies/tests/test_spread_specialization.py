"""Spread skills + forms (#745 Phase 2).

Spreading a tale takes a form (a specialization under a skill): Oratory / Prose /
Singing under Performance, Propaganda under Persuasion. The chosen form sets the
check skill; no form rolls plain Performance.
"""

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.societies.spread_services import (
    ensure_spread_skills,
    get_spread_specializations,
    spread_check_modifiers,
)


class SpreadFormsTest(TestCase):
    def test_creates_the_four_forms(self) -> None:
        ensure_spread_skills()
        names = set(get_spread_specializations().values_list("name", flat=True))
        self.assertEqual(names, {"Oratory", "Prose", "Singing", "Propaganda"})

    def test_propaganda_is_persuasion_artistic_forms_are_performance(self) -> None:
        ensure_spread_skills()
        parent = {s.name: s.parent_skill.name for s in get_spread_specializations()}
        self.assertEqual(parent["Propaganda"], "Persuasion")
        self.assertEqual(parent["Oratory"], "Performance")
        self.assertEqual(parent["Prose"], "Performance")
        self.assertEqual(parent["Singing"], "Performance")

    def test_idempotent(self) -> None:
        ensure_spread_skills()
        ensure_spread_skills()
        self.assertEqual(get_spread_specializations().count(), 4)

    def test_excludes_same_named_specialization_under_a_foreign_skill(self) -> None:
        from world.skills.factories import SpecializationFactory

        ensure_spread_skills()
        foreign = SpecializationFactory(name="Singing")  # under a different parent skill
        spread_ids = set(get_spread_specializations().values_list("pk", flat=True))
        self.assertNotIn(foreign.pk, spread_ids)

    def test_modifiers_zero_for_unskilled_character(self) -> None:
        ensure_spread_skills()
        character = PersonaFactory().character_sheet.character
        self.assertEqual(spread_check_modifiers(character, None), 0)
        form = get_spread_specializations().first()
        self.assertEqual(spread_check_modifiers(character, form), 0)
