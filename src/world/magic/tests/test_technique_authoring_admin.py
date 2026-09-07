"""The staff authoring surface for a technique's mechanical payload (#3682).

``TechniqueAdmin`` shipped inlines for capability grants, removals, treatments
and function tags — and none for the two payload families that decide what a
technique actually does on cast. ``TechniqueAppliedCondition`` carries the
``target_kind`` the cast gate reads and the severity scaling that gives an
applied condition its magnitude; ``TechniqueDamageProfile`` carries the damage.
Staff could describe an ability in prose and had no supported way to author
either one.
"""

from __future__ import annotations

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.conditions.models import ConditionModifierEffect, ConditionTemplate
from world.magic.models.techniques import (
    Technique,
    TechniqueAppliedCondition,
    TechniqueDamageProfile,
)


def _inline_models(model) -> set[type]:
    return {inline.model for inline in admin.site._registry[model].inlines}


class TechniquePayloadInlineTests(TestCase):
    def test_applied_conditions_are_authorable_on_the_technique_page(self):
        self.assertIn(TechniqueAppliedCondition, _inline_models(Technique))

    def test_damage_profiles_are_authorable_on_the_technique_page(self):
        self.assertIn(TechniqueDamageProfile, _inline_models(Technique))

    def test_damage_profile_has_no_standalone_admin(self):
        """Inline-only, deliberately.

        The authoring-relations panel decides whether to render a neighbour's
        edit link by whether its model is registered
        (``test_admin_link_omitted_for_unregistered_neighbor_model``), and a
        damage row means nothing apart from its technique — the technique page
        is the whole of its authoring surface.
        """
        self.assertNotIn(TechniqueDamageProfile, admin.site._registry)

    def test_condition_stat_modifiers_are_authorable_on_the_condition_page(self):
        """Guarded/Inspired advertise a stat change nothing delivered.

        ``ConditionModifierEffect`` is the row every stat reader folds in, and
        it had no admin surface at all — a condition authored in the admin got
        a name, a description, and no mechanical effect.
        """
        self.assertIn(ConditionModifierEffect, _inline_models(ConditionTemplate))


class TechniqueChangeFormRendersPayloadInlinesTests(TestCase):
    """The inlines reach the page, not just the class attribute."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "techauthoringadmin", "techauthoring@example.com", "pw-123456"
        )

    def test_add_form_renders_both_payload_formsets(self):
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_technique_add"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("condition_applications-TOTAL_FORMS", body)
        self.assertIn("damage_profiles-TOTAL_FORMS", body)

    def test_condition_add_form_renders_the_stat_modifier_formset(self):
        self.client.force_login(self.super)

        resp = self.client.get(reverse("admin:arxii_conditiontemplate_add"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("conditionmodifiereffect_set-TOTAL_FORMS", resp.content.decode())
