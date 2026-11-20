"""The fill rule for authored reactive lines (#4587): a bad line never raises.

The journeys in ``integration_tests/test_reactive_moment_narration_journeys.py`` carry the
moments themselves, with a good line and with a blank one. These stay as unit tests because
the fill rule is a pure function with many refusal branches, and the validation tests map
error paths a staff member would have to hit one authored mistake at a time.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from world.conditions.constants import DurationType, ReactiveMoment
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.reactive_narration import fill_reactive_line

NAMES = {"bearer": "Cassian", "source": "Brenna", "attacker": "Hired Brute"}


class FillReactiveLineTests(SimpleTestCase):
    def test_a_good_line_is_filled_with_each_name(self) -> None:
        self.assertEqual(
            fill_reactive_line("{source} guards {bearer} from {attacker}.", NAMES),
            "Brenna guards Cassian from Hired Brute.",
        )

    def test_a_doubled_brace_is_a_literal_brace(self) -> None:
        self.assertEqual(fill_reactive_line("{{{bearer}}} stands.", NAMES), "{Cassian} stands.")

    def test_a_line_that_cannot_be_used_is_none_and_never_raises(self) -> None:
        for text in (
            "",
            "   ",
            "A stray { brace",
            "A stray } brace",
            "Who is {nobody}?",
            "{bearer.__class__}",
            "{bearer[0]}",
            "{bearer!r}",
            "{bearer:>10}",
            "{}",
            "{0}",
        ):
            with self.subTest(text=text):
                self.assertIsNone(fill_reactive_line(text, NAMES))

    def test_a_name_the_moment_cannot_supply_makes_the_line_unusable(self) -> None:
        self.assertIsNone(fill_reactive_line("{attacker} falls.", {"bearer": "Cassian"}))
        self.assertIsNone(
            fill_reactive_line("{source} falls.", {"bearer": "Cassian", "source": ""})
        )


class ReactiveLineValidationTests(TestCase):
    """``ConditionTemplate.clean`` refuses a reactive line staff wrote wrongly."""

    def _problems(self, **fields: object) -> dict[str, list[str]]:
        template = ConditionTemplateFactory(**fields)
        try:
            template.full_clean(exclude=["category"])
        except ValidationError as error:
            return error.message_dict
        return {}

    def test_a_line_with_an_unknown_placeholder_is_refused(self) -> None:
        problems = self._problems(
            source_guards_bearer=True, guard_narration="{hero} steps in for {bearer}."
        )

        self.assertIn("guard_narration", problems)

    def test_a_line_naming_an_attacker_where_none_exists_is_refused(self) -> None:
        problems = self._problems(
            prevents_knockout=True, grace_narration="{bearer} shrugs off {attacker}."
        )

        self.assertIn("grace_narration", problems)

    def test_a_line_for_an_effect_the_condition_lacks_is_refused(self) -> None:
        for moment in ReactiveMoment:
            with self.subTest(moment=moment):
                problems = self._problems(**{f"{moment.value}_narration": "{bearer} acts."})
                self.assertIn(f"{moment.value}_narration", problems)

    def test_a_good_line_on_a_condition_with_the_effect_passes(self) -> None:
        problems = self._problems(
            default_duration_type=DurationType.UNTIL_USED,
            spent_narration="{bearer}'s blessing from {source} is used up.",
        )

        self.assertEqual(problems, {})
