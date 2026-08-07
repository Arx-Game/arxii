"""Tests for the shared workbench deep-link builder (#3020)."""

from django.test import TestCase
from django.urls import reverse

from web.admin.authoring.links import workbench_editor_url


class WorkbenchEditorUrlTests(TestCase):
    """One URL shape, shared by every stock-admin surface that links into the workbench."""

    def test_builds_editor_url_with_model_and_pk_query(self) -> None:
        url = workbench_editor_url("magic.EffectType", 7)

        expected = f"{reverse('admin_authoring_editor')}?model=magic.EffectType&pk=7"
        self.assertEqual(url, expected)
