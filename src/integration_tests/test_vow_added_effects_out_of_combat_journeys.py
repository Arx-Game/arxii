"""Journeys for vow added effects in a scene (#4581): a covenant vow adds to a cast.

Ysmay and Hobb share a Durance covenant; Wren is a bystander. Ysmay's vow carries a
staff-authored ``VowAddedEffect`` row on the CLEANSE function: a treatment child
(ALLY) that rides her own cleanses and her covenant allies' cleanses alike
(WHOLE_GROUP). Each journey casts a CLEANSE-tagged technique the way the web client
does (``cast_technique`` through dispatch) inside a scene and reads back what the
vow added: the ``TreatmentAttempt`` row the treatment leaves, or the condition a
vow condition row lands.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

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
from world.conditions.models import ConditionInstance, ConditionTemplate, TreatmentAttempt
from world.covenants.constants import CovenantType, VowEffectContext
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectFactory,
    VowAddedEffectRemovedConditionFactory,
    VowAddedEffectTreatmentFactory,
    engage_vow_with_thread,
)
from world.covenants.models import CharacterCovenantRole, VowAddedEffect
from world.covenants.perks.constants import PerkBeneficiary
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models import Technique, TechniqueTreatment
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals


class _FixedTreatmentCheck:
    """Minimal stand-in for a ``CheckResult``: just what ``perform_treatment`` reads."""

    def __init__(self, outcome: CheckOutcome) -> None:
        self.outcome = outcome
        self.success_level = outcome.success_level


@contextmanager
def casting_at(outcome_name: str) -> Iterator[None]:
    """The cast's own check, and the treatment's check inside it, land at ``outcome_name``."""
    outcome = CheckOutcome.objects.get(name=outcome_name)
    with (
        patch(
            "world.conditions.services.perform_check_with_modifiers",
            return_value=_FixedTreatmentCheck(CheckOutcome.objects.get(name="Success")),
        ),
        force_check_outcome(outcome),
    ):
        yield


class VowAddedEffectsInAScene(JourneyCase):
    """Ysmay holds the vow; Hobb is a covenant ally; Wren stands outside the covenant."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.room = self.make_room("The Infirmary")
        SceneFactory(room=self.room)
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.template = ActionTemplateFactory(check_type=check_type)

        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.cleanse = self.cleanse_technique()
        self.ysmay = self.player("Ysmay")
        self.hobb = self.player("Hobb")
        self.wren = self.player("Wren")
        engage_vow_with_thread(
            self.ysmay.sheet_data, self.role, covenant=self.covenant, thread_level=2
        )
        self.hobbs_vow = self.swear_hobb()

        # The treatment the vow adds: it mends this condition, wherever an ally carries it.
        self.fever = ConditionTemplateFactory(name="Marsh Fever")
        self.vow_treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=self.fever,
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
        )
        for character in (self.ysmay, self.hobb, self.wren):
            ConditionInstanceFactory(target=character, condition=self.fever, severity=5)

    # -- setup helpers ----------------------------------------------------------

    def cleanse_technique(self) -> Technique:
        """A castable CLEANSE technique that names an ally and carries no treatment of its own."""
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.template,
        )
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.CLEANSE)
        # An ALLY removed-condition row on a condition nobody carries: it makes the
        # technique ally-aimed (so it can name Ysmay) without touching the fever.
        TechniqueRemovedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Nothing To Cleanse"),
            target_kind=ConditionTargetKind.ALLY,
        )
        return technique

    def player(self, name: str) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        grant_technique(sheet.primary_persona, self.cleanse)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        return character

    def swear_hobb(self) -> CharacterCovenantRole:
        """Hobb takes an engaged role in Ysmay's covenant."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        return engage_vow_with_thread(
            self.hobb.sheet_data, role, covenant=self.covenant, thread_level=1
        )

    def ysmays_row(self, **row: object) -> VowAddedEffect:
        """Ysmay's vow row on CLEANSE for the whole group, any context unless overridden."""
        fields = {
            "covenant_role": self.role,
            "function": TechniqueFunction.CLEANSE,
            "beneficiary": PerkBeneficiary.WHOLE_GROUP,
            "cast_context": VowEffectContext.ANY,
            **row,
        }
        return VowAddedEffectFactory(**fields)

    def with_a_treatment(self, **row: object) -> VowAddedEffect:
        effect = self.ysmays_row(**row)
        VowAddedEffectTreatmentFactory(
            effect=effect,
            treatment_template=self.vow_treatment,
            target_kind=ConditionTargetKind.ALLY,
        )
        return effect

    # -- the cast ---------------------------------------------------------------

    def cast(self, caster: ObjectDB, target: ObjectDB, *, outcome: str = "Success") -> None:
        with casting_at(outcome):
            result = self.web(
                caster,
                "cast_technique",
                technique_id=self.cleanse.pk,
                target_persona_id=target.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)

    def treated(self, helper: ObjectDB, target: ObjectDB) -> bool:
        return TreatmentAttempt.objects.filter(
            helper=helper.sheet_data, target=target.sheet_data, treatment=self.vow_treatment
        ).exists()

    def carries(self, character: ObjectDB, condition: ConditionTemplate) -> bool:
        return ConditionInstance.objects.filter(target=character, condition=condition).exists()

    # -- journeys -----------------------------------------------------------------

    def test_an_allys_cleanse_also_treats_through_the_holders_vow(self) -> None:
        self.with_a_treatment()

        self.cast(self.hobb, self.ysmay)

        self.assertTrue(self.treated(self.hobb, self.ysmay))

    def test_the_holders_own_cleanse_treats_too(self) -> None:
        self.with_a_treatment()

        self.cast(self.ysmay, self.hobb)

        self.assertTrue(self.treated(self.ysmay, self.hobb))

    def test_a_holder_in_another_room_adds_nothing(self) -> None:
        self.with_a_treatment()
        self.ysmay.move_to(self.make_room("The Cellar"), quiet=True, move_hooks=False)

        self.cast(self.hobb, self.wren)

        self.assertFalse(TreatmentAttempt.objects.filter(treatment=self.vow_treatment).exists())

    def test_an_in_combat_row_stays_quiet_out_of_combat(self) -> None:
        self.with_a_treatment(cast_context=VowEffectContext.IN_COMBAT)

        self.cast(self.hobb, self.ysmay)

        self.assertFalse(TreatmentAttempt.objects.filter(treatment=self.vow_treatment).exists())

    def test_a_disengaged_caster_gets_nothing(self) -> None:
        self.with_a_treatment()
        self.hobbs_vow.engaged = False
        self.hobbs_vow.save(update_fields=["engaged"])
        self.hobb.covenant_roles.invalidate()

        self.cast(self.hobb, self.ysmay)

        self.assertFalse(TreatmentAttempt.objects.filter(treatment=self.vow_treatment).exists())

    def test_a_vow_condition_row_lands_on_a_successful_cast(self) -> None:
        bolstered = ConditionTemplateFactory(name="Bolstered")
        effect = self.ysmays_row()
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=bolstered,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )

        self.cast(self.hobb, self.ysmay)

        self.assertTrue(self.carries(self.ysmay, bolstered))

    def test_a_cast_below_success_adds_no_vow_effect_even_at_level_zero(self) -> None:
        bolstered = ConditionTemplateFactory(name="Bolstered")
        effect = self.with_a_treatment()
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=bolstered,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )

        self.cast(self.hobb, self.ysmay, outcome="Partial Success")

        self.assertFalse(self.carries(self.ysmay, bolstered))
        self.assertFalse(TreatmentAttempt.objects.filter(treatment=self.vow_treatment).exists())

    def test_a_vow_removal_strips_the_condition_after_the_techniques_own_treatment(
        self,
    ) -> None:
        # The technique itself mends the fever; the vow then strips it. The mend must
        # land first, or the strip leaves it nothing to mend.
        own_mend = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=self.fever,
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
        )
        TechniqueTreatment.objects.create(
            technique=self.cleanse,
            treatment_template=own_mend,
            target_kind=ConditionTargetKind.ALLY,
        )
        VowAddedEffectRemovedConditionFactory(
            effect=self.ysmays_row(),
            condition=self.fever,
            target_kind=ConditionTargetKind.ALLY,
        )

        self.cast(self.hobb, self.ysmay)

        self.assertTrue(
            TreatmentAttempt.objects.filter(
                helper=self.hobb.sheet_data, target=self.ysmay.sheet_data, treatment=own_mend
            ).exists()
        )
        self.assertFalse(self.carries(self.ysmay, self.fever))
        self.assertTrue(self.carries(self.hobb, self.fever))
        self.assertTrue(self.carries(self.wren, self.fever))
