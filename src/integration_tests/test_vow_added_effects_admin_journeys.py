"""Journeys for authoring vow added effects in the plain Django admin (#4581).

Staff author what a covenant vow adds to a technique in admin: a header row plus its
payload rows as inlines. Each row shows a summary built only from its fields, so what
staff read back is what the row does, never free prose.

- The summary reads in plain words, and a bare row says it adds nothing yet.
- Editing a payload row changes the summary the next time it is read.
- The authoring rules (#4581 clean() rules) surface in the admin: a behavior-altering
  condition, a once-a-round row outside a fight, a damage row on an any-context effect.
- A good row saves, and its summary shows on its change page, the changelist, and the
  covenant role's own page.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from integration_tests.harness import JourneyCase
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.covenants.constants import VowEffectContext, VowEffectFrequency
from world.covenants.factories import (
    CovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
)
from world.covenants.models import VowAddedEffect
from world.covenants.perks.constants import PerkBeneficiary, Situation
from world.magic.constants import TechniqueFunction
from world.magic.factories import GiftFactory

HEADER_DEFAULTS = {
    "cast_context": VowEffectContext.ANY,
    "situation": "",
    "beneficiary": PerkBeneficiary.SELF,
    "frequency": VowEffectFrequency.EVERY_CAST,
    "unlock_thread_level": "0",
    "severity_per_thread_level": "0",
    "duration_per_thread_level": "0",
    "damage_per_thread_level": "0",
    "gift": "",
    "technique": "",
    "upgrades": "",
}


class VowAddedEffectSummaryTests(TestCase):
    """The summary is built only from the row's fields."""

    def test_the_summary_reads_in_plain_words(self) -> None:
        effect = VowAddedEffectFactory(
            unlock_thread_level=3,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            function=TechniqueFunction.WEAKEN,
            cast_context=VowEffectContext.IN_COMBAT,
            situation=Situation.TARGET_IS_BOSS,
            frequency=VowEffectFrequency.ONCE_PER_FIGHT,
        )
        VowAddedEffectDamageProfileFactory(
            effect=effect, damage_type=DamageTypeFactory(name="Fire")
        )

        self.assertEqual(
            effect.cached_effect_summary,
            "From thread 3. On covenant allies' Weaken casts, in a fight, "
            "when Target Is a Boss, once a fight: Deals Fire damage.",
        )

    def test_a_bare_row_says_it_adds_nothing_yet(self) -> None:
        effect = VowAddedEffectFactory(function=TechniqueFunction.HOLD)

        self.assertEqual(
            effect.cached_effect_summary,
            "On your own Hold / Lock casts: Adds nothing yet.",
        )

    def test_a_row_narrowed_to_a_gift_names_it(self) -> None:
        gift = GiftFactory(name="Shadowcraft")
        effect = VowAddedEffectFactory(
            function=TechniqueFunction.STRIKE,
            gift=gift,
            beneficiary=PerkBeneficiary.WHOLE_GROUP,
            cast_context=VowEffectContext.OUT_OF_COMBAT,
            frequency=VowEffectFrequency.EVERY_CAST,
        )
        VowAddedEffectAppliedConditionFactory(
            effect=effect, condition=ConditionTemplateFactory(name="Guarded")
        )

        self.assertEqual(
            effect.cached_effect_summary,
            "On your and covenant allies' Strike casts of Shadowcraft, outside a fight: "
            "Applies Guarded.",
        )

    def test_editing_a_payload_row_changes_the_summary(self) -> None:
        effect = VowAddedEffectFactory(cast_context=VowEffectContext.IN_COMBAT)
        self.assertEqual(
            effect.cached_effect_summary,
            "On your own Hold / Lock casts, in a fight: Adds nothing yet.",
        )

        VowAddedEffectAppliedConditionFactory(
            effect=effect, condition=ConditionTemplateFactory(name="Slowed")
        )

        self.assertEqual(
            effect.cached_effect_summary,
            "On your own Hold / Lock casts, in a fight: Applies Slowed.",
        )

    def test_editing_a_header_field_changes_the_summary(self) -> None:
        effect = VowAddedEffectFactory(cast_context=VowEffectContext.IN_COMBAT)
        self.assertEqual(
            effect.cached_effect_summary,
            "On your own Hold / Lock casts, in a fight: Adds nothing yet.",
        )

        effect.frequency = VowEffectFrequency.ONCE_PER_FIGHT
        effect.save()

        self.assertEqual(
            effect.cached_effect_summary,
            "On your own Hold / Lock casts, in a fight, once a fight: Adds nothing yet.",
        )


def _filled(bound_fields) -> dict[str, str]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data


class StaffAuthorVowAddedEffectsInAdmin(JourneyCase):
    """Staff add, read and refuse vow added effects in plain admin."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.role = CovenantRoleFactory()

    def add_post(self, inline: str | None = None, row: dict[str, object] | None = None, **header):
        """The add form's post, with one inline row filled in when asked for."""
        page = self.client.get(reverse("admin:arxii_vowaddedeffect_add"))
        self.assertEqual(page.status_code, 200)
        data = _filled(page.context["adminform"].form)
        data.update({"covenant_role": str(self.role.pk), "function": TechniqueFunction.HOLD})
        data.update({key: str(value) for key, value in HEADER_DEFAULTS.items()})
        data.update({key: str(value) for key, value in header.items()})
        for inline_formset in page.context["inline_admin_formsets"]:
            formset = inline_formset.formset
            data.update(_filled(formset.management_form))
            if formset.prefix != inline:
                continue
            data[f"{formset.prefix}-TOTAL_FORMS"] = "1"
            prefilled = _filled(formset.empty_form)
            for name, value in prefilled.items():
                data[name.replace("__prefix__", "0")] = value
            for name, value in (row or {}).items():
                data[f"{formset.prefix}-0-{name}"] = str(value)
        return data

    def test_staff_cannot_save_a_behavior_altering_condition(self) -> None:
        charm = ConditionTemplateFactory(
            name="Enthralled", category=ConditionCategoryFactory(alters_behavior=True)
        )
        data = self.add_post("applied_conditions", {"condition": charm.pk})

        response = self.client.post(reverse("admin:arxii_vowaddedeffect_add"), data)

        self.assertEqual(response.status_code, 200)
        [applied] = [
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.prefix == "applied_conditions"
        ]
        self.assertIn("condition", applied.forms[0].errors)
        self.assertFalse(VowAddedEffect.objects.exists())

    def test_staff_cannot_save_a_once_a_round_row_outside_a_fight(self) -> None:
        data = self.add_post(
            frequency=VowEffectFrequency.ONCE_PER_ROUND, cast_context=VowEffectContext.ANY
        )

        response = self.client.post(reverse("admin:arxii_vowaddedeffect_add"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("frequency", response.context["adminform"].form.errors)
        self.assertFalse(VowAddedEffect.objects.exists())

    def test_staff_cannot_save_damage_on_an_any_context_row(self) -> None:
        data = self.add_post("damage_profiles", {"base_damage": 4})

        response = self.client.post(reverse("admin:arxii_vowaddedeffect_add"), data)

        self.assertEqual(response.status_code, 200)
        [damage] = [
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.prefix == "damage_profiles"
        ]
        self.assertIn("set to In Combat", str(damage.forms[0].errors))
        self.assertFalse(VowAddedEffect.objects.exists())

    def test_staff_save_a_good_row_and_read_its_summary(self) -> None:
        data = self.add_post(
            "damage_profiles",
            {"base_damage": 4},
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_ROUND,
        )

        response = self.client.post(reverse("admin:arxii_vowaddedeffect_add"), data)

        self.assertEqual(response.status_code, 302, response.content[:600])
        effect = VowAddedEffect.objects.get()
        self.assertEqual(effect.damage_profiles.count(), 1)
        page = self.client.get(reverse("admin:arxii_vowaddedeffect_change", args=[effect.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(
            page,
            escape("On your own Hold / Lock casts, in a fight, once a round: Deals damage."),
        )

    def test_the_changelist_shows_each_summary(self) -> None:
        effect = VowAddedEffectFactory(covenant_role=self.role)

        response = self.client.get(reverse("admin:arxii_vowaddedeffect_changelist"))

        self.assertContains(response, escape(effect.cached_effect_summary))

    def test_the_role_page_lists_its_added_effects(self) -> None:
        effect = VowAddedEffectFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            function=TechniqueFunction.MEND,
        )

        response = self.client.get(reverse("admin:arxii_covenantrole_change", args=[self.role.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, escape(effect.cached_effect_summary))
