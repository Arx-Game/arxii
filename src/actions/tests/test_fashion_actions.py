"""Tests for fashion presentation actions: present_outfit, judge_presentation (#514)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.fashion import JudgePresentationAction, PresentOutfitAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.events.factories import EventFactory
from world.items.constants import (
    FASHION_PRESENTATION_CHECK_TYPE_NAME,
    FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
)
from world.items.factories import FashionPresentationFactory
from world.items.models import FashionPresentation
from world.magic.models.endorsement import PresentationEndorsement
from world.mechanics.factories import ModifierTargetFactory
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory


def _make_actor(name: str) -> tuple:
    """Return (room, actor) with a Character and CharacterSheet."""
    room = ObjectDBFactory(
        db_key=f"{name}Room",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    return room, actor, sheet


class PresentOutfitActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Author the ModifierTarget + CheckType the service fetches by name.
        cls.modifier_target = ModifierTargetFactory(
            name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
        )
        cls.check_type = CheckTypeFactory(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)
        cls.outcome_success = CheckOutcomeFactory(
            name="present-action-success",
            success_level=2,
        )
        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)
        cls.event_no_society = EventFactory(host_society=None)

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("PresentOutfitActionAlice")

    def test_happy_path_creates_fashion_presentation(self) -> None:
        """Dispatching with a valid event → ActionResult success + FashionPresentation row."""
        action = PresentOutfitAction()
        with force_check_outcome(self.outcome_success):
            with patch.object(self.room, "msg_contents"):
                result = action.run(self.actor, event_id=self.event.pk)

        self.assertTrue(result.success)
        self.assertTrue(
            FashionPresentation.objects.filter(
                presenter=self.sheet,
                event=self.event,
            ).exists()
        )

    def test_missing_event_id_returns_failure(self) -> None:
        """No event_id kwarg → friendly failure, no DB write."""
        action = PresentOutfitAction()
        result = action.run(self.actor)

        self.assertFalse(result.success)
        self.assertIn("event", result.message.lower())

    def test_unknown_event_id_returns_failure(self) -> None:
        """Non-existent event_id → friendly failure."""
        action = PresentOutfitAction()
        result = action.run(self.actor, event_id=999_999)

        self.assertFalse(result.success)

    def test_event_without_host_society_returns_failure(self) -> None:
        """Event with no host_society → service raises FashionPresentationError."""
        action = PresentOutfitAction()
        with force_check_outcome(self.outcome_success):
            result = action.run(self.actor, event_id=self.event_no_society.pk)

        self.assertFalse(result.success)
        self.assertIn("host society", result.message.lower())

    def test_fashion_presentation_error_surfaces_user_message(self) -> None:
        """FashionPresentationError.user_message flows through to ActionResult."""
        from world.items.exceptions import FashionPresentationError

        action = PresentOutfitAction()
        with patch(
            "actions.definitions.fashion.present_outfit_service",
            side_effect=FashionPresentationError("Boom!"),
        ):
            with force_check_outcome(self.outcome_success):
                result = action.run(self.actor, event_id=self.event.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Boom!")


class JudgePresentationActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.modifier_target = ModifierTargetFactory(
            name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
        )
        cls.check_type = CheckTypeFactory(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)
        cls.outcome_success = CheckOutcomeFactory(
            name="judge-action-success",
            success_level=1,
        )
        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)

    def setUp(self) -> None:
        self.presenter_room, self.presenter_actor, self.presenter_sheet = _make_actor(
            "JudgePresentationPresenter"
        )
        self.judge_room, self.judge_actor, self.judge_sheet = _make_actor("JudgePresentationJudge")
        # Build a presentation to judge.
        self.presentation = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter_sheet,
            perceiving_society=self.society,
            base_score=2,
            acclaim=2,
        )

    def test_happy_path_creates_endorsement(self) -> None:
        """A second actor judging a presentation → success + PresentationEndorsement row."""
        action = JudgePresentationAction()
        with patch.object(self.judge_room, "msg_contents"):
            result = action.run(self.judge_actor, presentation_id=self.presentation.pk)

        self.assertTrue(result.success)
        self.assertTrue(
            PresentationEndorsement.objects.filter(
                presentation=self.presentation,
                endorser_sheet=self.judge_sheet,
            ).exists()
        )

    def test_missing_presentation_id_returns_failure(self) -> None:
        """No presentation_id kwarg → friendly failure."""
        action = JudgePresentationAction()
        result = action.run(self.judge_actor)

        self.assertFalse(result.success)
        self.assertIn("presentation", result.message.lower())

    def test_unknown_presentation_id_returns_failure(self) -> None:
        """Non-existent presentation_id → friendly failure."""
        action = JudgePresentationAction()
        result = action.run(self.judge_actor, presentation_id=999_999)

        self.assertFalse(result.success)

    def test_self_judge_returns_failure(self) -> None:
        """Presenter judging their own presentation → FashionPresentationError → failure."""
        action = JudgePresentationAction()
        result = action.run(self.presenter_actor, presentation_id=self.presentation.pk)

        self.assertFalse(result.success)
        self.assertIn("cannot judge", result.message.lower())

    def test_fashion_presentation_error_surfaces_user_message(self) -> None:
        """FashionPresentationError.user_message flows through to ActionResult."""
        from world.items.exceptions import FashionPresentationError

        action = JudgePresentationAction()
        with patch(
            "actions.definitions.fashion.judge_presentation_service",
            side_effect=FashionPresentationError("Custom error."),
        ):
            result = action.run(self.judge_actor, presentation_id=self.presentation.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Custom error.")
