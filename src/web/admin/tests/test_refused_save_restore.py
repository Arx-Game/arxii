"""Every admin page over shared rows restores a refused save (#4626, ADR-4626).

A refused save on a stock admin page leaves its posted values on the identity-mapped
rows unless the admin carries ``RefusedSaveRestoreMixin``. ``ArxAdminSite.register``
mixes it in; this walks the live registry so an admin that reaches it any other way
(a hand-built registry entry, a register override that skips it) fails here. The
behavior itself is proven by the journeys in
``integration_tests/test_refused_admin_saves_journeys``.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import SimpleTestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from web.admin import ArxAdminSite
from web.admin.authoring.identity_map import RefusedSaveRestoreMixin
from world.magic.admin import TechniqueAdmin
from world.magic.models import EffectType, Technique


def unprotected_admins(site: admin.AdminSite) -> list[str]:
    """Each registered admin that binds forms to shared rows without the restore.

    "Shared rows": the admin's own model, or a model one of its inlines edits, is a
    ``SharedMemoryModel``. Read off the registered instances, not off the site's own
    predicate, so a wrong predicate cannot hide an admin from this check.
    """
    missing = []
    for model, model_admin in site._registry.items():
        edited = [model, *(inline.model for inline in model_admin.inlines)]
        if any(issubclass(m, SharedMemoryModel) for m in edited) and not isinstance(
            model_admin, RefusedSaveRestoreMixin
        ):
            missing.append(f"{model.__name__}: {type(model_admin).__qualname__}")
    return missing


class EveryAdminOverSharedRowsRestoresARefusedSave(SimpleTestCase):
    def test_the_live_registry_has_no_unprotected_admin(self) -> None:
        self.assertEqual(unprotected_admins(admin.site), [])

    def test_the_registry_covers_our_admins_and_evennias(self) -> None:
        for model in (Technique, EffectType, ObjectDB):
            with self.subTest(model=model.__name__):
                self.assertIsInstance(admin.site._registry[model], RefusedSaveRestoreMixin)

    def test_an_admin_registered_around_the_site_is_reported(self) -> None:
        site = ArxAdminSite(name="probe")
        site._registry[EffectType] = admin.ModelAdmin(EffectType, site)

        self.assertEqual(unprotected_admins(site), ["EffectType: ModelAdmin"])

    def test_registering_puts_the_restore_first_and_keeps_the_admin_itself(self) -> None:
        site = ArxAdminSite(name="probe")
        site.register(Technique, TechniqueAdmin)

        registered = site._registry[Technique]
        self.assertIs(type(registered).__mro__[1], RefusedSaveRestoreMixin)
        self.assertIsInstance(registered, TechniqueAdmin)
        self.assertEqual(type(registered).__name__, "TechniqueAdmin")

    def test_an_admin_over_plain_rows_is_left_as_written(self) -> None:
        site = ArxAdminSite(name="probe")
        site.register(Group)

        self.assertIs(type(site._registry[Group]), admin.ModelAdmin)
