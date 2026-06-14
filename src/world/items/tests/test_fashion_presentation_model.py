"""Tests for the FashionPresentation model (#514)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.events.factories import EventFactory
from world.items.factories import FashionPresentationFactory
from world.items.models import FashionPresentation
from world.societies.factories import SocietyFactory


class FashionPresentationModelTests(TestCase):
    """Cover FashionPresentation defaults, str, and FK wiring."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)
        cls.presenter = CharacterSheetFactory()

    def test_defaults(self) -> None:
        """base_score and acclaim default to 0; outfit is optional."""
        presentation = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
            outfit=None,
        )
        self.assertEqual(presentation.base_score, 0)
        self.assertEqual(presentation.acclaim, 0)
        self.assertIsNone(presentation.outfit)

    def test_str(self) -> None:
        """__str__ returns the expected format."""
        presentation = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
            outfit=None,
        )
        expected = f"FashionPresentation({self.presenter.pk}@{self.event.pk})"
        self.assertEqual(str(presentation), expected)

    def test_factory_default_wiring(self) -> None:
        """FashionPresentationFactory builds a complete row without caller input."""
        presentation = FashionPresentationFactory()
        self.assertIsNotNone(presentation.pk)
        self.assertIsNotNone(presentation.event_id)
        self.assertIsNotNone(presentation.presenter_id)
        self.assertIsNotNone(presentation.perceiving_society_id)
        self.assertEqual(presentation.base_score, 0)
        self.assertEqual(presentation.acclaim, 0)

    def test_related_name_on_event(self) -> None:
        """event.fashion_presentations reverse manager is wired up."""
        presentation = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
        )
        self.assertIn(presentation, self.event.fashion_presentations.all())

    def test_related_name_on_presenter(self) -> None:
        """presenter.fashion_presentations reverse manager is wired up."""
        presentation = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
        )
        self.assertIn(presentation, self.presenter.fashion_presentations.all())

    def test_ordering(self) -> None:
        """Default ordering is newest-first by created_at."""
        first = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
        )
        second = FashionPresentationFactory(
            event=self.event,
            presenter=self.presenter,
            perceiving_society=self.society,
        )
        qs = list(FashionPresentation.objects.filter(event=self.event))
        # Newest (second) should come first.
        self.assertEqual(qs[0], second)
        self.assertEqual(qs[1], first)
