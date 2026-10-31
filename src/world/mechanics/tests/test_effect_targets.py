"""The maneuver effect reader: base value plus every target scoped to the effect (#4783)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantRoleFactory, make_engaged_member
from world.covenants.models import VowStatScaling
from world.distinctions.factories import DistinctionEffectFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    EffectKind,
    ManeuverEffectKey,
)
from world.mechanics.effect_targets import effect_value
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierTargetFactory,
)
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory, ModifierTarget


class EffectValueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_maneuver_effects()
        cls.category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.character = CharacterFactory(db_key="EffectReaderChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)
        cls.charge_damage = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)

    def _effect_target(self, name, *, effect=None, kind=""):
        return ModifierTargetFactory(
            category=self.category,
            name=name,
            scope_maneuver_effect=effect,
            scope_effect_kind=kind,
        )

    def _distinction_modifier(self, target, value):
        effect = DistinctionEffectFactory(target=target)
        return CharacterModifierFactory(
            character=self.sheet,
            target=target,
            value=value,
            source=DistinctionModifierSourceFactory(distinction_effect=effect),
        )

    def test_no_targets_returns_base(self):
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 5

    def test_one_effect_target_adds_its_total(self):
        target = self._effect_target("Charge damage up", effect=self.charge_damage)
        self._distinction_modifier(target, 3)
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 8
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_TO_HIT) == 10

    def test_kind_target_reaches_every_effect_of_that_kind(self):
        target = self._effect_target("All partial stops", kind=EffectKind.PARTIAL_PROTECTION)
        self._distinction_modifier(target, 10)
        assert effect_value(self.sheet, ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION) == 60
        assert effect_value(self.sheet, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION) == 60
        assert effect_value(self.sheet, ManeuverEffectKey.COVER_ESCAPE_BONUS) == 10

    def test_target_with_neither_scope_matches_nothing(self):
        target = ModifierTarget(category=self.category, name="Unscoped")
        ModifierTarget.objects.bulk_create([target])
        target = ModifierTarget.objects.get(category=self.category, name="Unscoped")
        self._distinction_modifier(target, 9)
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 5
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_TO_HIT) == 10
        assert effect_value(self.sheet, ManeuverEffectKey.COVER_ESCAPE_BONUS) == 10

    def test_target_outside_the_category_matches_nothing(self):
        other = ModifierCategory.objects.create(name="not_a_maneuver_category")
        target = ModifierTarget.objects.create(
            category=other, name="Stray", scope_effect_kind=EffectKind.DAMAGE
        )
        self._distinction_modifier(target, 9)
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 5

    def test_vow_stat_scaling_reaches_an_effect(self):
        target = self._effect_target("Charge damage vow", effect=self.charge_damage)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        make_engaged_member(character_sheet=self.sheet, covenant_role=role)
        VowStatScaling.objects.create(covenant_role=role, modifier_target=target, bonus_per_level=1)
        Thread.objects.create(
            owner=self.sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=ResonanceFactory(),
            level=3,
        )
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 8

    def test_condition_modifier_reaches_an_effect(self):
        target = self._effect_target(
            "Cover escape condition",
            effect=get_maneuver_effect(ManeuverEffectKey.COVER_ESCAPE_BONUS),
        )
        template = ConditionTemplateFactory(name="Sheltered")
        ConditionModifierEffectFactory(condition=template, modifier_target=target, value=2)
        ConditionInstanceFactory(target=self.character, condition=template)
        assert effect_value(self.sheet, ManeuverEffectKey.COVER_ESCAPE_BONUS) == 12

    def test_negative_total_clamps_at_zero(self):
        target = self._effect_target("Charge damage down", effect=self.charge_damage)
        self._distinction_modifier(target, -80)
        assert effect_value(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE) == 0

    def test_partial_protection_caps_at_100(self):
        target = self._effect_target("Succor stops more", kind=EffectKind.PARTIAL_PROTECTION)
        self._distinction_modifier(target, 70)
        assert effect_value(self.sheet, ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION) == 100

    def test_partial_protection_floors_at_zero(self):
        target = self._effect_target("Succor stops less", kind=EffectKind.PARTIAL_PROTECTION)
        self._distinction_modifier(target, -80)
        assert effect_value(self.sheet, ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION) == 0

    def test_none_sheet_returns_base(self):
        target = self._effect_target("Ignored for no sheet", effect=self.charge_damage)
        self._distinction_modifier(target, 3)
        assert effect_value(None, ManeuverEffectKey.CHARGE_DAMAGE) == 5
