"""Social maneuvers read their checks and Rally's condition by designation (#4739).

Rally rolls the check the ``RALLIED`` ``SurgeTuning`` names and applies the condition
``SocialManeuverConfig.rally_success_condition`` designates; Taunt, Demoralize and Parley
roll the check types designated on the same config. A row's name never matters. A
rallier whose vow scales "Rally: surge intensity" (a ``VowStatScaling`` row on a maneuver
effect target, #4783) surges the rallied ally more.

The journeys ``BeingRallied`` / ``BeingTauntedByAnotherPlayer``
(``integration_tests.test_surge_rolls_journeys``) and ``AVowedRallySurgesMore``
(``integration_tests.test_vow_surge_scaling_journeys``) play these through telnet; what
stays here is the per-verb designation edges no journey reaches (unset designations, the
name-independence of each verb, the seed's designation pass).
"""

from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.checks.models import CheckType
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    FALTER_MORALE_THRESHOLD,
    ParticipantStatus,
    SurgeTriggerKind,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SocialManeuverConfigFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import (
    _resolve_demoralize,
    _resolve_parley,
    _resolve_rally,
    _resolve_taunt,
    declare_demoralize,
    declare_parley,
    declare_rally,
    declare_taunt,
    get_social_maneuver_config,
)
from world.combat.social_combat_content import (
    INSPIRED_SEED_TEMPLATE_NAME,
    ensure_social_combat_content,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    EngagementType,
    ManeuverEffectKey,
)
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.mechanics.services import begin_engagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory

SUCCESS_INTENSITY = 3


class _SocialField(TestCase):
    """A rallier, an ally in combat and an opponent in an escalating encounter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.encounter = CombatEncounterFactory(
            escalation_curve=cls.curve, round_number=1, status=RoundStatus.DECLARING
        )
        cls.actor = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.ally = CombatParticipantFactory(
            encounter=cls.encounter, status=ParticipantStatus.ACTIVE
        )
        cls.opponent = CombatOpponentFactory(
            encounter=cls.encounter, threat_pool=ThreatPoolFactory()
        )
        cls.success = CheckOutcomeFactory(name="Designation Success", success_level=1)
        begin_engagement(
            cls.ally.character_sheet.character, EngagementType.COMBAT, source=cls.encounter
        )

    def _ally_intensity(self) -> int:
        return CharacterEngagement.objects.get(
            character=self.ally.character_sheet
        ).intensity_modifier


class RallyByDesignationTests(_SocialField):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Neither row is called "Rally" nor "Inspired"; no row called "Rally" exists.
        cls.encourage = CheckTypeFactory(name="Encourage")
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=cls.encourage
        )
        SurgeDegreeBandFactory(tuning=cls.tuning, outcome=cls.success, intensity=SUCCESS_INTENSITY)
        cls.heartened = ConditionTemplateFactory(name="Heartened")

    def _rally(self):
        action = declare_rally(self.actor, self.ally)
        with force_check_outcome(self.success) as capture:
            _resolve_rally(self.actor, action)
        return capture

    def _ally_has(self, template) -> bool:
        return ConditionInstance.objects.filter(
            target=self.ally.character_sheet.character, condition=template
        ).exists()

    def test_rally_rolls_the_rallied_tuning_s_check_whatever_its_name(self) -> None:
        self.assertFalse(CheckType.objects.filter(name="Rally").exists())

        capture = self._rally()

        self.assertEqual(capture.check_type, self.encourage)

    def test_without_a_rallied_tuning_nothing_is_rolled(self) -> None:
        self.tuning.delete()

        capture = self._rally()

        self.assertIsNone(capture.check_type)

    def test_a_success_applies_the_designated_condition_whatever_its_name(self) -> None:
        SocialManeuverConfigFactory(rally_success_condition=self.heartened)
        decoy = ConditionTemplateFactory(name=INSPIRED_SEED_TEMPLATE_NAME)

        self._rally()

        self.assertTrue(self._ally_has(self.heartened))
        self.assertFalse(self._ally_has(decoy))

    def test_an_unset_success_condition_applies_nothing_but_still_surges(self) -> None:
        SocialManeuverConfigFactory(rally_success_condition=None)
        ConditionTemplateFactory(name=INSPIRED_SEED_TEMPLATE_NAME)

        self._rally()

        self.assertFalse(
            ConditionInstance.objects.filter(target=self.ally.character_sheet.character).exists()
        )
        self.assertEqual(self._ally_intensity(), SUCCESS_INTENSITY)


class VowScaledRallySurgeTests(_SocialField):
    """A rallier's vow on "Rally: surge intensity" scales the surge's intensity only (#4783)."""

    THREAD_LEVEL = 2
    BONUS_PER_LEVEL = 50  # 100 + 2 x 50 = 200%

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        ensure_maneuver_effects()
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=CheckTypeFactory(name="Encourage")
        )
        cls.band = SurgeDegreeBandFactory(
            tuning=cls.tuning, outcome=cls.success, intensity=SUCCESS_INTENSITY, control_change=1
        )

    def _vow(self, key: str) -> None:
        """The rallier's engaged vow adds ``BONUS_PER_LEVEL`` per thread level to ``key``."""
        target = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name=f"{key} vow",
            scope_maneuver_effect=get_maneuver_effect(key),
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.actor.character_sheet,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=self.THREAD_LEVEL,
        )
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=target, bonus_per_level=self.BONUS_PER_LEVEL
        )

    def _rally(self) -> None:
        action = declare_rally(self.actor, self.ally)
        with force_check_outcome(self.success):
            _resolve_rally(self.actor, action)

    def _ally_control(self) -> int:
        return CharacterEngagement.objects.get(character=self.ally.character_sheet).control_modifier

    def test_a_vowed_rallier_surges_the_ally_more(self) -> None:
        self._vow(ManeuverEffectKey.RALLY_SURGE_INTENSITY)

        self._rally()

        # 200% surge intensity, so the Success band's 3 becomes 6.
        self.assertEqual(self._ally_intensity(), SUCCESS_INTENSITY * 2)
        # The control change is not scaled.
        self.assertEqual(self._ally_control(), 1)
        # The record keeps what the scaling added, for the roll line.
        self.assertEqual(DramaticSurgeRecord.objects.get().vow_scaling, SUCCESS_INTENSITY)

    def test_a_rallier_without_the_vow_row_surges_the_band_amount(self) -> None:
        self._rally()

        self.assertEqual(self._ally_intensity(), SUCCESS_INTENSITY)
        self.assertEqual(DramaticSurgeRecord.objects.get().vow_scaling, 0)

    def test_a_rally_morale_row_does_not_scale_surges(self) -> None:
        self._vow(ManeuverEffectKey.RALLY_MORALE)

        self._rally()

        self.assertEqual(self._ally_intensity(), SUCCESS_INTENSITY)


class OpponentVerbsByDesignationTests(_SocialField):
    """Taunt, Demoralize and Parley roll the check types designated for them."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.jibe = CheckTypeFactory(name="Jibe")
        cls.menace = CheckTypeFactory(name="Menace")
        cls.palaver = CheckTypeFactory(name="Palaver")
        # Rows with the old names exist and must not be rolled.
        for name in ("Taunt", "Demoralize", "Parley"):
            CheckTypeFactory(name=name)

    def _designate(self) -> None:
        SocialManeuverConfigFactory(
            taunt_check_type=self.jibe,
            demoralize_check_type=self.menace,
            parley_check_type=self.palaver,
        )

    def _taunt(self):
        action = declare_taunt(self.actor, self.opponent)
        with force_check_outcome(self.success) as capture:
            _resolve_taunt(self.actor, action)
        return capture

    def _demoralize(self):
        action = declare_demoralize(self.actor, self.opponent)
        with force_check_outcome(self.success) as capture:
            _resolve_demoralize(self.actor, action)
        return capture

    def _parley(self):
        self.opponent.morale = FALTER_MORALE_THRESHOLD
        self.opponent.save()
        action = declare_parley(self.actor, self.opponent)
        with force_check_outcome(self.success) as capture:
            _resolve_parley(self.actor, action)
        return capture

    def test_each_verb_rolls_its_designated_check(self) -> None:
        self._designate()

        self.assertEqual(self._taunt().check_type, self.jibe)
        self.assertEqual(self._demoralize().check_type, self.menace)
        self.assertEqual(self._parley().check_type, self.palaver)

    def test_an_unset_designation_rolls_nothing(self) -> None:
        SocialManeuverConfigFactory(
            taunt_check_type=None, demoralize_check_type=None, parley_check_type=None
        )

        self.assertIsNone(self._taunt().check_type)
        self.assertIsNone(self._demoralize().check_type)
        self.assertIsNone(self._parley().check_type)

    def test_an_inactive_designated_check_rolls_nothing(self) -> None:
        self._designate()
        self.menace.is_active = False
        self.menace.save()

        self.assertIsNone(self._demoralize().check_type)


@override_settings(SEED_SAMPLE_CONTENT=True)  # the social content seed gates on #2698
class SeedDesignatesUnsetFieldsTests(TestCase):
    def test_the_seed_points_unset_designations_at_its_rows(self) -> None:
        SocialManeuverConfigFactory(
            taunt_check_type=None,
            demoralize_check_type=None,
            parley_check_type=None,
            rally_success_condition=None,
        )

        ensure_social_combat_content()

        config = get_social_maneuver_config()
        self.assertEqual(config.taunt_check_type, CheckType.objects.get(name="Taunt"))
        self.assertEqual(config.demoralize_check_type, CheckType.objects.get(name="Demoralize"))
        self.assertEqual(config.parley_check_type, CheckType.objects.get(name="Parley"))
        self.assertEqual(
            config.rally_success_condition,
            ConditionTemplate.objects.get(name=INSPIRED_SEED_TEMPLATE_NAME),
        )

    def test_the_seed_keeps_a_designation_staff_set(self) -> None:
        staff_check = CheckTypeFactory(name="Goad")
        staff_condition = ConditionTemplateFactory(name="Heartened")
        SocialManeuverConfigFactory(
            taunt_check_type=staff_check, rally_success_condition=staff_condition
        )

        ensure_social_combat_content()

        config = get_social_maneuver_config()
        self.assertEqual(config.taunt_check_type, staff_check)
        self.assertEqual(config.rally_success_condition, staff_condition)
        self.assertEqual(config.demoralize_check_type, CheckType.objects.get(name="Demoralize"))
