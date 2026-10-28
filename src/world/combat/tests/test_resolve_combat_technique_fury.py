"""TDD tests for Task 4 (#1454): resolve_combat_technique honors soulfray-accept + fury.

Cases:
a) confirm_soulfray_risk=False + soulfray warning → no-op (no damage), anima unchanged.
b) fury_commitment set → CombatTechniqueResult.fury_committed == realized_tier. (Fury's
   trade lands on the engagement before use_technique, #4738; the journey
   integration_tests/test_surrendering_control_to_fury_journeys.py covers what it buys.)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory, OpponentTier
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
    FuryTierFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.fury import FuryResolution
from world.magic.types import CastCheck
from world.magic.types.techniques import SoulfrayWarning
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

# get_soulfray_warning is imported at module-level in world.magic.services.techniques
# (not lazy), so we must patch the bound name there.
_SOULFRAY_WARNING_PATCH = "world.magic.services.techniques.get_soulfray_warning"

# run_fury_for_action is imported lazily inside resolve_combat_technique, so
# patching the origin module is correct (repo convention: lazy-import + patch-origin).
_RUN_FURY_PATCH = "world.magic.services.fury.run_fury_for_action"

# use_technique is imported lazily inside resolve_combat_technique via
# `from world.magic.services import use_technique` — patch the re-export point.
_USE_TECHNIQUE_PATCH = "world.magic.services.use_technique"

_MOCK_SOULFRAY_WARNING = SoulfrayWarning(
    stage_name="Stage One",
    stage_description="You are accruing soulfray.",
    has_death_risk=False,
)


def _setup_combat_scenario():
    """Build a minimal PC-vs-mook scenario for resolve_combat_technique unit tests.

    Returns (participant, action, opponent, anima, technique).
    """
    encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
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
        db_key="TestRoom",
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
        confirm_soulfray_risk=False,
    )
    return participant, action, opponent, anima, technique


class SoulfrayGateHonorsActionFlagTests(TestCase):
    """resolve_combat_technique passes action.confirm_soulfray_risk to use_technique.

    When confirm_soulfray_risk is False and there is an active soulfray warning,
    use_technique returns confirmed=False → _build_combat_result produces an
    empty CombatTechniqueResult (no damage, no anima spent).
    """

    def test_unconfirmed_soulfray_returns_no_damage(self) -> None:
        """confirm_soulfray_risk=False + active soulfray warning → no damage."""
        participant, action, _opponent, _anima, _technique = _setup_combat_scenario()

        with patch(_SOULFRAY_WARNING_PATCH, return_value=_MOCK_SOULFRAY_WARNING):
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                cast_check=CastCheck(check_type=MagicMock(), extra_traits=()),
                offense_check_fn=None,
            )

        self.assertEqual(
            result.damage_results,
            [],
            "No damage results when soulfray gate fires (confirm_soulfray_risk=False).",
        )

    def test_unconfirmed_soulfray_leaves_anima_unchanged(self) -> None:
        """confirm_soulfray_risk=False + soulfray warning → anima is NOT deducted."""
        participant, action, _opponent, anima, _technique = _setup_combat_scenario()

        with patch(_SOULFRAY_WARNING_PATCH, return_value=_MOCK_SOULFRAY_WARNING):
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                cast_check=CastCheck(check_type=MagicMock(), extra_traits=()),
                offense_check_fn=None,
            )

        anima.refresh_from_db()
        self.assertEqual(
            anima.current,
            20,
            "Anima must not be spent when the soulfray gate fires.",
        )


class FuryAuditTests(TestCase):
    """resolve_combat_technique records the realized Fury tier on its result."""

    def test_fury_committed_on_result(self) -> None:
        """CombatTechniqueResult.fury_committed is set to the realized_tier from FuryResolution."""
        participant, action, _opponent, _anima, technique = _setup_combat_scenario()

        fury_tier = FuryTierFactory()
        fury_res = FuryResolution(
            realized_tier=fury_tier,
            control_surrendered=7,
            intensity_gained=4,
            berserk_severity=0,
        )
        action.fury_commitment = fury_tier
        action.save(update_fields=["fury_commitment"])

        from world.magic.types import TechniqueUseResult
        from world.magic.types.techniques import AnimaCostResult

        fake_cost = AnimaCostResult(
            base_cost=3, effective_cost=3, control_delta=5, current_anima=20, deficit=0
        )
        fake_use_result = TechniqueUseResult(
            anima_cost=fake_cost, confirmed=False, technique=technique
        )

        with patch(_RUN_FURY_PATCH, return_value=fury_res):
            with patch(_USE_TECHNIQUE_PATCH, return_value=fake_use_result):
                result = resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=ActionCategory.PHYSICAL,
                    cast_check=CastCheck(check_type=MagicMock(), extra_traits=()),
                    offense_check_fn=None,
                )

        self.assertIs(
            result.fury_committed,
            fury_tier,
            "CombatTechniqueResult.fury_committed must be the realized_tier from FuryResolution.",
        )
