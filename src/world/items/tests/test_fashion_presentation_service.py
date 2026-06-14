"""Tests for the fashion-presentation service (#514).

Covers ``present_outfit`` + ``judge_presentation`` and the acclaim/prestige
recompute helpers. The presentation check is forced deterministic via
``force_check_outcome`` so ``base_score`` reflects a known graded outcome.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.events.factories import EventFactory
from world.items.constants import (
    FASHION_PRESENTATION_BASE_DIFFICULTY,
    FASHION_PRESENTATION_CHECK_TYPE_NAME,
    FASHION_PRESENTATION_ENDORSEMENT_WEIGHT,
    FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
)
from world.items.exceptions import FashionPresentationError
from world.items.factories import FashionStyleFactory
from world.items.models import FashionPresentation
from world.items.services.fashion_presentation import (
    judge_presentation,
    present_outfit,
    recompute_acclaim,
    recompute_persona_prestige_from_fashion,
)
from world.magic.factories import FacetFactory
from world.magic.models.endorsement import PresentationEndorsement
from world.mechanics.factories import ModifierTargetFactory
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory


class FashionPresentationServiceTests(TestCase):
    """Cover present_outfit + judge_presentation + recompute helpers."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Author the ModifierTarget + CheckType the service fetches by name.
        cls.modifier_target = ModifierTargetFactory(
            name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
        )
        cls.check_type = CheckTypeFactory(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)

        # Deterministic graded outcomes.
        cls.outcome_success = CheckOutcomeFactory(
            name="fashion-success",
            success_level=3,
        )
        cls.outcome_botch = CheckOutcomeFactory(
            name="fashion-botch",
            success_level=-2,
        )

        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)
        cls.presenter = CharacterSheetFactory()
        cls.judge = CharacterSheetFactory()

    # -- present_outfit -----------------------------------------------------

    def test_present_outfit_records_graded_base_score(self) -> None:
        """A successful check yields base_score == graded success_level, acclaim mirrors it."""
        with force_check_outcome(self.outcome_success):
            presentation = present_outfit(self.presenter, self.event)
        self.assertEqual(presentation.base_score, 3)
        self.assertEqual(presentation.acclaim, 3)
        self.assertEqual(presentation.presenter, self.presenter)
        self.assertEqual(presentation.perceiving_society, self.society)
        self.assertIsNotNone(presentation.pk)

    def test_present_outfit_floors_botch_at_zero(self) -> None:
        """A botched check floors base_score at 0 (no negative acclaim)."""
        with force_check_outcome(self.outcome_botch):
            presentation = present_outfit(self.presenter, self.event)
        self.assertEqual(presentation.base_score, 0)
        self.assertEqual(presentation.acclaim, 0)

    def test_present_outfit_passes_taste_difficulty(self) -> None:
        """Difficulty derives from base + number of in-vogue facets in the style."""
        style = FashionStyleFactory()
        style.in_vogue_facets.add(FacetFactory(), FacetFactory())
        self.society.current_fashion_style = style
        self.society.save(update_fields=["current_fashion_style"])
        with force_check_outcome(self.outcome_success) as capture:
            present_outfit(self.presenter, self.event)
        self.assertEqual(
            capture.target_difficulty,
            FASHION_PRESENTATION_BASE_DIFFICULTY + 2,
        )

    def test_present_outfit_requires_host_society(self) -> None:
        """present_outfit raises when the event has no host society."""
        event = EventFactory(host_society=None)
        with self.assertRaises(FashionPresentationError):
            present_outfit(self.presenter, event)

    # -- judge_presentation -------------------------------------------------

    def _present(self) -> FashionPresentation:
        with force_check_outcome(self.outcome_success):
            return present_outfit(self.presenter, self.event)

    def test_judge_creates_endorsement_and_raises_acclaim(self) -> None:
        """Judging creates an endorsement and bumps acclaim by the configured weight."""
        presentation = self._present()
        base = presentation.base_score
        endorsement = judge_presentation(self.judge, presentation)
        self.assertIsInstance(endorsement, PresentationEndorsement)
        self.assertEqual(endorsement.endorser_sheet, self.judge)
        self.assertEqual(endorsement.endorsee_sheet, self.presenter)
        presentation.refresh_from_db()
        self.assertEqual(
            presentation.acclaim,
            base + FASHION_PRESENTATION_ENDORSEMENT_WEIGHT,
        )

    def test_judge_recomputes_presenter_prestige_from_fashion(self) -> None:
        """Judging folds the presentation acclaim into the presenter's persona prestige."""
        presentation = self._present()
        persona = self.presenter.primary_persona
        before_total = persona.total_prestige
        judge_presentation(self.judge, presentation)
        persona.refresh_from_db()
        presentation.refresh_from_db()
        self.assertEqual(persona.prestige_from_fashion, presentation.acclaim)
        self.assertEqual(
            persona.total_prestige,
            before_total + presentation.acclaim,
        )

    def test_self_judging_rejected(self) -> None:
        """A presenter cannot judge their own presentation."""
        presentation = self._present()
        with self.assertRaises(FashionPresentationError):
            judge_presentation(self.presenter, presentation)

    def test_alt_judging_rejected(self) -> None:
        """Two sheets played by the same account cannot judge each other."""
        judge = CharacterSheetFactory()
        _link_same_account(self.presenter, judge)
        presentation = self._present()
        with self.assertRaises(FashionPresentationError):
            judge_presentation(judge, presentation)

    def test_duplicate_judging_rejected(self) -> None:
        """A judge cannot endorse the same presentation twice."""
        presentation = self._present()
        judge_presentation(self.judge, presentation)
        with self.assertRaises(FashionPresentationError):
            judge_presentation(self.judge, presentation)

    # -- recompute helpers --------------------------------------------------

    def test_recompute_acclaim_sums_weighted_endorsements(self) -> None:
        """recompute_acclaim = base_score + weight * sum(endorsement weights)."""
        presentation = self._present()
        judge_presentation(self.judge, presentation)
        judge_presentation(CharacterSheetFactory(), presentation)
        value = recompute_acclaim(presentation)
        self.assertEqual(
            value,
            presentation.base_score + FASHION_PRESENTATION_ENDORSEMENT_WEIGHT * 2,
        )

    def test_recompute_prestige_sums_all_presentations(self) -> None:
        """Prestige axis sums acclaim across every presentation by the presenter."""
        first = self._present()
        judge_presentation(self.judge, first)
        second = self._present()
        judge_presentation(self.judge, second)
        persona = self.presenter.primary_persona
        value = recompute_persona_prestige_from_fashion(persona)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(value, first.acclaim + second.acclaim)


def _link_same_account(sheet_a: object, sheet_b: object) -> None:
    """Wire two CharacterSheets to the same Account via roster tenure chain.

    Mirrors the walk in ``account_for_sheet``: CharacterSheet -> RosterEntry ->
    current RosterTenure -> PlayerData -> Account.
    """
    from world.roster.factories import (
        PlayerDataFactory,
        RosterEntryFactory,
        RosterTenureFactory,
    )

    player_data = PlayerDataFactory()
    for sheet in (sheet_a, sheet_b):
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
