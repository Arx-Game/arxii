"""Tests for check_outcome_faces() (#3807 Part B): success-level wheel faces.

The wheel shows the raw ResultChart bands, never a rollmod- or
outcome-guarantee-shaped view of them -- see the HARD RULE in
world.checks.theater.check_outcome_faces's docstring.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.theater import check_outcome_faces
from world.checks.types import CheckResult
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory


def _result(*, chart, outcome) -> CheckResult:
    return CheckResult(
        check_type=None,
        outcome=outcome,
        chart=chart,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


class CheckOutcomeFacesTests(TestCase):
    """check_outcome_faces() builds faces straight off the chart's bands."""

    @classmethod
    def setUpTestData(cls) -> None:
        setup = CheckSystemSetupFactory.create()
        cls.outcomes = setup["outcomes"]
        # The "Even" chart (rank_difference=0): failure 1-40 (w40),
        # partial 41-60 (w20), success 61-100 (w40).
        cls.chart = setup["charts"][0]

    def test_weights_equal_band_widths(self) -> None:
        faces, _selected = check_outcome_faces(
            _result(chart=self.chart, outcome=self.outcomes["success"])
        )
        by_label = {f.label: f.weight for f in faces}
        assert by_label == {
            "Failure": 40,
            "Partial Success": 20,
            "Success": 40,
        }

    def test_faces_ordered_by_min_roll(self) -> None:
        faces, _selected = check_outcome_faces(
            _result(chart=self.chart, outcome=self.outcomes["success"])
        )
        assert [f.label for f in faces] == ["Failure", "Partial Success", "Success"]

    def test_selected_is_the_rolled_outcome(self) -> None:
        faces, selected = check_outcome_faces(
            _result(chart=self.chart, outcome=self.outcomes["partial"])
        )
        assert selected is not None
        assert selected.label == "Partial Success"
        # Identity, not just equality -- build_roulette_payload compares by `is`.
        assert any(f is selected for f in faces)

    def test_outcome_not_on_chart_is_appended_and_selected(self) -> None:
        """An outcome-guarantee-lifted outcome not on the chart's own bands
        still gets a face, appended with weight 1 and selected."""
        off_chart_outcome = CheckOutcomeFactory(name="Guaranteed Outcome", success_level=3)

        faces, selected = check_outcome_faces(_result(chart=self.chart, outcome=off_chart_outcome))

        assert selected is not None
        assert selected.label == "Guaranteed Outcome"
        assert selected.weight == 1
        assert selected.outcome_tier_id == off_chart_outcome.pk
        assert faces[-1] is selected
        # The chart's own three bands are still present, untouched.
        assert [f.label for f in faces[:3]] == ["Failure", "Partial Success", "Success"]

    def test_no_chart_returns_empty(self) -> None:
        faces, selected = check_outcome_faces(_result(chart=None, outcome=self.outcomes["success"]))
        assert faces == []
        assert selected is None

    def test_no_outcome_returns_empty(self) -> None:
        faces, selected = check_outcome_faces(_result(chart=self.chart, outcome=None))
        assert faces == []
        assert selected is None

    def test_rollmod_never_shapes_the_wheel(self) -> None:
        """Faces come from the chart bands alone -- a nonzero rollmod on the
        roller's sheet must never change what the wheel shows (HARD RULE)."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character, rollmod=0)

        result = _result(chart=self.chart, outcome=self.outcomes["success"])
        baseline_faces, baseline_selected = check_outcome_faces(result)

        sheet.rollmod = 50
        sheet.save(update_fields=["rollmod"])

        rollmod_faces, rollmod_selected = check_outcome_faces(result)

        assert [(f.label, f.weight) for f in baseline_faces] == [
            (f.label, f.weight) for f in rollmod_faces
        ]
        assert baseline_selected.label == rollmod_selected.label
        assert baseline_selected.weight == rollmod_selected.weight
