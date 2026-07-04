from django.core.exceptions import ValidationError
from django.test import TestCase

from world.boundaries.constants import BoundaryKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
)
from world.boundaries.models import PlayerBoundary


class PlayerBoundaryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.theme = ContentThemeFactory(key="child-endangerment", name="Child endangerment")

    def test_hard_line_requires_theme(self):
        boundary = PlayerBoundaryFactory.build(kind=BoundaryKind.HARD_LINE, theme=None)
        with self.assertRaises(ValidationError):
            boundary.clean()

    def test_hard_line_forced_private(self):
        # A HARD_LINE authored as shareable is coerced/rejected to PRIVATE.
        boundary = PlayerBoundaryFactory.build(
            kind=BoundaryKind.HARD_LINE,
            theme=self.theme,
            visibility_mode=PlayerBoundary.VisibilityMode.PUBLIC,
        )
        with self.assertRaises(ValidationError):
            boundary.clean()

    def test_advisory_allows_no_theme_and_sharing(self):
        boundary = PlayerBoundaryFactory.build(
            kind=BoundaryKind.ADVISORY,
            theme=None,
            visibility_mode=PlayerBoundary.VisibilityMode.PUBLIC,
        )
        boundary.clean()  # no raise


class TreasuredSubjectModelTests(TestCase):
    def test_treasured_subject_str(self):
        ts = TreasuredSubjectFactory()
        self.assertIn(ts.get_subject_kind_display(), str(ts))
