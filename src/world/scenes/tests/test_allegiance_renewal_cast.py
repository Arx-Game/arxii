"""Renewing a charm is a cast, never a fight; a damage cast still opens one (#4091).

``is_allegiance_renewal`` (``world.magic.services.hostility``) intercepts a recast
of a pure allegiance technique on a target the caster already holds, routing it
through the plain immediate-cast path instead of ``is_technique_hostile``'s combat
seed. The unit tests below exercise the predicate directly (fast tier, no cast);
the integration tests exercise the full ``request_technique_cast`` pipeline, which
goes through ``bulk_apply_conditions`` — tagged ``postgres`` only if the fast tier
actually raises ``NotSupportedError`` on it (it doesn't: ``has_progression=False``
by factory default skips the DISTINCT ON path).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.models import CombatEncounter
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import bulk_apply_conditions, get_active_conditions
from world.conditions.types import BulkConditionApplication
from world.magic.factories import (
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models import CharacterAnima
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.hostility import is_allegiance_renewal
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_hostile_castable_technique,
)

# ---------------------------------------------------------------------------
# Unit tests — is_allegiance_renewal, no cast
# ---------------------------------------------------------------------------


class IsAllegianceRenewalUnitTests(TestCase):
    """Fast-tier unit coverage of the predicate itself, built from factories directly."""

    @classmethod
    def setUpTestData(cls):
        cls.caster_sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.charm_template = ConditionTemplateFactory(
            name="Renewal unit charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
        )

    def _pure_charm_technique(self):
        technique = TechniqueFactory(damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=self.charm_template,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=0,
        )
        return technique

    def _charm_instance(self, *, source_sheet):
        return ConditionInstanceFactory(
            target=self.target_sheet.character,
            condition=self.charm_template,
            source_character=source_sheet.character,
        )

    def test_true_when_caster_already_holds_the_target(self):
        technique = self._pure_charm_technique()
        self._charm_instance(source_sheet=self.caster_sheet)

        self.assertTrue(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_with_damage_profile(self):
        technique = TechniqueFactory()  # default auto-seeds a damage profile
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=self.charm_template,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=0,
        )
        self._charm_instance(source_sheet=self.caster_sheet)

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_with_removed_condition_rows(self):
        technique = self._pure_charm_technique()
        TechniqueRemovedConditionFactory(technique=technique)
        self._charm_instance(source_sheet=self.caster_sheet)

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_when_condition_application_is_not_allegiance_setting(self):
        plain_condition = ConditionTemplateFactory(name="Plain unit condition")
        technique = TechniqueFactory(damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=plain_condition,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=0,
        )
        self._charm_instance(source_sheet=self.caster_sheet)

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_when_target_has_no_allegiance_instance(self):
        technique = self._pure_charm_technique()

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_when_instance_sourced_by_a_different_character(self):
        technique = self._pure_charm_technique()
        self._charm_instance(source_sheet=self.other_sheet)

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )

    def test_false_with_no_condition_application_rows_at_all(self):
        technique = TechniqueFactory(damage_profile=False)
        self._charm_instance(source_sheet=self.caster_sheet)

        self.assertFalse(
            is_allegiance_renewal(
                technique,
                caster=self.caster_sheet.character,
                target=self.target_sheet.character,
            )
        )


# ---------------------------------------------------------------------------
# Integration tests — full request_technique_cast pipeline
# ---------------------------------------------------------------------------


class AllegianceRenewalCastIntegrationTests(CastScenarioMixin):
    """Full coverage: renew is a cast, a different caster isn't, strike-first still fights."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.charm_template = ConditionTemplateFactory(
            name="Renewal integration charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
        )

    def _pure_charm_technique(self):
        from actions.factories import ActionTemplateFactory

        # intensity >> control so effective_cost > 0 despite the runtime control
        # bonus every caster gets (mirrors test_scene_magic_integration.py's
        # "costly_technique": control_delta = runtime_control - runtime_intensity
        # would otherwise erase a low base_cost).
        technique = TechniqueFactory(
            damage_profile=False,
            action_template=ActionTemplateFactory(),
            intensity=15,
            control=1,
            anima_cost=5,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=self.charm_template,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=0,
        )
        return technique

    def _charm_target_from(self, caster_persona):
        """Apply the charm template to self.target, sourced by caster_persona's character."""
        bulk_apply_conditions(
            [
                BulkConditionApplication(
                    target=self.target.character_sheet.character,
                    template=self.charm_template,
                )
            ],
            source_character=caster_persona.character_sheet.character,
        )

    def test_renewal_creates_no_encounter(self):
        self._charm_target_from(self.caster)
        technique = self._pure_charm_technique()
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

        self.assertIsNone(cast.encounter)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())
        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

    def test_renewal_refreshes_the_existing_instance(self):
        self._charm_target_from(self.caster)
        instance = get_active_conditions(
            self.target.character_sheet.character, condition=self.charm_template
        ).get()
        # Simulate time passing: the charm is about to lapse.
        instance.rounds_remaining = 1
        instance.save()

        technique = self._pure_charm_technique()
        grant_technique(self.caster, technique)

        # Force a guaranteed-success roll so the row's minimum_success_level=0
        # gate clears deterministically (real check rolls are otherwise random).
        with patch("world.checks.services.random.randint", return_value=100):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                target_persona=self.target,
                technique=technique,
            )

        instance.refresh_from_db()
        self.assertEqual(instance.rounds_remaining, self.charm_template.default_duration_value)

    def test_renewal_still_charges_anima(self):
        self._charm_target_from(self.caster)
        technique = self._pure_charm_technique()
        grant_technique(self.caster, technique)
        anima = CharacterAnima.objects.get(character=self.caster.character_sheet)
        before = anima.current

        request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

        anima.refresh_from_db()
        self.assertLess(anima.current, before)

    def test_different_caster_is_not_a_renewal_and_routes_hostile(self):
        self._charm_target_from(self.caster)
        technique = self._pure_charm_technique()

        other_caster = self._make_other_caster()
        grant_technique(other_caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=other_caster,
            target_persona=self.target,
            technique=technique,
        )

        self.assertIsNotNone(cast.encounter)

    def test_strike_first_damage_cast_still_opens_combat(self):
        self._charm_target_from(self.caster)
        damage_technique = make_hostile_castable_technique()
        grant_technique(self.caster, damage_technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=damage_technique,
        )

        self.assertIsNotNone(cast.encounter)
        cast.encounter.refresh_from_db()
        self.assertTrue(cast.encounter.initiated_by_pc_side)

    def _make_other_caster(self):
        from world.magic.factories import CharacterAnimaFactory
        from world.scenes.factories import PersonaFactory
        from world.vitals.models import CharacterVitals

        other = PersonaFactory()
        CharacterAnimaFactory(character=other.character_sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=other.character_sheet,
            health=50,
            max_health=50,
            base_max_health=50,
        )
        return other
