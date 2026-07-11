"""Tests for the nemesis-regard combat hook — PC defeats a notable NPC (#2039).

Mirrors the mocking pattern in test_combat_technique_resolver.py's
NonAttackPCActionRoutingTests: resolve_combat_technique is patched at the
services module level so the damage_results shape (and therefore whether the
target opponent is defeated) is fully deterministic, without needing to drive
the real magic/check pipeline to a forced outcome.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import _resolve_pc_action
from world.combat.types import CombatTechniqueResolution, OpponentDamageResult
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.models import NpcRegard
from world.scenes.factories import PersonaFactory


def _build_technique():
    """A minimal combat-ready technique — action_template is required by
    _resolve_pc_action (resolve_cast_check_type falls back to
    template.check_type for an unprovisioned caster, ADR-0096)."""
    return TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(base_power=20),
        action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
    )


def _declare_action(participant, technique, target):
    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=participant.encounter.round_number,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=target,
        effort_level=EffortLevel.MEDIUM,
    )


def _resolution_with_result(*, opponent_id, defeated):
    return CombatTechniqueResolution(
        check_result=MagicMock(success_level=2),
        damage_results=[
            OpponentDamageResult(
                damage_dealt=20,
                health_damaged=True,
                probed=False,
                probing_increment=0,
                defeated=defeated,
                opponent_id=opponent_id,
            )
        ],
        applied_conditions=[],
        pull_flat_bonus=0,
        scaled_damage=20,
    )


class NemesisRegardCombatHookTests(TestCase):
    def test_defeating_persona_backed_opponent_records_regard_event(self):
        npc_persona = PersonaFactory()
        encounter = CombatEncounterFactory(round_number=1)
        opponent = CombatOpponentFactory(encounter=encounter, persona=npc_persona)

        pc_sheet = CharacterSheetFactory()
        pc_persona = pc_sheet.primary_persona
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        technique = _build_technique()
        action = _declare_action(participant, technique, opponent)

        resolution = _resolution_with_result(opponent_id=opponent.pk, defeated=True)
        with patch("world.combat.services.resolve_combat_technique", return_value=resolution):
            _resolve_pc_action(participant=participant, action=action, offense_check_fn=None)

        regard = NpcRegard.objects.get(holder_persona=npc_persona, target_persona=pc_persona)
        self.assertLess(regard.value, 0)
        event = regard.events.get()
        self.assertEqual(event.reason, NpcRegardEventReason.PC_FOILED_NPC_PLAN)
        self.assertEqual(event.source_pc_combat_action_id, action.pk)

    def test_defeating_persona_less_opponent_is_a_no_op(self):
        encounter = CombatEncounterFactory(round_number=1)
        opponent = CombatOpponentFactory(encounter=encounter, persona=None)

        pc_sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        technique = _build_technique()
        action = _declare_action(participant, technique, opponent)

        resolution = _resolution_with_result(opponent_id=opponent.pk, defeated=True)
        with patch("world.combat.services.resolve_combat_technique", return_value=resolution):
            _resolve_pc_action(participant=participant, action=action, offense_check_fn=None)

        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_hit_without_defeat_on_persona_backed_opponent_is_a_no_op(self):
        """Confirms the hook fires only on defeat, not on every hit."""
        npc_persona = PersonaFactory()
        encounter = CombatEncounterFactory(round_number=1)
        opponent = CombatOpponentFactory(encounter=encounter, persona=npc_persona)

        pc_sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        technique = _build_technique()
        action = _declare_action(participant, technique, opponent)

        resolution = _resolution_with_result(opponent_id=opponent.pk, defeated=False)
        with patch("world.combat.services.resolve_combat_technique", return_value=resolution):
            _resolve_pc_action(participant=participant, action=action, offense_check_fn=None)

        self.assertEqual(NpcRegard.objects.count(), 0)
