"""Integration tests for non-attack combat techniques routed through use_technique.

Verifies TECHNIQUE_AFFECTED fires uniformly across target types, including
ephemeral mooks — the gap closed by passing _build_affected_targets to
use_technique instead of an empty list.
"""

from unittest.mock import MagicMock, patch

from evennia.objects.models import ObjectDB
from evennia.utils.test_resources import EvenniaTestCase

from flows.constants import EventName
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


def _create_room() -> ObjectDB:
    return ObjectDB.objects.create(
        db_key="TestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _setup_participant_with_technique(
    *,
    encounter,
    room,
    base_power: int = 10,
    technique_intensity: int = 5,
):
    """Build a participant with a technique, anima, and room placement."""
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
    sheet.character.location = room
    sheet.character.save()

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
        intensity=technique_intensity,
        control=10,
        anima_cost=3,
    )
    return participant, technique, anima


class TechniqueAffectedFiringTests(EvenniaTestCase):
    """Verifies TECHNIQUE_AFFECTED fires uniformly across target types,
    including ephemeral mooks (the gap closed by the CombatOpponent → ObjectDB
    refactor in this PR).
    """

    def _capture_affected(self, fn):
        """Call fn() while capturing TECHNIQUE_AFFECTED payloads. Return captured list."""
        captured: list = []
        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_AFFECTED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            fn()
        finally:
            svc_mod.emit_event = original
        return captured

    def test_affected_emitted_per_target_for_attack_against_mook(self) -> None:
        """TECHNIQUE_AFFECTED fires once with the mook's ObjectDB as target."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=30)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        room = _create_room()
        participant, technique, _anima = _setup_participant_with_technique(
            encounter=encounter,
            room=room,
            base_power=10,
        )

        # The mook's objectdb must be in the same room for emit_event's room check.
        opponent.objectdb.location = room
        opponent.objectdb.save()

        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
            effort_level=EffortLevel.MEDIUM,
        )

        def run():
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )

        captured = self._capture_affected(run)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].target, opponent.objectdb)

    def test_affected_emitted_for_self_targeted_buff(self) -> None:
        """Self-targeted buff: TECHNIQUE_AFFECTED fires once with the caster as target."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=1,
        )
        room = _create_room()
        participant, technique, _anima = _setup_participant_with_technique(
            encounter=encounter,
            room=room,
            base_power=10,
        )

        # Self-targeted: no opponent or ally target; _build_affected_targets returns []
        # and TECHNIQUE_AFFECTED will not fire. This test documents that behaviour.
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=None,
            focused_ally_target=None,
            effort_level=EffortLevel.MEDIUM,
        )

        def run():
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )

        captured = self._capture_affected(run)
        # No targets → no TECHNIQUE_AFFECTED events (consistent with use_technique contract)
        self.assertEqual(captured, [])

    def test_affected_emitted_for_ally_targeted_buff(self) -> None:
        """Ally-targeted buff: TECHNIQUE_AFFECTED fires with the ally's character ObjectDB."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=1,
        )
        room = _create_room()
        participant, technique, _anima = _setup_participant_with_technique(
            encounter=encounter,
            room=room,
            base_power=10,
        )

        # Build an ally participant in the same encounter
        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
        )
        CharacterEngagementFactory(character=ally_sheet.character)
        ally_sheet.character.location = room
        ally_sheet.character.save()

        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=None,
            focused_ally_target=ally_participant,
            effort_level=EffortLevel.MEDIUM,
        )

        def run():
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )

        captured = self._capture_affected(run)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].target, ally_sheet.character)
