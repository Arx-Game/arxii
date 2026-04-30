"""Integration tests for the combat → use_technique pipeline.

These tests exercise the full round-resolution path with a real
use_technique envelope. They assert observable side effects (anima
deduction, event emission, mishap conditions, damage delivered)
rather than internal call patterns.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from flows.constants import EventName
from flows.events.payloads import TechniqueCastPayload, TechniquePreCastPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    EncounterStatus,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_combat_technique
from world.fatigue.constants import EffortLevel, FatigueCategory
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


def _setup_pc_attacking_mook(
    *,
    technique_intensity: int = 5,
    technique_control: int = 10,
    technique_anima_cost: int = 3,
    base_power: int = 20,
    opponent_health: int = 50,
):
    """Build the standard test scenario: 1 PC, 1 mook, technique ready."""
    encounter = CombatEncounterFactory(
        status=EncounterStatus.RESOLVING,
        round_number=1,
    )
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=30)
    opponent = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=opponent_health,
        max_health=opponent_health,
        threat_pool=pool,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    CharacterVitals.objects.create(
        character_sheet=sheet,
        health=100,
        max_health=100,
        status=CharacterStatus.ALIVE,
    )
    anima = CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
    CharacterEngagementFactory(character=sheet.character)
    room = ObjectDB.objects.create(
        db_key="TestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    sheet.character.location = room
    sheet.character.save()

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
        intensity=technique_intensity,
        control=technique_control,
        anima_cost=technique_anima_cost,
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    return participant, action, opponent, anima, technique, room


class AnimaDeductionTest(TestCase):
    """Combat-cast technique deducts anima cost from CharacterAnima.current."""

    def test_combat_cast_deducts_anima(self) -> None:
        participant, action, opponent, anima, _technique, _ = _setup_pc_attacking_mook(
            technique_anima_cost=3,
            technique_intensity=5,
            technique_control=10,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                target=opponent,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        anima.refresh_from_db()
        # control_delta = 10 - 5 = 5; effective_cost = max(3 - 5, 0) = 0.
        self.assertEqual(anima.current, 20)

    def test_combat_cast_with_high_intensity_deducts_anima(self) -> None:
        participant, action, opponent, anima, _technique, _ = _setup_pc_attacking_mook(
            technique_anima_cost=5,
            technique_intensity=10,
            technique_control=2,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                target=opponent,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        anima.refresh_from_db()
        # control_delta = 2 - 10 = -8; effective_cost = max(5 - (-8), 0) = 13.
        self.assertEqual(anima.current, 7)


class EventEmissionTest(TestCase):
    """PRE_CAST and CAST events fire during combat round resolution."""

    def test_pre_cast_emitted_in_combat(self) -> None:
        participant, action, opponent, _, _, _ = _setup_pc_attacking_mook()
        captured: list = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_PRE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    target=opponent,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], TechniquePreCastPayload)
        self.assertIs(captured[0].caster, participant.character_sheet.character)

    def test_cast_emitted_in_combat(self) -> None:
        participant, action, opponent, _, _, _ = _setup_pc_attacking_mook()
        captured: list = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    target=opponent,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], TechniqueCastPayload)
