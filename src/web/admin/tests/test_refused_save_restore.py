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
from django.test import SimpleTestCase, TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from evennia_extensions.factories import ObjectDBFactory
from web.admin import ArxAdminSite
from web.admin.authoring.identity_map import CacheGuard, RefusedSaveRestoreMixin
from world.magic.admin import TechniqueAdmin
from world.magic.factories import TechniqueFactory, TechniqueMoraleEffectFactory
from world.magic.models import EffectType, Technique, TechniqueMoraleEffect


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


class CacheGuardPutsBackWhatTheFormsReach(TestCase):
    """What a bound form writes beyond its own row, which no journey can post cheaply.

    A form that picks a one-to-one target writes the target's reverse cache too, and a
    failed save that deleted a row marks it deleted. Both are on objects the game shares.
    """

    def test_a_one_to_one_target_picked_by_a_refused_form_does_not_point_back(self) -> None:
        stored, posted = (
            TechniqueFactory(damage_profile=False),
            TechniqueFactory(damage_profile=False),
        )
        row = TechniqueMoraleEffectFactory(technique=stored, base_morale=30)
        guard = CacheGuard()
        guard.keep(row)
        row.technique = posted

        guard.restore()

        self.assertIs(row.technique, stored)
        with self.assertRaises(TechniqueMoraleEffect.DoesNotExist):
            posted.morale_effect  # noqa: B018 - the reverse read is the assertion

    def test_a_row_a_rolled_back_save_deleted_is_usable_again(self) -> None:
        room = ObjectDBFactory(db_key="The Vestry")
        guard = CacheGuard()
        guard.keep(room)
        room._is_deleted = True

        guard.restore()

        self.assertNotIn("_is_deleted", room.__dict__)
        self.assertEqual(room.db_key, "The Vestry")
