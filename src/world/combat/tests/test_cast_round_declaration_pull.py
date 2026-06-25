"""TDD tests for Task 4 (#1455): combat cast declaration with a thread pull.

When a player declares a technique cast INTO a combat round with a cast_pull
(CastPullDeclaration), round_declaration must:

1. Resolve the participant + encounter from the CombatRoundContext.
2. Call spend_resonance_for_pull with a combat PullActionContext so a
   CombatPull row is persisted and resonance/anima are debited.
3. Enforce the one-pull-per-round cap: a second pull in the same round must
   fail cleanly (return a failure ActionResult or raise a handled error).

SQLite tier limits:
- The read-path sums (_sum_active_flat_bonuses / _sum_intensity_bump_pulls)
  are exercised directly to verify the persisted CombatPull row is visible —
  no full clash resolution is attempted here (several resolution paths are PG-only).
- @tag("postgres") tests for full resolution delta are deferred to a later task.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatPull
from world.combat.round_context import CombatRoundContext
from world.combat.services import _sum_active_flat_bonuses, compute_intensity_for_clash
from world.magic.constants import EffectKind, TargetKind
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
from world.scenes.constants import RoundStatus


def _make_pull_setup(
    *,
    effect_kind: str = EffectKind.FLAT_BONUS,
    tier: int = 1,
    flat_bonus_amount: int = 3,
    intensity_bump_amount: int | None = None,
):
    """Build a full pull-enabled combat scene and return a dict of useful objects.

    Creates:
    - A CharacterSheet with resonance, anima, and a TECHNIQUE-anchored Thread.
    - A Technique that matches the thread's anchor.
    - A ThreadPullCost row for the given tier.
    - A ThreadPullEffect row that will yield a non-zero applicable effect.
    - A CombatEncounter in DECLARING status + a CombatParticipant for the sheet.
    - A CombatRoundContext wrapping the participant.
    - A CastPullDeclaration referencing the resonance / tier / thread.
    """
    sheet = CharacterSheetFactory()
    resonance = ResonanceFactory()

    # Technique anchored to this sheet's character.
    technique = TechniqueFactory()

    # Thread anchored to the technique — passes _anchor_in_action when
    # involved_techniques contains technique.pk.
    thread = ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_technique=technique,
        target_trait=None,
        level=5,
    )

    # Resonance currency (balance >= cost).
    CharacterResonanceFactory(
        character_sheet=sheet,
        resonance=resonance,
        balance=10,
    )

    # Anima (current >= anima_per_thread × max(0, n-1); n=1 → anima cost = 0,
    # but we seed a positive value so future multi-thread tests can reuse this).
    CharacterAnimaFactory(
        character=sheet.character,
        current=10,
        maximum=20,
    )

    # Per-tier pull cost catalogue row.
    cost = ThreadPullCostFactory(tier=tier, resonance_cost=1, anima_per_thread=0)

    # Authored effect — must yield at least one non-inactive resolved effect for
    # spend_resonance_for_pull to proceed (it raises InvalidImbueAmount otherwise).
    if effect_kind == EffectKind.INTENSITY_BUMP:
        effect = ThreadPullEffectFactory(
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            tier=tier,
            min_thread_level=0,
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=intensity_bump_amount if intensity_bump_amount else 2,
            flat_bonus_amount=None,
        )
    else:
        effect = ThreadPullEffectFactory(
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            tier=tier,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=flat_bonus_amount,
        )

    # Combat context.
    encounter = CombatEncounterFactory(
        status=RoundStatus.DECLARING,
        round_number=1,
    )
    participant = CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
    )
    ctx = CombatRoundContext(participant)

    pull_decl = CastPullDeclaration(
        resonance=resonance,
        tier=tier,
        threads=(thread,),
    )

    return {
        "sheet": sheet,
        "resonance": resonance,
        "technique": technique,
        "thread": thread,
        "cost": cost,
        "effect": effect,
        "encounter": encounter,
        "participant": participant,
        "ctx": ctx,
        "pull_decl": pull_decl,
    }


class CombatCastRoundDeclarationPullTests(TestCase):
    """round_declaration with a cast_pull in CombatRoundContext commits a CombatPull."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_red_round_declaration_without_pull_does_not_create_combat_pull(self) -> None:
        """Baseline: without a cast_pull kwarg, no CombatPull row is created."""
        data = _make_pull_setup()
        action = _import_cast_action()

        # Should return a (PlayerAction, decl_kwargs) tuple (non-None) for a valid ctx.
        result = action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
        )

        # Declaration should succeed.
        self.assertIsNotNone(result)
        # No CombatPull without a pull declaration.
        self.assertFalse(
            CombatPull.objects.filter(participant=data["participant"]).exists(),
            "Without cast_pull, no CombatPull row should be created.",
        )

    def test_round_declaration_with_pull_creates_combat_pull(self) -> None:
        """round_declaration with a cast_pull persists a CombatPull for (participant, round)."""
        data = _make_pull_setup()
        action = _import_cast_action()

        result = action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )

        self.assertIsNotNone(
            result,
            "round_declaration should return a (PlayerAction, decl_kwargs) tuple.",
        )

        pull_qs = CombatPull.objects.filter(
            participant=data["participant"],
            round_number=data["encounter"].round_number,
        )
        self.assertTrue(
            pull_qs.exists(),
            "A CombatPull row must be created when cast_pull is declared into a combat round.",
        )
        pull = pull_qs.get()
        self.assertEqual(pull.resonance, data["resonance"])
        self.assertEqual(pull.tier, 1)
        self.assertIn(data["thread"], pull.threads.all())

    def test_round_declaration_with_pull_debits_resonance(self) -> None:
        """Resonance balance decreases after a combat cast pull."""
        data = _make_pull_setup()
        action = _import_cast_action()

        from world.magic.models import CharacterResonance

        cr_before = CharacterResonance.objects.get(
            character_sheet=data["sheet"],
            resonance=data["resonance"],
        )
        balance_before = cr_before.balance

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )

        cr_before.refresh_from_db()
        self.assertLess(
            cr_before.balance,
            balance_before,
            "Resonance balance must decrease after a combat cast pull.",
        )

    def test_round_declaration_pull_visible_to_flat_bonus_read_path(self) -> None:
        """_sum_active_flat_bonuses reflects the committed CombatPull's FLAT_BONUS effect."""
        data = _make_pull_setup(effect_kind=EffectKind.FLAT_BONUS, flat_bonus_amount=3)
        action = _import_cast_action()

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )

        # Invalidate handler cache so the next read reflects the new DB row.
        data["sheet"].character.combat_pulls.invalidate()

        bonus = _sum_active_flat_bonuses(data["participant"], data["encounter"])
        self.assertGreater(
            bonus,
            0,
            "_sum_active_flat_bonuses must return a positive value after a FLAT_BONUS pull.",
        )

    def test_round_declaration_pull_visible_to_intensity_read_path(self) -> None:
        """compute_intensity_for_clash reflects the committed CombatPull's INTENSITY_BUMP effect."""
        from world.combat.factories import CombatRoundActionFactory

        data = _make_pull_setup(effect_kind=EffectKind.INTENSITY_BUMP, intensity_bump_amount=2)
        action = _import_cast_action()

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )

        # Build a CombatRoundAction so compute_intensity_for_clash has something to work with.
        round_action = CombatRoundActionFactory(
            participant=data["participant"],
            focused_action=data["technique"],
        )

        # Invalidate handler cache.
        data["sheet"].character.combat_pulls.invalidate()

        intensity = compute_intensity_for_clash(data["participant"], round_action)
        # Base is technique.intensity (≥0); pull should add 2.
        self.assertGreaterEqual(
            intensity,
            data["technique"].intensity + 2,
            "compute_intensity_for_clash must include the INTENSITY_BUMP pull bonus.",
        )

    def test_second_pull_in_same_round_fails_cleanly(self) -> None:
        """A second round_declaration with a cast_pull in the same round fails cleanly.

        The duplicate (participant, round_number) unique constraint must surface as
        ActionDispatchError(PULL_ALREADY_COMMITTED), NOT as a bare IntegrityError.
        """
        from actions.errors import ActionDispatchError

        data = _make_pull_setup()
        action = _import_cast_action()

        # First declaration: should succeed.
        first = action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )
        self.assertIsNotNone(first, "First declaration with pull must succeed.")

        # Second declaration in the same round: must raise PULL_ALREADY_COMMITTED.
        with self.assertRaises(ActionDispatchError) as cm:
            action.round_declaration(
                data["ctx"],
                technique_id=data["technique"].pk,
                cast_pull=data["pull_decl"],
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.PULL_ALREADY_COMMITTED)

        # Still only one CombatPull after the failed second attempt.
        self.assertEqual(
            CombatPull.objects.filter(
                participant=data["participant"],
                round_number=data["encounter"].round_number,
            ).count(),
            1,
            "Only one CombatPull may exist per (participant, round).",
        )

    def test_round_declaration_without_combat_ctx_returns_none(self) -> None:
        """round_declaration with None context (non-combat) returns None for cast_pull."""
        action = _import_cast_action()
        data = _make_pull_setup()

        result = action.round_declaration(
            None,
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )
        self.assertIsNone(result, "Non-combat context must return None from round_declaration.")


def _import_cast_action():
    """Late import to avoid module-level coupling."""
    from actions.definitions.cast import CastTechniqueAction

    return CastTechniqueAction()
