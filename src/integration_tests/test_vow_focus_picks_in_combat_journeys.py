"""Journeys for vow focus picks in a fight (#4806, slice 2 of #4759).

Ysmay and Hobb hold the same Durance vow. The vow carries two added effects on
Hold casts: a base row that dazes the held enemy, and a row on the focus pick
"Binding Grip" that also slows it. Ysmay chose the pick; Hobb did not. Each
declares a Hold through dispatch at their own bandit, the round resolves, and
the journey reads which conditions landed on which bandit.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import resolve_round
from world.conditions.factories import (
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.covenants.constants import CovenantType, VowEffectContext
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    engage_vow_with_thread,
)
from world.covenants.models import CharacterCovenantRole, VowAddedEffect, VowFocusPick
from world.covenants.perks.constants import PerkBeneficiary
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals


class AFocusPickRidesOnlyItsChoosersHold(JourneyCase):
    """Two holders of one vow; only Ysmay chose the pick."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        self.yard = self.make_room("The Yard")
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.hold = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        TechniqueFunctionTagFactory(technique=self.hold, function=TechniqueFunction.HOLD)

        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.vow = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.ysmay, ysmays_vow = self.holder("Ysmay")
        self.hobb, _ = self.holder("Hobb")
        self.ysmays_bandit = CombatOpponentFactory(encounter=self.encounter)
        self.hobbs_bandit = CombatOpponentFactory(encounter=self.encounter)

        self.dazed = ConditionTemplateFactory(name="Dazed")
        self.slowed = ConditionTemplateFactory(name="Slowed")
        self.grip = VowFocusPickFactory(covenant_role=self.vow, name="Binding Grip")
        self.hold_row(focus_pick=None, condition=self.dazed)
        self.hold_row(focus_pick=self.grip, condition=self.slowed)
        CharacterVowFocusPickFactory(character_role=ysmays_vow, pick=self.grip)

    def holder(self, name: str) -> tuple[ObjectDB, CharacterCovenantRole]:
        """A player in the fight who knows Hold and holds the vow at thread level 1."""
        character = self.make_player(name, room=self.yard)
        sheet = character.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.hold)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        membership = engage_vow_with_thread(sheet, self.vow, covenant=self.covenant, thread_level=1)
        return character, membership

    def hold_row(
        self, *, focus_pick: VowFocusPick | None, condition: ConditionTemplate
    ) -> VowAddedEffect:
        """A row on the vow: the holder's own Hold, in a fight, lays ``condition``."""
        effect = VowAddedEffectFactory(
            covenant_role=self.vow,
            function=TechniqueFunction.HOLD,
            beneficiary=PerkBeneficiary.SELF,
            cast_context=VowEffectContext.IN_COMBAT,
            focus_pick=focus_pick,
        )
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=condition,
            target_kind=ConditionTargetKind.ENEMY,
            base_severity=1,
        )
        return effect

    def declare_hold(self, character: ObjectDB, target: CombatOpponent) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.hold.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            character,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": target.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def conditions_on(self, opponent: CombatOpponent) -> set[str]:
        return set(
            ConditionInstance.objects.filter(target=opponent.objectdb).values_list(
                "condition__name", flat=True
            )
        )

    def test_only_the_holder_who_chose_the_pick_slows_her_bandit(self) -> None:
        self.declare_hold(self.ysmay, self.ysmays_bandit)
        self.declare_hold(self.hobb, self.hobbs_bandit)
        with every_check_succeeds():
            resolve_round(self.encounter)

        # The base row lands for both holders; the pick row only for Ysmay.
        self.assertEqual(self.conditions_on(self.ysmays_bandit), {"Dazed", "Slowed"})
        self.assertEqual(self.conditions_on(self.hobbs_bandit), {"Dazed"})
