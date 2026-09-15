"""Authoring surfaces that did not exist, and two edits that served stale caches (#3712).

Three models the system already depended on had no admin page: ``PathGiftGrant``
(the path half of the CG technique menu) and the ``AuraPowerConfig`` /
``CapabilityPowerConfig`` singletons, whose missing rows the required-content
dashboard already reported while offering no page on which to create them.

The two cache tests break the invariant rather than asserting the fix: they read
a derived value, edit through the surface under test, and assert the next read
differs. Asserting only that a hook exists would pass with the hook doing nothing.
"""

from __future__ import annotations

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.classes.models import Path
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import TechniqueRemovedConditionFactory
from world.magic.models import (
    AuraPowerConfig,
    CapabilityPowerConfig,
    PathGiftGrant,
    TechniqueRemovedCondition,
)
from world.magic.services.technique_effects import technique_catalog_revision


def _inline_models(model) -> set:
    return {inline.model for inline in admin.site._registry[model].inlines}


class UnreachableAuthoringSurfacesTests(TestCase):
    """Each of these was reachable only from a shell before #3712."""

    def test_path_gift_grant_is_registered(self) -> None:
        """The path half of `get_technique_options`' union is now authorable.

        Its tradition-side sibling has had both an inline and a standalone admin
        since #2426; this half had neither, so the 76 authored path pools were
        fixture-loaded and could not be edited at all.
        """
        self.assertIn(PathGiftGrant, admin.site._registry)

    def test_path_gift_grant_composes_the_pool_with_a_picker(self) -> None:
        """`filter_horizontal` is where a pool is actually composed."""
        self.assertIn("starter_techniques", admin.site._registry[PathGiftGrant].filter_horizontal)

    def test_path_admin_reaches_its_gift_grants(self) -> None:
        self.assertIn(PathGiftGrant, _inline_models(Path))

    def test_both_power_configs_are_registered(self) -> None:
        """The required-content dashboard named these rows missing while no page existed."""
        self.assertIn(AuraPowerConfig, admin.site._registry)
        self.assertIn(CapabilityPowerConfig, admin.site._registry)

    def test_power_configs_are_singleton_guarded(self) -> None:
        """One row each, and never deletable, matching `LevelPowerConfigAdmin`."""
        for model in (AuraPowerConfig, CapabilityPowerConfig):
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry[model]
                self.assertTrue(model_admin.has_add_permission(None))
                model.objects.create()
                self.assertFalse(model_admin.has_add_permission(None))
                self.assertFalse(model_admin.has_delete_permission(None))


class UnreachableAuthoringSurfacesRenderTests(TestCase):
    """The pages resolve and render, not merely appear in the registry."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "authoringgaps", "authoringgaps@example.com", "pw-123456"
        )

    def test_add_forms_render(self) -> None:
        self.client.force_login(self.super)
        for url_name in (
            "admin:arxii_pathgiftgrant_add",
            "admin:arxii_aurapowerconfig_add",
            "admin:arxii_capabilitypowerconfig_add",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_path_change_form_renders_the_gift_grant_formset(self) -> None:
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_path_add"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("gift_grants-TOTAL_FORMS", resp.content.decode())


class DispelRowEditInvalidatesItsTechniqueTests(TestCase):
    """The same edit had two outcomes depending on which page staff used.

    Through the Technique page's inline, `TechniqueAdmin.save_related`
    invalidated the caches. Through this standalone changelist, nothing did, so
    the technique kept answering with its pre-edit `cached_removed_conditions`
    for the life of the process (techniques are SharedMemoryModels).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.row = TechniqueRemovedConditionFactory()
        cls.technique = cls.row.technique

    def _model_admin(self):
        return admin.site._registry[TechniqueRemovedCondition]

    def test_saving_a_dispel_row_drops_the_stale_payload_cache(self) -> None:
        """Prime the cache, edit through this admin, assert the next read differs."""
        self.assertEqual(len(self.technique.cached_removed_conditions), 1)

        self.row.remove_all_stacks = False
        self._model_admin().save_model(
            request=None, obj=self.row, form=_StubForm(self.row), change=True
        )

        rebuilt = self.technique.cached_removed_conditions
        self.assertEqual(len(rebuilt), 1)
        self.assertFalse(rebuilt[0].remove_all_stacks)

    def test_saving_a_dispel_row_bumps_the_catalog_revision(self) -> None:
        """The tuning corpus keys on the revision, not on the instance cache."""
        before = technique_catalog_revision()

        self._model_admin().save_model(
            request=None, obj=self.row, form=_StubForm(self.row), change=True
        )

        self.assertGreater(technique_catalog_revision(), before)

    def test_deleting_a_dispel_row_invalidates_too(self) -> None:
        """Removing a payload row changes the summary as much as adding one."""
        self.assertEqual(len(self.technique.cached_removed_conditions), 1)

        self._model_admin().delete_model(request=None, obj=self.row)

        self.assertEqual(len(self.technique.cached_removed_conditions), 0)


class ConditionEditBumpsCatalogRevisionTests(TestCase):
    """A condition's mechanics decide what techniques applying it are worth.

    The tuning corpus caches its evaluation for 24 hours keyed on the catalog
    revision, and #3683 wired the bump into technique-side writes only. Editing
    a `ConditionModifierEffect` value left staff tuning against the number they
    had just changed, with nothing to tell them.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "conditionrevision", "conditionrevision@example.com", "pw-123456"
        )
        cls.condition = ConditionTemplateFactory()

    def test_saving_a_condition_bumps_the_revision(self) -> None:
        self.client.force_login(self.super)
        before = technique_catalog_revision()

        model_admin = admin.site._registry[type(self.condition)]
        model_admin.save_related(
            request=None, form=_StubForm(self.condition), formsets=[], change=True
        )

        self.assertGreater(technique_catalog_revision(), before)


class _StubForm:
    """The one attribute `ModelAdmin.save_related` reads off the form.

    Django's own `save_related` calls `form.save_m2m()`; the admin under test
    calls `super()` first, so the stub supplies both.
    """

    def __init__(self, instance) -> None:
        self.instance = instance

    def save_m2m(self) -> None:
        return None
