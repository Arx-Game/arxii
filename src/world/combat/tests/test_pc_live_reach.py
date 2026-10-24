"""A PC's strike re-checks reach live at resolution (#4607, slice 2 of #4576).

NPCs move in their own slots, so a target a PC declared against may have left reach by
the PC's slot. A single target out of reach fizzles with a narration line and costs
nothing; an area cast keeps only the targets still in reach; unplaced combatants stay
lenient. Driven through ``resolve_round`` with a real technique and a real pipeline.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import ActionTargetType
from actions.factories import ActionTemplateFactory
from world.areas.positioning.services import connect_positions, create_position, place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction, CombatRoundActionTarget
from world.combat.services import declare_action, resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.constants import EffortLevel
from world.fatigue.models import FatiguePool
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterAnima
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.models import Interaction
from world.vitals.models import CharacterVitals

FIZZLE_SUFFIX = "'s strike finds no one in reach."


def _hit(*args, **kwargs):
    return MagicMock(success_level=2)


class PcLiveReachTests(TestCase):
    """Uses setUp: factories create Evennia objects, which setUpTestData cannot deepcopy."""

    def setUp(self) -> None:
        DamageSuccessLevelMultiplierFactory(min_success_level=0, multiplier=1)
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.room = self.encounter.room
        self.pos_a = create_position(self.room, "live_reach_a")
        self.pos_b = create_position(self.room, "live_reach_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=self.sheet)
        self.caster = self.sheet.character
        self.caster.move_to(self.room, quiet=True)

    def _technique(self, *, reach: str = TechniqueReach.SAME, target_type=None):
        kwargs = {"target_type": target_type} if target_type else {}
        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name=f"LiveReach{reach}", base_power=20),
            action_category=ActionCategory.PHYSICAL,
            reach=reach,
            anima_cost=3,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            damage_profile=False,
            **kwargs,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)
        return technique

    def _opponent(self):
        opponent = CombatOpponentFactory(encounter=self.encounter)
        return opponent, ObjectDB.objects.get(pk=opponent.objectdb_id)

    def _anima(self) -> int:
        return CharacterAnima.objects.get(character=self.sheet).current

    def _fatigue(self) -> int:
        pool = FatiguePool.objects.filter(character_sheet=self.sheet).first()
        return pool.physical_current if pool else 0

    def _lines(self) -> list[str]:
        return [
            i.content
            for i in Interaction.objects.filter(scene=self.encounter.scene)
            if FIZZLE_SUFFIX in i.content
        ]

    def _persona_name(self) -> str:
        from world.scenes.services import active_persona_for_sheet

        return active_persona_for_sheet(self.sheet).name

    def test_single_target_that_moved_out_of_reach_fizzles_free(self) -> None:
        technique = self._technique(reach=TechniqueReach.SAME)
        opponent, opponent_od = self._opponent()
        place_in_position(self.caster, self.pos_a)
        place_in_position(opponent_od, self.pos_a)
        declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        place_in_position(opponent_od, self.pos_b)  # stepped away before the PC's slot
        health_before = opponent.health
        anima_before, fatigue_before = self._anima(), self._fatigue()

        result = resolve_round(self.encounter, offense_check_fn=_hit)

        pc_outcome = next(
            o for o in result.action_outcomes if o.participant_id == self.participant.pk
        )
        self.assertEqual(pc_outcome.damage_results, [])
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, health_before)
        self.assertEqual(self._anima(), anima_before)
        self.assertEqual(self._fatigue(), fatigue_before)
        self.assertEqual(self._lines(), [f"{self._persona_name()}{FIZZLE_SUFFIX}"])

    def test_single_target_still_in_reach_resolves_and_charges(self) -> None:
        technique = self._technique(reach=TechniqueReach.SAME)
        opponent, opponent_od = self._opponent()
        place_in_position(self.caster, self.pos_a)
        place_in_position(opponent_od, self.pos_a)
        declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        anima_before = self._anima()

        resolve_round(self.encounter, offense_check_fn=_hit)

        self.assertLess(self._anima(), anima_before)
        self.assertEqual(self._lines(), [])

    def test_unplaced_pair_stays_lenient(self) -> None:
        technique = self._technique(reach=TechniqueReach.SAME)
        opponent, _ = self._opponent()
        declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        anima_before = self._anima()

        resolve_round(self.encounter, offense_check_fn=_hit)

        self.assertLess(self._anima(), anima_before)
        self.assertEqual(self._lines(), [])

    def _declare_area(self, technique, opponents) -> CombatRoundAction:
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponents[0],
        )
        for opp in opponents:
            CombatRoundActionTarget.objects.get_or_create(action=action, opponent=opp)
        return action

    def test_area_cast_keeps_only_targets_in_reach(self) -> None:
        technique = self._technique(reach=TechniqueReach.SAME, target_type=ActionTargetType.AREA)
        near, near_od = self._opponent()
        far, far_od = self._opponent()
        place_in_position(self.caster, self.pos_a)
        place_in_position(near_od, self.pos_a)
        place_in_position(far_od, self.pos_a)
        self._declare_area(technique, [near, far])
        place_in_position(far_od, self.pos_b)
        near_before, far_before = near.health, far.health
        anima_before = self._anima()

        resolve_round(self.encounter, offense_check_fn=_hit)

        near.refresh_from_db()
        far.refresh_from_db()
        self.assertLess(near.health, near_before)
        self.assertEqual(far.health, far_before)
        self.assertLess(self._anima(), anima_before)
        self.assertEqual(self._lines(), [])

    def test_area_cast_with_no_one_left_in_reach_fizzles_free(self) -> None:
        technique = self._technique(reach=TechniqueReach.SAME, target_type=ActionTargetType.AREA)
        first, first_od = self._opponent()
        second, second_od = self._opponent()
        place_in_position(self.caster, self.pos_a)
        place_in_position(first_od, self.pos_a)
        place_in_position(second_od, self.pos_a)
        self._declare_area(technique, [first, second])
        place_in_position(first_od, self.pos_b)
        place_in_position(second_od, self.pos_b)
        first_before, second_before = first.health, second.health
        anima_before, fatigue_before = self._anima(), self._fatigue()

        resolve_round(self.encounter, offense_check_fn=_hit)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.health, second.health), (first_before, second_before))
        self.assertEqual(self._anima(), anima_before)
        self.assertEqual(self._fatigue(), fatigue_before)
        self.assertEqual(self._lines(), [f"{self._persona_name()}{FIZZLE_SUFFIX}"])
