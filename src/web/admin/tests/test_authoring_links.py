"""Tests for the shared workbench deep-link builder (#3020)."""

from django.test import TestCase
from django.urls import reverse

from web.admin.authoring.links import admin_change_url, workbench_editor_url


class WorkbenchEditorUrlTests(TestCase):
    """One URL shape, shared by every stock-admin surface that links into the workbench."""

    def test_builds_editor_url_with_model_and_pk_query(self) -> None:
        url = workbench_editor_url("magic.EffectType", 7)

        expected = f"{reverse('admin_authoring_editor')}?model=magic.EffectType&pk=7"
        self.assertEqual(url, expected)


class AdminChangeUrlTests(TestCase):
    """The outward link, shared by the related-entries pane and the backlog queue."""

    def test_builds_change_url_for_a_registered_model(self) -> None:
        url = admin_change_url("traits.Trait", 7)

        self.assertEqual(url, reverse("admin:arxii_trait_change", args=[7]))

    def test_returns_none_for_a_model_with_no_registered_admin(self) -> None:
        """Not every credited model has a ModelAdmin; callers render nothing rather than 500."""
        self.assertIsNone(admin_change_url("builders.BuildingKind", 7))

    def test_returns_none_for_an_unresolvable_label(self) -> None:
        self.assertIsNone(admin_change_url("nosuchdomain.NoSuchModel", 7))
