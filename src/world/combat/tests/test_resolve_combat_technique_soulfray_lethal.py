"""Soulfray can kill only in combat encounters (#4098 fix round 2).

A LETHAL ``CombatEncounter`` is the one context where ``use_technique`` must
still be allowed to pass a lethal value through to Soulfray — unlike a scene
cast or a battle (``world.scenes.tests.test_cast_soulfray_nonlethal``,
``world.battles.tests.test_resolution_soulfray_nonlethal``), which must always
pass ``lethal=False``. ``resolve_combat_technique`` already threads
``lethal=encounter.is_lethal``; this proves that wiring still reaches the real
death seam's gate for a genuinely lethal encounter.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory, OpponentTier, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_combat_technique
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

# use_technique is imported lazily inside resolve_combat_technique via
# `from world.magic.services import use_technique` — patch the re-export point.
_USE_TECHNIQUE_PATCH = "world.magic.services.use_technique"


def _setup_lethal_combat_scenario():
    """A minimal PC-vs-mook scenario in a LETHAL CombatEncounter.

    Mirrors world.combat.tests.test_resolve_combat_technique_fury
    ._setup_combat_scenario, with risk_level pinned to LETHAL so
    encounter.is_lethal is True (the factory default is MODERATE).
    """
    encounter = CombatEncounterFactory(
        status=RoundStatus.RESOLVING, round_number=1, risk_level=RiskLevel.LETHAL
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
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
    anima = CharacterAnimaFactory(character=sheet, current=20, maximum=20)
    CharacterEngagementFactory(character=sheet)
    room = ObjectDBFactory(
        db_key="LethalCombatTestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    sheet.character.location = room
    sheet.character.save()

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=20),
        intensity=5,
        control=10,
        anima_cost=3,
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent,
        effort_level=EffortLevel.MEDIUM,
        confirm_soulfray_risk=True,
    )
    return participant, action, opponent, anima, technique


class CombatTechniqueStillReachesTheDeathSeamTests(TestCase):
    def test_lethal_encounter_cast_passes_lethal_true_to_use_technique(self) -> None:
        participant, action, _opponent, _anima, _technique = _setup_lethal_combat_scenario()
        self.assertTrue(participant.encounter.is_lethal)
        mock_result = MagicMock(confirmed=False)

        with patch(_USE_TECHNIQUE_PATCH, return_value=mock_result) as mock_use:
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        mock_use.assert_called_once()
        self.assertTrue(mock_use.call_args.kwargs["lethal"])
