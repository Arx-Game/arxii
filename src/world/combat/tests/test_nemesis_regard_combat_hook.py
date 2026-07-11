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
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import _resolve_npc_action, _resolve_pc_action
from world.combat.types import CombatTechniqueResolution, OpponentDamageResult
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.models import NpcRegard
from world.scenes.factories import PersonaFactory
from world.vitals.models import CharacterVitals


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


def _declare_npc_action(opponent, participant, entry):
    """Mirrors test_defense_sourcing.py's DefenseCheckSourcingTests._make_action.

    A flat-damage threat entry (``defense_check_type=None``) drives
    ``_resolve_npc_action_on_target``'s ``else`` branch (``apply_damage_to_participant``),
    so the resulting ``ParticipantDamageResult`` is fully deterministic from
    ``base_damage`` and the target's vitals — no check pipeline to force.
    """
    action = CombatOpponentAction.objects.create(
        opponent=opponent,
        round_number=1,
        threat_entry=entry,
    )
    action.targets.add(participant)
    return action


class NotableNpcCriticalHitRegardHookTests(TestCase):
    def test_notable_npc_critically_harming_pc_records_regard_event(self):
        npc_persona = PersonaFactory()
        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(encounter=encounter, persona=npc_persona, threat_pool=pool)

        pc_sheet = CharacterSheetFactory()
        pc_persona = pc_sheet.primary_persona
        CharacterVitals.objects.create(character_sheet=pc_sheet, health=10, max_health=200)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        # base_damage=50 drives health_after to -40 <= DEATH_HEALTH_THRESHOLD (0),
        # so dmg_result.death_eligible is True.
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=50, defense_check_type=None)
        action = _declare_npc_action(opponent, participant, entry)

        _resolve_npc_action(opponent, action, defense_check_type=None, defense_check_fn=MagicMock())

        regard = NpcRegard.objects.get(holder_persona=npc_persona, target_persona=pc_persona)
        self.assertLess(regard.value, 0)
        event = regard.events.get()
        self.assertEqual(event.reason, NpcRegardEventReason.NPC_HARMED_PC_INTEREST)
        self.assertEqual(event.source_npc_combat_action_id, action.pk)

    def test_minor_hit_from_notable_npc_is_a_no_op(self):
        """Confirms the hook fires only on a death/wound-eligible hit, not every hit."""
        npc_persona = PersonaFactory()
        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(encounter=encounter, persona=npc_persona, threat_pool=pool)

        pc_sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=pc_sheet, health=200, max_health=200)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        # base_damage=10 leaves health_after=190 (well above the death threshold)
        # and effective_damage=10 (well under 50% of max_health) — neither flag fires.
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=10, defense_check_type=None)
        action = _declare_npc_action(opponent, participant, entry)

        _resolve_npc_action(opponent, action, defense_check_type=None, defense_check_fn=MagicMock())

        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_critical_hit_from_persona_less_opponent_is_a_no_op(self):
        """A mook/persona-less opponent's critical hit must be a genuine no-op."""
        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(encounter=encounter, persona=None, threat_pool=pool)

        pc_sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=pc_sheet, health=10, max_health=200)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=pc_sheet)

        entry = ThreatPoolEntryFactory(pool=pool, base_damage=50, defense_check_type=None)
        action = _declare_npc_action(opponent, participant, entry)

        _resolve_npc_action(opponent, action, defense_check_type=None, defense_check_fn=MagicMock())

        self.assertEqual(NpcRegard.objects.count(), 0)
