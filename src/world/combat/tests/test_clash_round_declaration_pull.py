"""TDD tests for Task 5 (#1455): clash declaration with a thread pull.

When a player declares a clash contribution WITH a ``cast_pull``
(``CastPullDeclaration`` passed via ``_dispatch_clash_contribution``), the system
must:

1. Commit the pull immediately at declaration time via
   ``world.combat.pull_helpers.commit_combat_pull`` so the combat read-path
   (``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``) sees the
   ``CombatPull`` row during round resolution.
2. Enforce the one-pull-per-round cap: a player who already pulled on a cast
   this round cannot also pull on a clash — the second call must raise
   ``ActionDispatchError(PULL_ALREADY_COMMITTED)``.
3. Raise ``CommandError`` on the telnet side when ``pull=`` is given without
   ``resonance=`` (``CmdClashCommit._parse_args`` validation).

SQLite tier limits:
- The full clash-WINNER-differs resolution E2E may need Postgres (DISTINCT ON /
  partitioned Interaction).  On the SQLite fast tier we assert the MECHANISM:
    * the pull is committed as a ``CombatPull`` row,
    * ``compute_intensity_for_clash`` returns a HIGHER value with the pull vs without,
    * ``_sum_active_flat_bonuses`` returns the flat bonus.
- @tag("postgres") tests for full clash-result-differs resolution are deferred to
  Task 7.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatPull
from world.combat.pull_helpers import commit_combat_pull
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


def _make_clash_pull_setup(
    *,
    effect_kind: str = EffectKind.FLAT_BONUS,
    tier: int = 1,
    flat_bonus_amount: int = 3,
    intensity_bump_amount: int | None = None,
) -> dict:
    """Build a full pull-enabled combat scene for clash tests.

    Mirrors ``_make_pull_setup`` from ``test_cast_round_declaration_pull.py``.

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

    # Anima (seed positive value; n=1 thread → anima cost = 0 at default config,
    # but we provide current > 0 so future multi-thread tests can reuse this).
    CharacterAnimaFactory(
        character=sheet.character,
        current=10,
        maximum=20,
    )

    # Per-tier pull cost catalogue row.
    ThreadPullCostFactory(tier=tier, resonance_cost=1, anima_per_thread=0)

    # Authored effect — must yield at least one non-inactive resolved effect for
    # spend_resonance_for_pull to proceed (it raises InvalidImbueAmount otherwise).
    if effect_kind == EffectKind.INTENSITY_BUMP:
        ThreadPullEffectFactory(
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            tier=tier,
            min_thread_level=0,
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=intensity_bump_amount if intensity_bump_amount else 2,
            flat_bonus_amount=None,
        )
    else:
        ThreadPullEffectFactory(
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
        "encounter": encounter,
        "participant": participant,
        "ctx": ctx,
        "pull_decl": pull_decl,
    }


class ClashRoundDeclarationPullTests(TestCase):
    """commit_combat_pull called via _dispatch_clash_contribution path."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_clash_pull_creates_combat_pull_row(self) -> None:
        """Committing a pull via clash path persists a CombatPull for (participant, round)."""
        data = _make_clash_pull_setup()

        commit_combat_pull(
            cast_pull=data["pull_decl"],
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        pull_qs = CombatPull.objects.filter(
            participant=data["participant"],
            round_number=data["encounter"].round_number,
        )
        self.assertTrue(
            pull_qs.exists(),
            "A CombatPull row must be created when a clash carries a pull.",
        )
        pull = pull_qs.get()
        self.assertEqual(pull.resonance, data["resonance"])
        self.assertEqual(pull.tier, 1)
        self.assertIn(data["thread"], pull.threads.all())

    def test_clash_pull_debits_resonance(self) -> None:
        """Resonance balance decreases after a combat clash pull."""
        from world.magic.models import CharacterResonance

        data = _make_clash_pull_setup()
        cr_before = CharacterResonance.objects.get(
            character_sheet=data["sheet"],
            resonance=data["resonance"],
        )
        balance_before = cr_before.balance

        commit_combat_pull(
            cast_pull=data["pull_decl"],
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        cr_before.refresh_from_db()
        self.assertLess(
            cr_before.balance,
            balance_before,
            "Resonance balance must decrease after a combat clash pull.",
        )

    def test_clash_pull_visible_to_flat_bonus_read_path(self) -> None:
        """_sum_active_flat_bonuses reflects the CombatPull committed via the clash path."""
        data = _make_clash_pull_setup(effect_kind=EffectKind.FLAT_BONUS, flat_bonus_amount=3)

        commit_combat_pull(
            cast_pull=data["pull_decl"],
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        # Invalidate handler cache so the next read reflects the new DB row.
        data["sheet"].character.combat_pulls.invalidate()

        bonus = _sum_active_flat_bonuses(data["participant"], data["encounter"])
        self.assertGreater(
            bonus,
            0,
            "_sum_active_flat_bonuses must return > 0 after a FLAT_BONUS pull via clash.",
        )

    def test_clash_pull_visible_to_intensity_read_path(self) -> None:
        """compute_intensity_for_clash returns a higher value with the pull committed via clash."""
        data = _make_clash_pull_setup(
            effect_kind=EffectKind.INTENSITY_BUMP, intensity_bump_amount=2
        )

        # Build a CombatRoundAction so compute_intensity_for_clash has something to work with.
        round_action = CombatRoundActionFactory(
            participant=data["participant"],
            focused_action=data["technique"],
        )

        # Baseline — no pull yet.
        data["sheet"].character.combat_pulls.invalidate()
        intensity_without_pull = compute_intensity_for_clash(data["participant"], round_action)

        # Commit the pull.
        commit_combat_pull(
            cast_pull=data["pull_decl"],
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        # Invalidate handler cache.
        data["sheet"].character.combat_pulls.invalidate()

        intensity_with_pull = compute_intensity_for_clash(data["participant"], round_action)
        self.assertGreater(
            intensity_with_pull,
            intensity_without_pull,
            "compute_intensity_for_clash must be higher after a clash pull commits INTENSITY_BUMP.",
        )
        # Specifically, the pull should add 2 (the authored intensity_bump_amount).
        self.assertGreaterEqual(
            intensity_with_pull,
            data["technique"].intensity + 2,
            "compute_intensity_for_clash must include the INTENSITY_BUMP pull bonus.",
        )

    def test_second_pull_same_round_fails_with_already_committed(self) -> None:
        """A second pull in the same round — whether cast or clash — fails cleanly.

        This simulates: player pulled on a cast this round, then tries to pull on
        a clash too.  The (participant, round_number) unique constraint on CombatPull
        must surface as ActionDispatchError(PULL_ALREADY_COMMITTED).
        """
        from actions.errors import ActionDispatchError

        data = _make_clash_pull_setup()

        # First pull: succeeds (simulates a cast pull earlier in the round).
        commit_combat_pull(
            cast_pull=data["pull_decl"],
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )
        self.assertEqual(
            CombatPull.objects.filter(
                participant=data["participant"],
                round_number=data["encounter"].round_number,
            ).count(),
            1,
            "First pull must succeed and create exactly one CombatPull.",
        )

        # Second pull in the same round: must raise PULL_ALREADY_COMMITTED.
        with self.assertRaises(ActionDispatchError) as cm:
            commit_combat_pull(
                cast_pull=data["pull_decl"],
                participant=data["participant"],
                encounter=data["encounter"],
                technique_id=data["technique"].pk,
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


class CmdClashCommitPullParsingTests(TestCase):
    """CmdClashCommit._parse_args validates pull= / resonance= interaction."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_pull_without_resonance_raises_command_error(self) -> None:
        """pull= without resonance= must raise CommandError immediately in _parse_args."""
        from unittest.mock import MagicMock

        from commands.combat import CmdClashCommit
        from commands.exceptions import CommandError

        cmd = CmdClashCommit.__new__(CmdClashCommit)
        # Minimal caller mock — _parse_args does not call .caller for this error path.
        cmd.caller = MagicMock()
        cmd.args = "Goblin with Fireball pull=EmberStrand"
        cmd._parsed = False

        with self.assertRaises(CommandError) as cm:
            cmd._parse_args()
        self.assertIn("resonance=", str(cm.exception))

    def test_pull_with_resonance_sets_parsed_state(self) -> None:
        """pull= with resonance= must populate _pull_thread_str and _pull_resonance_str."""
        from unittest.mock import MagicMock

        from commands.combat import CmdClashCommit

        cmd = CmdClashCommit.__new__(CmdClashCommit)
        cmd.caller = MagicMock()
        cmd.args = "Goblin with Fireball pull=EmberStrand resonance=Flame"
        cmd._parsed = False

        # _parse_args does not query DB for pull validation — it only tokenises.
        # The DB-backed resolution happens in _resolve_cast_pull (called from
        # resolve_action_args).  So _parse_args should succeed here.
        cmd._parse_args()

        self.assertEqual(cmd._pull_thread_str, "EmberStrand")
        self.assertEqual(cmd._pull_resonance_str, "Flame")
        self.assertEqual(cmd._pull_tier, 1)

    def test_parse_no_pull_sets_none(self) -> None:
        """Absence of pull= leaves _pull_thread_str as None."""
        from unittest.mock import MagicMock

        from commands.combat import CmdClashCommit

        cmd = CmdClashCommit.__new__(CmdClashCommit)
        cmd.caller = MagicMock()
        cmd.args = "Goblin with Fireball strain=3"
        cmd._parsed = False

        cmd._parse_args()

        self.assertIsNone(cmd._pull_thread_str)
        self.assertIsNone(cmd._pull_resonance_str)
        self.assertEqual(cmd._pull_tier, 1)
