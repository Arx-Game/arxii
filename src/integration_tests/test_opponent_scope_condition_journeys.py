"""Journeys for a condition modifier narrowed by who the condition lands on (#4823).

Hobb is a fighter (or a caster in a scene) whose technique applies one authored condition row:
base severity 3, base duration 4 rounds, no scaling. A "+N condition severity against X"
modifier is a ModifierTarget in the maneuver effect category with the condition severity kind
and an opponent scope, granted to Hobb through a distinction.

Expected values come from the spec, not from running the code:

* An area technique that leaves Singed on a bandit and an archer, with "+2 severity against
  Bleeding" while only the archer bleeds, lands severity 3 + 2 = 5 on the archer and 3 on the
  bandit.
* A modifier with no opponent scope ("+2 severity", this technique) lands 3 + 2 = 5 on both.
* In a scene cast on Wren (Bleeding) and on Vex (not), "+2 severity against Bleeding" and
  "+1 duration against Bleeding" land severity 5 and duration 5 on Wren, 3 and 4 on Vex.
* A passive technique that lands on every opponent reads each one: severity 5 on the bleeding
  archer, 3 on the bandit.
"""

from __future__ import annotations

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_technique_effect_condition_journeys import (
    BASE_DURATION,
    BASE_SEVERITY,
    applied_row,
    grant_condition_modifier,
)
from integration_tests.test_technique_effect_damage_journeys import _DamageField
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from integration_tests.test_vow_added_effects_out_of_combat_journeys import casting_at
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.factories import CombatOpponentFactory
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.constants import EffectKind
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals


class OpponentScopedConditionsInCombat(_DamageField):
    """Hobb sweeps a bandit and an archer, and only the archer is Bleeding."""

    def setUp(self) -> None:
        super().setUp()
        self.bleeding = ConditionTemplateFactory(name="Bleeding")
        self.singed = ConditionTemplateFactory(name="Singed")
        self.archer = CombatOpponentFactory(
            encounter=self.encounter, name="Archer", health=200, max_health=200
        )
        ConditionInstanceFactory(
            target=self.archer.objectdb, condition=self.bleeding, rounds_remaining=50
        )
        self.sweep = self.technique(self.ember, target_type=ActionTargetType.AREA)
        applied_row(self.sweep, self.singed, ConditionTargetKind.ENEMY)

    def severity_on(self, opponent) -> int:
        return ConditionInstance.objects.get(
            target=opponent.objectdb, condition=self.singed, resolved_at__isnull=True
        ).severity

    def sweep_round(self, technique: Technique, slot: str = "focused") -> None:
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot=slot)
        kwargs: dict[str, object] = {"effort_level": EffortLevel.MEDIUM}
        if slot == "focused":
            kwargs["focused_opponent_target_id"] = self.bandit.pk
        declared = dispatch_player_action(self.hobb, ref, kwargs)
        self.assertTrue(declared.deferred, declared)
        with every_check_succeeds():
            resolve_round(self.encounter)
        begin_declaration_phase(self.encounter)

    def test_vs_bleeding_severity_lands_only_on_the_bleeding_target(self) -> None:
        grant_condition_modifier(
            self.sheet,
            "Singe deeper vs bleeding",
            2,
            EffectKind.CONDITION_SEVERITY,
            scope_technique=self.sweep,
            scope_opponent_condition=self.bleeding,
        )

        self.sweep_round(self.sweep)

        self.assertEqual(self.severity_on(self.archer), BASE_SEVERITY + 2)
        self.assertEqual(self.severity_on(self.bandit), BASE_SEVERITY)

    def test_untargeted_bonus_still_reaches_everyone(self) -> None:
        grant_condition_modifier(
            self.sheet,
            "Singe deeper",
            2,
            EffectKind.CONDITION_SEVERITY,
            scope_technique=self.sweep,
        )

        self.sweep_round(self.sweep)

        self.assertEqual(self.severity_on(self.archer), BASE_SEVERITY + 2)
        self.assertEqual(self.severity_on(self.bandit), BASE_SEVERITY + 2)

    def test_a_passive_reads_each_opponent(self) -> None:
        passive = self.technique(self.ember)
        applied_row(passive, self.singed, ConditionTargetKind.ENEMY)
        grant_condition_modifier(
            self.sheet,
            "Singe deeper vs bleeding",
            2,
            EffectKind.CONDITION_SEVERITY,
            scope_technique=passive,
            scope_opponent_condition=self.bleeding,
        )

        self.sweep_round(passive, slot="passive-physical")

        self.assertEqual(self.severity_on(self.archer), BASE_SEVERITY + 2)
        self.assertEqual(self.severity_on(self.bandit), BASE_SEVERITY)


class OpponentScopedConditionsInAScene(JourneyCase):
    """Hobb wards Wren, who is Bleeding, and Vex, who is not."""

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
        self.wren = self.make_player("Wren", room=self.room)
        self.vex = self.make_player("Vex", room=self.room)
        self.bleeding = ConditionTemplateFactory(name="Bleeding")
        ConditionInstanceFactory(target=self.wren, condition=self.bleeding, rounds_remaining=50)
        self.condition = ConditionTemplateFactory(name="Warded")
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        applied_row(self.technique, self.condition, ConditionTargetKind.ALLY)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def ward(self, target) -> ConditionInstance:
        with casting_at("Success"):
            result = self.web(
                self.hobb,
                "cast_technique",
                technique_id=self.technique.pk,
                target_persona_id=target.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)
        return ConditionInstance.objects.get(
            target=target, condition=self.condition, resolved_at__isnull=True
        )

    def test_scene_cast_vs_bleeding(self) -> None:
        for name, kind, value in (
            ("Ward deeper vs bleeding", EffectKind.CONDITION_SEVERITY, 2),
            ("Ward longer vs bleeding", EffectKind.CONDITION_DURATION, 1),
        ):
            grant_condition_modifier(
                self.sheet,
                name,
                value,
                kind,
                scope_technique=self.technique,
                scope_opponent_condition=self.bleeding,
            )

        on_wren = self.ward(self.wren)
        on_vex = self.ward(self.vex)

        self.assertEqual(
            (on_wren.severity, on_wren.rounds_remaining),
            (BASE_SEVERITY + 2, BASE_DURATION + 1),
        )
        self.assertEqual((on_vex.severity, on_vex.rounds_remaining), (BASE_SEVERITY, BASE_DURATION))
