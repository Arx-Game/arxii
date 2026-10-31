"""Journeys for a modifier on the conditions a technique applies (#4822).

Hobb is a fighter (or a caster in a scene) whose technique applies one authored condition
row: base severity 3, base duration 4 rounds, no scaling. A "+N condition severity" or
"+N condition duration" modifier is a ModifierTarget in the maneuver effect category with the
condition severity or duration effect kind, granted to Hobb through a distinction.

Expected values come from the spec, not from running the code:

* "+2 condition severity" scoped to the technique lifts the applied condition from 3 to 5 in a
  real combat round, and a passive technique's condition from 3 to 5.
* In a scene cast, "+2 condition severity" and "+1 condition duration" land severity 5 and
  duration 5 (4 + 1).
* A "-50" modifier never takes either number below 1: severity 1, duration 1. (A combat round
  ticks the new condition, and a one-round duration would already be gone, so the duration
  floor is read in the scene cast, where nothing ticks.)
* A condition that lasts until cured has no round count; a duration bonus gives it none.
* A modifier scoped to another technique changes nothing: severity 3, duration 4.
* A team-lane row ignoring both bonuses is pinned by
  ``world.magic.tests.test_condition_application.VowSeamKwargTests``.
"""

from __future__ import annotations

from decimal import Decimal

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from integration_tests.test_vow_added_effects_out_of_combat_journeys import casting_at
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory, DamageSuccessLevelMultiplierFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.distinctions.factories import DistinctionEffectFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierTargetFactory,
)
from world.mechanics.models import ModifierCategory, ModifierTarget
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals

BASE_SEVERITY = 3
BASE_DURATION = 4


def grant_condition_modifier(
    sheet, name: str, value: int, kind: str, **scopes: object
) -> ModifierTarget:
    """``sheet`` holds a ``value`` modifier on a ``kind`` target scoped by ``scopes``."""
    category = ModifierCategory.objects.get_or_create(name=MANEUVER_EFFECT_CATEGORY_NAME)[0]
    target = ModifierTargetFactory(category=category, name=name, scope_effect_kind=kind, **scopes)
    CharacterModifierFactory(
        character=sheet,
        target=target,
        value=value,
        source=DistinctionModifierSourceFactory(
            distinction_effect=DistinctionEffectFactory(target=target)
        ),
    )
    return target


def applied_row(technique: Technique, condition: ConditionTemplate, target_kind: str) -> None:
    TechniqueAppliedConditionFactory(
        technique=technique,
        condition=condition,
        target_kind=target_kind,
        minimum_success_level=1,
        base_severity=BASE_SEVERITY,
        base_duration_rounds=BASE_DURATION,
    )


class TechniqueConditionModifiersInCombat(JourneyCase):
    """Hobb in the Yard, striking a bandit with techniques that leave a condition on it."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )
        self.yard = self.make_room("The Yard")
        self.hobb = self.make_player("Hobb", room=self.yard)
        self.sheet = self.hobb.sheet_data
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)
        self.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.check_type, trait=StatTraitFactory(), weight=1)
        self.gift = GiftFactory(name="Ember")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit", health=200, max_health=200
        )
        self.condition = ConditionTemplateFactory(name="Singed")

    def technique(self, condition: ConditionTemplate, target_kind: str) -> Technique:
        technique = TechniqueFactory(
            gift=self.gift,
            target_type=ActionTargetType.SINGLE,
            anima_cost=1,
            intensity=4,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        applied_row(technique, condition, target_kind)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def resolve(self, technique: Technique, *, slot: str) -> None:
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot=slot)
        kwargs: dict[str, object] = {"effort_level": EffortLevel.MEDIUM}
        if slot == "focused":
            kwargs["focused_opponent_target_id"] = self.bandit.pk
        declared = dispatch_player_action(self.hobb, ref, kwargs)
        self.assertTrue(declared.deferred, declared)
        with every_check_succeeds():
            resolve_round(self.encounter)
        begin_declaration_phase(self.encounter)

    def on(self, character, condition: ConditionTemplate | None = None) -> ConditionInstance:
        return ConditionInstance.objects.get(
            target=character, condition=condition or self.condition, resolved_at__isnull=True
        )

    def strike(
        self, technique: Technique, condition: ConditionTemplate | None = None
    ) -> ConditionInstance:
        self.resolve(technique, slot="focused")
        return self.on(self.bandit.objectdb, condition)

    def test_severity_bonus_in_combat(self) -> None:
        technique = self.technique(self.condition, ConditionTargetKind.ENEMY)
        grant_condition_modifier(
            self.sheet, "Singe deeper", 2, EffectKind.CONDITION_SEVERITY, scope_technique=technique
        )

        instance = self.strike(technique)

        self.assertEqual(instance.severity, BASE_SEVERITY + 2)

    def test_a_modifier_scoped_to_another_technique_changes_nothing(self) -> None:
        technique = self.technique(self.condition, ConditionTargetKind.ENEMY)
        other = self.technique(ConditionTemplateFactory(name="Other"), ConditionTargetKind.ENEMY)
        grant_condition_modifier(
            self.sheet, "Other only", 2, EffectKind.CONDITION_SEVERITY, scope_technique=other
        )

        instance = self.strike(technique)

        self.assertEqual(instance.severity, BASE_SEVERITY)

    def test_negative_bonus_floors_at_one(self) -> None:
        technique = self.technique(self.condition, ConditionTargetKind.ENEMY)
        grant_condition_modifier(
            self.sheet, "Dulled", -50, EffectKind.CONDITION_SEVERITY, scope_technique=technique
        )

        instance = self.strike(technique)

        self.assertEqual(instance.severity, 1)

    def test_no_duration_stays_none(self) -> None:
        lasting = ConditionTemplateFactory(
            name="Branded", default_duration_type=DurationType.UNTIL_CURED
        )
        technique = self.technique(lasting, ConditionTargetKind.ENEMY)
        grant_condition_modifier(
            self.sheet, "Longer", 1, EffectKind.CONDITION_DURATION, scope_technique=technique
        )

        instance = self.strike(technique, lasting)

        self.assertIsNone(instance.rounds_remaining)

    def test_passive_technique_takes_the_bonus(self) -> None:
        passive = self.technique(self.condition, ConditionTargetKind.SELF)
        grant_condition_modifier(
            self.sheet, "Singe deeper", 2, EffectKind.CONDITION_SEVERITY, scope_technique=passive
        )

        self.resolve(passive, slot="passive-physical")

        self.assertEqual(self.on(self.hobb).severity, BASE_SEVERITY + 2)


class TechniqueConditionModifiersInAScene(JourneyCase):
    """Hobb casts a technique in the Infirmary that leaves a condition on himself."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.room = self.make_room("The Infirmary")
        SceneFactory(room=self.room)
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.sheet = self.hobb.sheet_data
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        self.condition = ConditionTemplateFactory(name="Warded")
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        applied_row(self.technique, self.condition, ConditionTargetKind.SELF)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def cast(self) -> ConditionInstance:
        with casting_at("Success"):
            result = self.web(self.hobb, "cast_technique", technique_id=self.technique.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        return ConditionInstance.objects.get(
            target=self.hobb, condition=self.condition, resolved_at__isnull=True
        )

    def test_severity_and_duration_in_scene_cast(self) -> None:
        grant_condition_modifier(
            self.sheet,
            "Ward deeper",
            2,
            EffectKind.CONDITION_SEVERITY,
            scope_technique=self.technique,
        )
        grant_condition_modifier(
            self.sheet,
            "Ward longer",
            1,
            EffectKind.CONDITION_DURATION,
            scope_technique=self.technique,
        )

        instance = self.cast()

        self.assertEqual(
            (instance.severity, instance.rounds_remaining),
            (BASE_SEVERITY + 2, BASE_DURATION + 1),
        )

    def test_negative_bonus_floors_at_one_in_a_scene(self) -> None:
        grant_condition_modifier(
            self.sheet, "Dulled", -50, EffectKind.CONDITION_SEVERITY, scope_technique=self.technique
        )
        grant_condition_modifier(
            self.sheet, "Brief", -50, EffectKind.CONDITION_DURATION, scope_technique=self.technique
        )

        instance = self.cast()

        self.assertEqual((instance.severity, instance.rounds_remaining), (1, 1))
