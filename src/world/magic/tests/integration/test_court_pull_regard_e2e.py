"""E2E combat journey: Court-role thread-pull regard modulation (#1831 Task 7).

Builds ONE Court scenario — a COURT covenant + leader, a servant with an
engaged Court-role membership, and a single COVENANT_ROLE thread carrying
BOTH an OFFENSIVE ``ThreadPullEffect`` (FLAT_BONUS) and a PROTECTIVE
``ThreadPullEffect`` (INTENSITY_BUMP) — then drives *real* ``commit_combat_pull``
commits (the same seam ``CastTechniqueAction`` and the clash-contribution path
use) against a negative-regard ENEMY and a positive-regard ALLY, reading the
snapshotted ``CombatPullResolvedEffect.scaled_value`` for each polarity off the
combat damage path.

``ThreadPullEffect`` is unique per ``(target_kind, resonance, tier,
min_thread_level)`` regardless of ``effect_kind`` (see
``threadpulleffect_lookup_key`` in ``world/magic/models/threads.py``), so the
two effects on this one thread are authored at different tiers (0 and 1) —
``resolve_pull_effects`` resolves every tier from 0 up to the pull's tier, so
a single tier-1 pull against this thread still resolves both rows.

Matrix (hand-computed via the empower formula in
``court_regard_modulation``: ``base + round(base * abs(regard) / REGARD_MAX *
COURT_REGARD_PULL_K)``, with ``REGARD_MAX=1000`` and ``COURT_REGARD_PULL_K=1.0``):

- Pull vs the ENEMY (regard=-500): OFFENSIVE amplified 10 -> 15; PROTECTIVE
  stays at base 10.
- Pull vs the ALLY (regard=+500): PROTECTIVE amplified 10 -> 15; OFFENSIVE
  stays at base 10.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatPullResolvedEffect
from world.combat.pull_helpers import commit_combat_pull
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import COURT_REGARD_PULL_K, EffectKind, RegardPolarity, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.types.pull import CastPullDeclaration
from world.npc_services.factories import NpcRegardFactory
from world.npc_services.models import REGARD_MAX
from world.scenes.constants import RoundStatus
from world.scenes.services import active_persona_for_sheet

OFFENSIVE_BASE = 10
PROTECTIVE_BASE = 10


def _empowered(base: int, regard: int) -> int:
    """Hand-computed mirror of ``court_regard_modulation``'s empower formula."""
    bonus = round(base * (abs(regard) / REGARD_MAX) * COURT_REGARD_PULL_K)
    return base + bonus


class CourtPullRegardModulationJourneyTests(TestCase):
    """Full OFFENSIVE/PROTECTIVE x ENEMY/ALLY matrix through commit_combat_pull."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.resonance = ResonanceFactory()
        self.leader_sheet = CharacterSheetFactory()
        self.covenant = CovenantFactory(
            covenant_type=CovenantType.COURT,
            leader=self.leader_sheet,
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)

        # OFFENSIVE effect at tier 0 -- always resolved alongside a tier-1 pull,
        # since resolve_pull_effects walks every effect_tier in range(tier + 1).
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=OFFENSIVE_BASE,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        # PROTECTIVE effect at tier 1 -- distinct lookup key (different tier)
        # from the OFFENSIVE row above, so both can anchor the same thread.
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            as_intensity_bump=True,
            intensity_bump_amount=PROTECTIVE_BASE,
            regard_polarity=RegardPolarity.PROTECTIVE,
        )

    def _commit_pull_against(self, target_sheet: object) -> tuple[int, int]:
        """Build a fresh engaged Court servant + combat round and commit a
        tier-1 pull against ``target_sheet.character``.

        Returns the (offensive FLAT_BONUS, protective INTENSITY_BUMP)
        snapshotted ``scaled_value`` pair.
        """
        servant = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=servant,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )
        thread = ThreadFactory(
            owner=servant,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            target_trait=None,
        )
        CharacterResonanceFactory(character_sheet=servant, resonance=self.resonance, balance=20)
        CharacterAnimaFactory(character=servant.character, current=10, maximum=20)

        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=servant,
            status=ParticipantStatus.ACTIVE,
        )
        cast_pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(thread,))

        commit_combat_pull(
            cast_pull=cast_pull,
            participant=participant,
            encounter=encounter,
            technique_id=1,
            target=target_sheet.character,
        )

        offensive = CombatPullResolvedEffect.objects.get(
            pull__participant=participant,
            kind=EffectKind.FLAT_BONUS,
        ).scaled_value
        protective = CombatPullResolvedEffect.objects.get(
            pull__participant=participant,
            kind=EffectKind.INTENSITY_BUMP,
        ).scaled_value
        return offensive, protective

    def test_full_polarity_matrix_through_real_combat_pull(self) -> None:
        enemy_sheet = CharacterSheetFactory()
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(self.leader_sheet),
            target_persona=active_persona_for_sheet(enemy_sheet),
            value=-500,
        )
        offensive_vs_enemy, protective_vs_enemy = self._commit_pull_against(enemy_sheet)

        ally_sheet = CharacterSheetFactory()
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(self.leader_sheet),
            target_persona=active_persona_for_sheet(ally_sheet),
            value=500,
        )
        offensive_vs_ally, protective_vs_ally = self._commit_pull_against(ally_sheet)

        self.assertEqual(
            offensive_vs_enemy,
            _empowered(OFFENSIVE_BASE, -500),
            "OFFENSIVE effect must be amplified by the leader's negative regard for the enemy.",
        )
        self.assertEqual(
            protective_vs_enemy,
            PROTECTIVE_BASE,
            "PROTECTIVE effect must NOT be amplified against a negative-regard (enemy) target.",
        )
        self.assertEqual(
            protective_vs_ally,
            _empowered(PROTECTIVE_BASE, 500),
            "PROTECTIVE effect must be amplified by the leader's positive regard for the ally.",
        )
        self.assertEqual(
            offensive_vs_ally,
            OFFENSIVE_BASE,
            "OFFENSIVE effect must NOT be amplified against a positive-regard (ally) target.",
        )
