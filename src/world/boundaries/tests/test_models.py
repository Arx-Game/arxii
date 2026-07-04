from django.core.exceptions import ValidationError
from django.test import TestCase

from world.boundaries.constants import BoundaryKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
    make_default_content_themes,
)
from world.boundaries.models import ContentTheme, PlayerBoundary


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


class DefaultContentThemesTests(TestCase):
    """The small starter ContentTheme catalog (#1771 task 8)."""

    def test_creates_the_expected_starter_keys(self):
        themes = make_default_content_themes()
        self.assertEqual(
            set(themes.keys()),
            {"child-endangerment", "suicide-self-harm", "sexual-violence", "torture"},
        )
        for key, theme in themes.items():
            self.assertEqual(theme.key, key)

    def test_idempotent_no_duplicate_rows(self):
        make_default_content_themes()
        make_default_content_themes()
        self.assertEqual(ContentTheme.objects.count(), 4)
