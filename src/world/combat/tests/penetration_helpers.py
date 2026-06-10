"""Shared builder helpers for penetration-contest test suites (#767).

``_build_resolver`` and ``_ledger`` are used by both test_penetration.py and
test_penetration_seed.py; they live here to avoid cross-test-module imports,
which are not an established repo pattern.
"""

from decimal import Decimal
from unittest.mock import MagicMock

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
from world.combat.services import CombatTechniqueResolver
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.types.power_ledger import PowerLedger


def _ledger(power: int) -> PowerLedger:
    return PowerLedger(entries=(), total=power)


def _build_resolver(*, barrier_strength=None, base_power=20, offense_sl=2):
    """Build a resolver against an opponent with the given ward.

    ``offense_check_fn`` returns a fixed offense success level so the offense
    roll is deterministic and separable from the penetration roll.
    """
    encounter = CombatEncounterFactory(round_number=1)
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=30)
    opponent = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=200,
        max_health=200,
        threat_pool=pool,
        barrier_strength=barrier_strength,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
        damage_profile=False,
    )
    # Profile whose budget scales with effective power (budget = base + power),
    # so penetration scaling actually moves the resulting damage. The default
    # auto-seeded profile has intensity_multiplier=0 (flat damage) which would
    # mask power changes.
    TechniqueDamageProfileFactory(
        technique=technique,
        base_damage=10,
        damage_intensity_multiplier=Decimal("1.0"),
        minimum_success_level=1,
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    offense_fn = MagicMock(return_value=MagicMock(success_level=offense_sl))
    return CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=ActionCategory.PHYSICAL,
        offense_check_type=MagicMock(),
        offense_check_fn=offense_fn,
    )
