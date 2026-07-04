"""Tests for combat charge-site target plumbing (#1831 Task 4).

``commit_combat_pull`` now accepts an optional ``target: ObjectDB | None`` that it
threads onto ``PullActionContext.target`` — which ``resolve_pull_effects`` feeds
into ``court_regard_modulation`` (Task 3) so a COVENANT_ROLE pull's FLAT_BONUS is
scaled by the Court leader's signed regard for the live combat target.

Three things are proven here:

1. **End-to-end amplification** — committing a real combat pull against a
   negative-regard opponent yields a strictly higher snapshotted
   ``CombatPullResolvedEffect.scaled_value`` than the identical pull against an
   indifferent (no-regard) target.
2. **Cast-path wiring** — ``CastTechniqueAction._commit_combat_pull`` resolves the
   focused target (opponent, else ally) from raw declaration kwargs via
   ``resolve_focused_target_objectdb`` and forwards it to ``commit_combat_pull``.
3. **Clash-path wiring** — ``_dispatch_clash_contribution`` forwards
   ``clash.npc_opponent.objectdb`` as the target (a Clash is always PC(s)-vs-one-NPC).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.constants import ActionBackend
from actions.definitions.cast import CastTechniqueAction
from actions.player_interface import _dispatch_clash_contribution
from actions.types import ActionRef
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ClashActionSlot, ParticipantStatus
from world.combat.factories import (
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatPullResolvedEffect
from world.combat.pull_helpers import commit_combat_pull
from world.combat.round_context import CombatRoundContext
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
from world.magic.types.pull import CastPullDeclaration
from world.npc_services.factories import NpcRegardFactory
from world.scenes.constants import RoundStatus
from world.scenes.services import active_persona_for_sheet


class CommitCombatPullCourtRegardAmplificationTests(TestCase):
    """A Court servant's combat pull is amplified by the leader's negative regard."""

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
            regard_polarity=RegardPolarity.OFFENSIVE,
        )

    def _commit_pull_against(self, target_sheet: object) -> int:
        """Build a fresh engaged Court servant + combat round and commit a pull
        against ``target_sheet.character``. Returns the resolved FLAT_BONUS
        ``scaled_value``."""
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

        resolved = CombatPullResolvedEffect.objects.get(
            pull__participant=participant,
            kind=EffectKind.FLAT_BONUS,
        )
        return resolved.scaled_value

    def test_negative_regard_amplifies_offensive_pull(self) -> None:
        indifferent_target = CharacterSheetFactory()
        baseline = self._commit_pull_against(indifferent_target)

        hated_target = CharacterSheetFactory()
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(self.leader_sheet),
            target_persona=active_persona_for_sheet(hated_target),
            value=-500,
        )
        amplified = self._commit_pull_against(hated_target)

        self.assertEqual(baseline, 10, "No regard on the target must leave the pull unamplified.")
        self.assertGreater(
            amplified,
            baseline,
            "A negative-regard target must amplify an OFFENSIVE Court-role pull's "
            "snapshotted scaled_value.",
        )


class CastCommitCombatPullTargetWiringTests(TestCase):
    """CastTechniqueAction._commit_combat_pull resolves + forwards the focused target."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def _ctx(self) -> tuple[CombatRoundContext, object]:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        return CombatRoundContext(participant), encounter

    def test_resolves_focused_opponent_target(self) -> None:
        ctx, encounter = self._ctx()
        enemy_sheet = CharacterSheetFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            persona=enemy_sheet.primary_persona,
        )
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())

        with patch("world.combat.pull_helpers.commit_combat_pull") as mock_commit:
            CastTechniqueAction._commit_combat_pull(
                cast_pull,
                ctx,
                technique_id=1,
                kwargs={"focused_opponent_target_id": opponent.pk},
            )

        mock_commit.assert_called_once()
        self.assertEqual(mock_commit.call_args.kwargs["target"], opponent.objectdb)

    def test_resolves_focused_ally_target_when_no_opponent(self) -> None:
        ctx, encounter = self._ctx()
        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())

        with patch("world.combat.pull_helpers.commit_combat_pull") as mock_commit:
            CastTechniqueAction._commit_combat_pull(
                cast_pull,
                ctx,
                technique_id=1,
                kwargs={"focused_ally_target_id": ally_participant.pk},
            )

        mock_commit.assert_called_once()
        self.assertEqual(mock_commit.call_args.kwargs["target"], ally_sheet.character)

    def test_no_focused_target_kwargs_forwards_none(self) -> None:
        ctx, _encounter = self._ctx()
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())

        with patch("world.combat.pull_helpers.commit_combat_pull") as mock_commit:
            CastTechniqueAction._commit_combat_pull(
                cast_pull,
                ctx,
                technique_id=1,
                kwargs={},
            )

        mock_commit.assert_called_once()
        self.assertIsNone(mock_commit.call_args.kwargs["target"])


class DispatchClashContributionTargetWiringTests(TestCase):
    """_dispatch_clash_contribution forwards the clash's NPC opponent as the target."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_target_is_clash_npc_opponent_objectdb(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        ctx = CombatRoundContext(participant)

        clash = ClashFactory(encounter=encounter)
        enemy_sheet = CharacterSheetFactory()
        clash.npc_opponent.objectdb = enemy_sheet.character
        clash.npc_opponent.save(update_fields=["objectdb"])

        technique = TechniqueFactory()
        cast_pull = CastPullDeclaration(resonance=ResonanceFactory(), tier=1, threads=())
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=clash.pk,
            clash_action_slot=ClashActionSlot.FOCUSED.value,
        )

        with patch("world.combat.pull_helpers.commit_combat_pull") as mock_commit:
            _dispatch_clash_contribution(
                ctx,
                ref,
                {"technique_id": technique.pk, "cast_pull": cast_pull},
            )

        mock_commit.assert_called_once()
        self.assertEqual(
            mock_commit.call_args.kwargs["target"],
            enemy_sheet.character,
        )
