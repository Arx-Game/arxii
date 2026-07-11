"""E2E: the full out-of-combat sudden-harm Interpose player journey (#1316).

Task 8 closes a *narrow* gap: three prior tasks each proved one link of this chain
in isolation —

- ``world.scenes.tests.test_sudden_harm`` (Tasks 3 & 5) calls
  ``arm_or_apply_sudden_harm``/``resolve_pending_interpose_harm`` directly, and
  declares Interpose via ``declare_interpose_scene`` directly (not through the
  action layer).
- ``world.mechanics.tests.test_effect_handlers`` (Task 6)
  ``DealDamageHandlerTests.test_defers_when_bystander_present`` already fires the
  harm through the real ``apply_effect`` entrypoint and confirms the defer, but
  stops there — it never carries the journey through to Interpose declaration or
  round resolution.
- ``actions.tests.test_round_actions`` (Task 7) ``InterposeSceneActionTests``
  proves ``InterposeSceneAction`` writes the declaration, but starts from a bare
  hand-built ``SceneRound``/``SceneRoundParticipant`` fixture, not one produced by
  a real sudden-harm arming.

No existing test chains all three seams (``apply_effect`` fires the trap ->
``InterposeSceneAction.run()`` declares -> ``resolve_scene_round`` resolves) in one
continuous flow, the way an actual player/GM would experience it. That is the
whole of this file's job — no new production code, no re-proving of the
individual links above.

Determinism note: the clean-block outcome is forced with the same
``dispatch_capability_reaction`` mock used by
``test_sudden_harm.ResolvePendingInterposeHarmTests.test_clean_block_declaration_prevents_damage``
(itself mirroring ``world.combat.tests.test_interpose_resolution``) — an
``outcome_fn``-invoking side effect that drives the real
``dispatch_interpose``/``apply_interpose_outcome`` mutation-in-place logic without
needing a full capability-grant + dice-roll fixture. ``test_interpose_damage_path``
(combat) instead mocks the lower-level ``perform_check`` because combat's
Interpose runs the check through ``dispatch_interpose`` -> ``perform_check``
directly; the non-combat path resolves via ``dispatch_capability_reaction``, so
that is the correct seam to pin here (matches the established, verified-working
approach already landed in this exact codebase for this exact feature).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.combat.interpose_content import ensure_interpose_content
from world.conditions.factories import DamageTypeFactory
from world.mechanics.constants import ResolutionType
from world.mechanics.effect_handlers import apply_effect
from world.mechanics.types import ChallengeResolutionResult
from world.scenes.models import PendingSuddenHarm
from world.scenes.round_services import resolve_scene_round
from world.vitals.factories import CharacterVitalsFactory


def _clean_block_dispatch(  # noqa: PLR0913
    actor,
    target_object,
    *,
    challenge_name,
    approach,
    error_msg,
    outcome_fn,
    extra_modifiers=0,
    **kwargs,
):
    """Force a clean-block DESTROY outcome, exactly as test_sudden_harm.py's
    ResolvePendingInterposeHarmTests._dispatch_clean_block does — invokes
    outcome_fn with a DESTROY ChallengeResolutionResult so the real
    dispatch_interpose/apply_interpose_outcome mutation-in-place logic runs."""
    result = ChallengeResolutionResult(
        challenge_instance_id=1,
        challenge_name=challenge_name,
        approach_name="telekinesis",
        check_result=None,
        consequence=None,
        applied_effects=[],
        resolution_type=ResolutionType.DESTROY,
        challenge_deactivated=True,
        display_consequences=[],
    )
    outcome_fn(result)
    return result


class SuddenHarmInterposeE2ETests(TestCase):
    """Full journey: trap fires via apply_effect -> ally Interposes via the real
    action seam -> the round resolves -> the outcome is confirmed."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="TrapRoom", nohome=True)

        victim_sheet = CharacterSheetFactory()
        self.victim = victim_sheet.character
        self.victim.db_location = self.room
        self.victim.save(update_fields=["db_location"])
        self.victim_sheet = victim_sheet
        CharacterVitalsFactory(character_sheet=victim_sheet, health=100, max_health=100)

        ally_sheet = CharacterSheetFactory()
        self.ally = ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])
        self.ally_sheet = ally_sheet
        CharacterVitalsFactory(character_sheet=ally_sheet, health=100, max_health=100)

        self.damage_type = DamageTypeFactory()

    def _fire_trap(self, amount: int) -> None:
        """Fire a DEAL_DAMAGE consequence at the victim through the real,
        production consequence-resolution entrypoint (apply_effect) — not by
        calling _deal_damage/arm_or_apply_sudden_harm directly."""
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=amount,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=self.victim)
        result = apply_effect(effect, context)
        self.assertTrue(result.applied, result.skip_reason)

    def test_bystander_interpose_full_journey_clean_block_saves_the_target(self) -> None:
        """The complete player journey: trap fires and holds, the ally declares
        Interpose via the real action seam, the round resolves, a clean block
        leaves the victim untouched."""
        ensure_interpose_content()

        # Step 1-2: fire the trap through the real production entrypoint; harm holds.
        self._fire_trap(20)

        self.victim_sheet.vitals.refresh_from_db()
        self.assertEqual(
            self.victim_sheet.vitals.health, 100, "harm must hold, not apply, with a bystander"
        )
        pending = PendingSuddenHarm.objects.get(target_sheet=self.victim_sheet)
        scene_round = pending.scene_round

        # Step 3: the ally declares Interpose via the SAME seam a real telnet/web
        # player uses — InterposeSceneAction.run(), not declare_interpose_scene directly.
        from actions.definitions.rounds import InterposeSceneAction

        action_result = InterposeSceneAction().run(self.ally, ally_name=self.victim.db_key)
        self.assertTrue(action_result.success, action_result.message)

        # Step 4-5: resolve the round; force a deterministic clean-block outcome.
        with patch(
            "world.mechanics.reactions.dispatch_capability_reaction",
            side_effect=_clean_block_dispatch,
        ) as mocked:
            resolve_scene_round(scene_round)
            self.assertTrue(mocked.called, "dispatch_interpose must route through the reaction")

        self.victim_sheet.vitals.refresh_from_db()
        self.assertEqual(
            self.victim_sheet.vitals.health, 100, "a clean block must leave the victim untouched"
        )
        self.assertFalse(
            PendingSuddenHarm.objects.filter(target_sheet=self.victim_sheet).exists(),
            "the pending harm must be resolved (deleted) once the round resolves",
        )

    def test_solo_target_no_round_created_full_journey(self) -> None:
        """The same real apply_effect entrypoint, but nobody is present: no round
        is bootstrapped and the damage lands immediately, end to end."""
        self.ally.db_location = None
        self.ally.save(update_fields=["db_location"])

        self._fire_trap(20)

        self.victim_sheet.vitals.refresh_from_db()
        self.assertEqual(
            self.victim_sheet.vitals.health,
            80,
            "solo target: full damage lands immediately with no bystander to hold for",
        )
        self.assertFalse(
            PendingSuddenHarm.objects.filter(target_sheet=self.victim_sheet).exists(),
            "no round/pending row should ever exist for a solo target",
        )
