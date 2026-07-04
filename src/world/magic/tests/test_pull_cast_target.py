"""Tests for cast (non-combat) charge-site target plumbing (#1831 Task 5).

``_charge_cast_pull`` now accepts an optional ``target: ObjectDB | None`` that it
threads onto ``PullActionContext.target`` — which ``resolve_pull_effects`` feeds
into ``court_regard_modulation`` (Task 3) so a COVENANT_ROLE cast pull's FLAT_BONUS
is scaled by the Court leader's signed regard for the live cast target.

Two things are proven here:

1. **End-to-end amplification** — charging a cast pull against a regarded target
   (NEUTRAL polarity empowers either sign) yields a strictly higher FLAT_BONUS
   than the identical pull against an indifferent (no-regard) target.
2. **use_technique wiring** — ``use_technique`` resolves ``targets[0]`` and forwards
   it to ``_charge_cast_pull`` as ``target=``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, RegardPolarity, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.services import use_technique
from world.magic.services.techniques import _charge_cast_pull
from world.magic.types.pull import CastPullDeclaration
from world.npc_services.factories import NpcRegardFactory
from world.scenes.services import active_persona_for_sheet


class ChargeCastPullCourtRegardAmplificationTests(TestCase):
    """A Court servant's cast pull is amplified by the leader's regard (NEUTRAL polarity)."""

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
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
            regard_polarity=RegardPolarity.NEUTRAL,
        )
        self.technique = TechniqueFactory()

    def _charge_against(self, target_sheet: object) -> int:
        """Build a fresh engaged Court servant and charge a cast pull against
        ``target_sheet.character``. Returns the resolved FLAT_BONUS."""
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
        cast_pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(thread,))

        pull_flat_bonus, _effective_power, _resolved = _charge_cast_pull(
            character=servant.character,
            technique=self.technique,
            cast_pull=cast_pull,
            effective_power=0,
            target=target_sheet.character,
        )
        return pull_flat_bonus

    def test_regarded_target_amplifies_neutral_polarity_pull(self) -> None:
        indifferent_target = CharacterSheetFactory()
        baseline = self._charge_against(indifferent_target)

        regarded_target = CharacterSheetFactory()
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(self.leader_sheet),
            target_persona=active_persona_for_sheet(regarded_target),
            value=500,
        )
        amplified = self._charge_against(regarded_target)

        self.assertEqual(baseline, 10, "No regard on the target must leave the pull unamplified.")
        self.assertGreater(
            amplified,
            baseline,
            "A regarded target must amplify a NEUTRAL Court-role cast pull's FLAT_BONUS.",
        )


class UseTechniqueForwardsFirstTargetTests(TestCase):
    """use_technique resolves targets[0] and forwards it to _charge_cast_pull."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def _character(self) -> object:
        sheet = CharacterSheetFactory()
        character = sheet.character
        CharacterAnimaFactory(character=character, current=20, maximum=20)
        return character

    def test_forwards_first_target_when_present(self) -> None:
        character = self._character()
        technique = TechniqueFactory()
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())
        target = CharacterSheetFactory().character

        with patch(
            "world.magic.services.techniques._charge_cast_pull",
            return_value=(0, 0, []),
        ) as mock_charge:
            use_technique(
                character=character,
                technique=technique,
                resolve_fn=MagicMock(return_value="ok"),
                cast_pull=cast_pull,
                targets=[target],
            )

        mock_charge.assert_called_once()
        self.assertEqual(mock_charge.call_args.kwargs["target"], target)

    def test_forwards_none_when_no_targets(self) -> None:
        character = self._character()
        technique = TechniqueFactory()
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())

        with patch(
            "world.magic.services.techniques._charge_cast_pull",
            return_value=(0, 0, []),
        ) as mock_charge:
            use_technique(
                character=character,
                technique=technique,
                resolve_fn=MagicMock(return_value="ok"),
                cast_pull=cast_pull,
                targets=None,
            )

        mock_charge.assert_called_once()
        self.assertIsNone(mock_charge.call_args.kwargs["target"])
