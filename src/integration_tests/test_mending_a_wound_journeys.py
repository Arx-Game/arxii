"""Journeys for healing that depends on the technique (#4600, Part F of #4573).

Ilse carries a wound that did 20 damage. Aldo knows Field Mend, authored to heal a
wound at most 0.40 of its damage; Sera knows Deep Restoration, authored at 0.70; Wren
knows Field Mend too. Both techniques perform the same treatment, so the fraction is
the technique's, not the treatment's. Each healer casts the way the web client does
(``cast_technique`` through dispatch) and the journey reads back what Ilse's health
and the wound's running total hold.

The authored numbers fix the expected values: 0.40 x 20 = 8 and 0.70 x 20 = 14, and
no combination of casts heals past the highest fraction anyone cast.

Staff author the fraction in the Technique admin's treatment inline: 0.40 saves, and a
fraction above the 0.75 ceiling is refused with the field named.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import TreatmentAttempt
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import Technique, TechniqueTreatment
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals, WoundDetails

WOUND_DAMAGE = 20
ILSE_HEALTH = 10


class _FixedTreatmentCheck:
    """Minimal stand-in for a ``CheckResult``: just what ``perform_treatment`` reads."""

    def __init__(self, outcome: CheckOutcome) -> None:
        self.outcome = outcome
        self.success_level = outcome.success_level


@contextmanager
def casting_well() -> Iterator[None]:
    """The cast's own check, and the treatment's check inside it, land at Success."""
    success = CheckOutcome.objects.get(name="Success")
    with (
        patch(
            "world.conditions.services.perform_check_with_modifiers",
            return_value=_FixedTreatmentCheck(success),
        ),
        force_check_outcome(success),
    ):
        yield


class TwoHealersTendOneWound(JourneyCase):
    """Aldo, Sera and Wren each tend Ilse's 20-damage wound with their own technique."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.room = self.make_room("The Field Hospital")
        SceneFactory(room=self.room)
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.action_template = ActionTemplateFactory(check_type=check_type)

        wound_condition = ConditionTemplateFactory(name="Torn Shoulder")
        # Offers far more than any cap allows, so the fraction is what decides.
        self.binding = TreatmentTemplateFactory(
            name="Binding the Wound",
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=wound_condition,
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            scene_required=False,
            once_per_scene_per_helper=False,
            reduction_on_crit=0,
            reduction_on_success=0,
            reduction_on_partial=0,
            mend_on_crit=50,
            mend_on_success=50,
            mend_on_partial=50,
        )
        self.field_mend = self.healing_technique("Field Mend", Decimal("0.40"))
        self.deep_restoration = self.healing_technique("Deep Restoration", Decimal("0.70"))

        self.ilse = self.player("Ilse", knows=None)
        self.aldo = self.player("Aldo", knows=self.field_mend)
        self.sera = self.player("Sera", knows=self.deep_restoration)
        self.wren = self.player("Wren", knows=self.field_mend)

        self.wound = ConditionInstanceFactory(
            target=self.ilse, condition=wound_condition, severity=1
        )
        WoundDetails.objects.create(condition_instance=self.wound, damage_taken=WOUND_DAMAGE)

    # -- setup helpers ----------------------------------------------------------

    def healing_technique(self, name: str, fraction: Decimal) -> Technique:
        """A castable technique whose one payload tends an ally's wound up to ``fraction``."""
        technique = TechniqueFactory(
            name=name,
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.action_template,
        )
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=self.binding,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            mend_cap_fraction=fraction,
        )
        return technique

    def player(self, name: str, *, knows: Technique | None) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        if knows is not None:
            grant_technique(sheet.primary_persona, knows)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=ILSE_HEALTH, max_health=100, base_max_health=100
        )
        return character

    # -- the cast and what it left ----------------------------------------------

    def cast(self, healer: ObjectDB, technique: Technique) -> None:
        with casting_well():
            result = self.web(
                healer,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=self.ilse.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)

    def mended_by(self, healer: ObjectDB) -> int:
        return TreatmentAttempt.objects.get(
            helper=healer.sheet_data, target=self.ilse.sheet_data, treatment=self.binding
        ).health_mended

    def ilses_health(self) -> int:
        return (
            CharacterVitals.objects.filter(character_sheet=self.ilse.sheet_data)
            .values_list("health", flat=True)
            .get()
        )

    def mended_on_the_wound(self) -> int:
        return (
            WoundDetails.objects.filter(condition_instance=self.wound)
            .values_list("health_mended_total", flat=True)
            .get()
        )

    # -- journeys -----------------------------------------------------------------

    def test_a_field_mend_then_a_deep_restoration_stop_at_the_deeper_share(self) -> None:
        self.cast(self.aldo, self.field_mend)
        self.assertEqual(self.mended_by(self.aldo), 8)

        self.cast(self.sera, self.deep_restoration)
        self.assertEqual(self.mended_by(self.sera), 6)

        self.cast(self.wren, self.field_mend)
        self.assertEqual(self.mended_by(self.wren), 0)

        self.assertEqual(self.mended_on_the_wound(), 14)
        self.assertEqual(self.ilses_health(), ILSE_HEALTH + 14)

    def test_a_deep_restoration_first_leaves_a_field_mend_nothing(self) -> None:
        self.cast(self.sera, self.deep_restoration)
        self.assertEqual(self.mended_by(self.sera), 14)

        self.cast(self.aldo, self.field_mend)
        self.assertEqual(self.mended_by(self.aldo), 0)

        self.assertEqual(self.mended_on_the_wound(), 14)
        self.assertEqual(self.ilses_health(), ILSE_HEALTH + 14)


def _filled(bound_fields) -> dict[str, str]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        elif isinstance(value, list):
            data[bound.html_name] = value  # type: ignore[assignment]
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data


class StaffSetTheFractionInTheTechniqueAdmin(JourneyCase):
    """Staff open a healing technique's change form and set its treatment's fraction."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.technique = TechniqueFactory(name="Field Mend", damage_profile=False)
        self.row = TechniqueTreatment.objects.create(
            technique=self.technique,
            treatment_template=TreatmentTemplateFactory(name="Binding the Wound"),
            target_kind=ConditionTargetKind.ALLY,
        )
        self.url = reverse("admin:arxii_technique_change", args=[self.technique.pk])

    def change_post(self, fraction: str) -> dict[str, str]:
        """The change form exactly as a browser posts it, with the treatment's fraction set."""
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(_filled(formset.management_form))
            for form in formset.forms:
                data.update(_filled(form))
        data[f"{self.treatment_formset(page).prefix}-0-mend_cap_fraction"] = fraction
        return data

    def treatment_formset(self, response):
        [formset] = [
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.model is TechniqueTreatment
        ]
        return formset

    def stored_fraction(self) -> Decimal:
        return (
            TechniqueTreatment.objects.filter(pk=self.row.pk)
            .values_list("mend_cap_fraction", flat=True)
            .get()
        )

    def test_the_treatment_inline_shows_the_fraction(self) -> None:
        page = self.client.get(self.url)

        formset = self.treatment_formset(page)
        self.assertIn("mend_cap_fraction", formset.forms[0].fields)
        self.assertContains(page, f'name="{formset.prefix}-0-mend_cap_fraction"')
        self.assertContains(page, 'value="0.75"')

    def test_staff_save_a_field_mend_at_forty_percent(self) -> None:
        response = self.client.post(self.url, self.change_post("0.40"))

        self.assertEqual(response.status_code, 302, response.content[:800])
        self.assertEqual(self.stored_fraction(), Decimal("0.40"))

    def test_a_fraction_above_the_ceiling_is_refused_by_name(self) -> None:
        response = self.client.post(self.url, self.change_post("0.80"))

        self.assertEqual(response.status_code, 200)
        errors = self.treatment_formset(response).forms[0].errors
        self.assertIn("mend_cap_fraction", errors)
        self.assertIn("less than or equal to 0.75", str(errors["mend_cap_fraction"]))
        self.assertEqual(self.stored_fraction(), Decimal("0.75"))
