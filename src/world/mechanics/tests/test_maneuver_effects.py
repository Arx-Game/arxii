"""The maneuver effect catalog, the target scope columns and the admin (#4783)."""

from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from evennia_extensions.factories import AccountFactory
from world.mechanics.admin import ManeuverEffectAdmin, ModifierTargetAdmin
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    MANEUVER_EFFECT_DEFAULTS,
    MANEUVER_EFFECT_KIND,
    EffectKind,
    ManeuverEffectKey,
)
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ManeuverEffect, ModifierCategory, ModifierTarget


class EnsureManeuverEffectsTests(TestCase):
    def test_ensure_creates_eight_rows_with_todays_values(self):
        ensure_maneuver_effects()
        assert {e.key: e.base_value for e in ManeuverEffect.objects.all()} == (
            MANEUVER_EFFECT_DEFAULTS
        )
        assert len(MANEUVER_EFFECT_DEFAULTS) == 8
        assert ModifierCategory.objects.filter(name=MANEUVER_EFFECT_CATEGORY_NAME).exists()
        ensure_maneuver_effects()
        assert ManeuverEffect.objects.count() == 8
        assert ModifierCategory.objects.filter(name=MANEUVER_EFFECT_CATEGORY_NAME).count() == 1

    def test_ensure_keeps_an_edited_value(self):
        ensure_maneuver_effects()
        row = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        row.base_value = 7
        row.save()
        ensure_maneuver_effects()
        assert get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE).base_value == 7

    def test_every_key_has_a_kind_and_a_default(self):
        assert set(MANEUVER_EFFECT_KIND) == set(ManeuverEffectKey)
        assert set(MANEUVER_EFFECT_DEFAULTS) == set(ManeuverEffectKey)
        row = get_maneuver_effect(ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION)
        assert row.kind == EffectKind.PARTIAL_PROTECTION


class ModifierTargetScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_maneuver_effects()
        cls.category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.effect = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)
        cls.other_category = ModifierCategory.objects.create(name="other_test_category")

    def test_target_with_both_scopes_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTarget.objects.create(
                category=self.category,
                name="Both",
                scope_maneuver_effect=self.effect,
                scope_effect_kind=EffectKind.DAMAGE,
            )

    def test_maneuver_effect_target_needs_one_scope(self):
        neither = ModifierTarget(category=self.category, name="Neither")
        with self.assertRaises(ValidationError):
            neither.clean()
        one = ModifierTarget(category=self.category, name="One", scope_maneuver_effect=self.effect)
        one.clean()
        kind = ModifierTarget(
            category=self.category, name="Kind", scope_effect_kind=EffectKind.DAMAGE
        )
        kind.clean()
        both = ModifierTarget(
            category=self.category,
            name="Both",
            scope_maneuver_effect=self.effect,
            scope_effect_kind=EffectKind.DAMAGE,
        )
        with self.assertRaises(ValidationError):
            both.clean()
        ModifierTarget(category=self.other_category, name="Plain").clean()

    def test_other_category_refuses_a_scope(self):
        target = ModifierTarget(
            category=self.other_category, name="Stray", scope_maneuver_effect=self.effect
        )
        with self.assertRaises(ValidationError) as caught:
            target.clean()
        self.assertEqual(list(caught.exception.message_dict), ["scope_maneuver_effect"])

    def test_other_category_refuses_a_kind_on_the_kind_field(self):
        target = ModifierTarget(
            category=self.other_category,
            name="Stray kind",
            scope_effect_kind=EffectKind.PARTIAL_PROTECTION,
        )
        with self.assertRaises(ValidationError) as caught:
            target.clean()
        self.assertEqual(list(caught.exception.message_dict), ["scope_effect_kind"])


class ManeuverEffectAdminTests(TestCase):
    def test_admin_has_no_add_or_delete(self):
        ensure_maneuver_effects()
        model_admin = ManeuverEffectAdmin(ManeuverEffect, site)
        request = RequestFactory().get("/")
        request.user = AccountFactory(is_superuser=True, is_staff=True)
        row = get_maneuver_effect(ManeuverEffectKey.CHARGE_REACH)
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_delete_permission(request, row) is False
        assert "key" in model_admin.get_readonly_fields(request, row)


class ModifierTargetFormTests(TestCase):
    def test_form_labels_the_two_scope_fields_as_the_mockup_does(self):
        request = RequestFactory().get("/")
        request.user = AccountFactory(is_superuser=True, is_staff=True)
        form = ModifierTargetAdmin(ModifierTarget, site).get_form(request)()
        one = form.fields["scope_maneuver_effect"]
        kind = form.fields["scope_effect_kind"]
        assert one.label == "Scope - one effect"
        assert one.help_text == "This effect only."
        assert kind.label == "Scope - kind of effect"
        assert kind.help_text == (
            "This kind of effect on every maneuver; damage and the two condition kinds also "
            "reach techniques. Set this or the effect above, not both."
        )
