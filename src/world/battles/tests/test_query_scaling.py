"""Marginal per-declaration query-cost gate for resolve_battle_round.

Guards the scaling property (#1741, tightened by #1846): per-declaration
marginal query cost must stay bounded. Uses two rounds of different sizes
and asserts the marginal cost per added declaration stays below a budget.

The singleton-caching (SoulfrayConfig) + select_related (.character hop)
wins (#1741), plus the catalog cache (ArxSharedMemoryManager.cached_all())
and BattleStateCache roster-state cache (#1846), are what make the
marginal cost drop. A regression in any of these would raise the marginal
above the budget.
"""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from actions.factories import ActionTemplateFactory
from world.battles.models import BattleActionKind, BattleSideRole
from world.battles.resolution import resolve_battle_round
from world.battles.services import (
    add_side,
    add_unit,
    begin_battle_round,
    create_battle,
    declare_battle_action,
    enlist_participant,
)
from world.battles.tests.test_resolution import _success_result
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.magic.models.soulfray import SoulfrayConfig
from world.vitals.factories import CharacterVitalsFactory


class ResolveBattleRoundQueryScalingTests(TestCase):
    """Assert marginal per-declaration query cost stays bounded.

    Post-#1741, the SoulfrayConfig singleton lookup and the .character
    select_related hop are eliminated from the per-declaration marginal.
    Post-#1846, the catalog cache and BattleStateCache further eliminate
    per-declaration roster/catalog re-queries. Any regression in marginal
    cost indicates a new per-declaration query was introduced in the
    use_technique path or the battles modifier stack.
    """

    def setUp(self) -> None:
        SoulfrayConfig.objects.flush_singleton_cache()
        SoulfrayConfig.flush_instance_cache()
        self.soulfray_config = SoulfrayConfigFactory()

    def _build_round_with_declarations(self, num_declarations: int):
        """Build a battle round with N STRIKE declarations, return the round."""
        battle = create_battle(name=f"Scaling Battle N={num_declarations}")
        attacker_side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defender_side = add_side(battle=battle, role=BattleSideRole.DEFENDER)

        technique = TechniqueFactory(action_template=ActionTemplateFactory(), damage_profile=False)
        unit = add_unit(
            battle=battle,
            side=defender_side,
            name="Target Unit",
            descriptor="enemy",
            strength=1000,
        )

        battle_round = begin_battle_round(battle=battle)

        for _ in range(num_declarations):
            sheet = CharacterSheetFactory()
            CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
            CharacterTechniqueFactory(character=sheet, technique=technique)
            CharacterAnimaFactory(character=sheet.character, current=50, maximum=50)
            participant = enlist_participant(
                battle=battle, character_sheet=sheet, side=attacker_side
            )
            declare_battle_action(
                participant=participant,
                action_kind=BattleActionKind.STRIKE,
                technique=technique,
                target_unit=unit,
            )

        return battle_round

    def _count_queries_for_round(self, battle_round) -> int:
        """Resolve a round and return the number of SQL queries executed."""
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(5)
            with CaptureQueriesContext(connection) as ctx:
                resolve_battle_round(battle_round=battle_round)
        return len(ctx)

    def test_marginal_per_declaration_cost_stays_bounded(self) -> None:
        """Marginal query cost per added declaration stays below budget.

        Measures Q(2) and Q(5) and asserts (Q(5) - Q(2)) / 3 < budget.
        Post-#1846, the catalog cache (ArxSharedMemoryManager.cached_all())
        and BattleStateCache eliminate per-declaration re-queries of roster
        and catalog state on top of #1741's SoulfrayConfig singleton +
        .character hop wins.
        """
        round_small = self._build_round_with_declarations(num_declarations=2)
        round_large = self._build_round_with_declarations(num_declarations=5)

        q_small = self._count_queries_for_round(round_small)
        q_large = self._count_queries_for_round(round_large)

        marginal = (q_large - q_small) / 3
        # baseline (#1846): Q(2)=77, Q(5)=149, marginal=24.0
        # Budget set just above this observed marginal — a regression here means
        # a new per-declaration query was reintroduced into the modifier stack,
        # scope resolution, or use_technique envelope.
        per_declaration_budget = 30
        self.assertLess(
            marginal,
            per_declaration_budget,
            f"Marginal per-declaration query cost {marginal:.1f} exceeds budget "
            f"{per_declaration_budget}. Q(2)={q_small}, Q(5)={q_large}. "
            "A new per-declaration query may have been introduced in the "
            "use_technique path or the battles modifier stack (#1846).",
        )
