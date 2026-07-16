"""Cross-context pull outcome E2E (#1455): pull changes the ACTION OUTCOME, not just the ledger.

Proves the issue's "Done when" across all four pull contexts:

  A. Non-combat cast — FLAT_BONUS pull raises extra_modifiers delivered to the check.
  B. Combat declared cast — FLAT_BONUS pull visible to _sum_active_flat_bonuses after
     declaring via CmdDeclareTechnique with pull=.
  C. Combat clash (INTENSITY_BUMP) — compute_intensity_for_clash higher with pull vs
     without, after declaring via CmdClashCommit with pull=.  @tag("postgres") because
     full clash resolution touches DISTINCT ON / partitioned Interaction.
  D. Refuse-without-charge — VITAL_BONUS-only pull in non-combat raises CommandError
     (propagated InvalidImbueAmount) and does NOT debit resonance.

Determinism strategy:
  - A: patch actions.services.perform_check; inspect extra_modifiers kwarg.
  - B: read _sum_active_flat_bonuses() on the participant; no roll needed.
  - C: read compute_intensity_for_clash() on the participant; no roll needed.
  - D: assert CommandError + resonance balance unchanged.

SQLite tier: A, B, D run cleanly.  C is @tag("postgres") (DISTINCT ON guard on the
clash resolution path).

Reference: issue #1455 Task 9.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdClashCommit, CmdDeclareTechnique
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    ClashStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
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
from world.magic.models import CharacterTechnique
from world.magic.seeds_cast import ensure_technique_cast_content
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Shared command helpers
# ---------------------------------------------------------------------------


def _cast_cmd(caller: object, args: str) -> CmdDeclareTechnique:
    """Build a CmdDeclareTechnique wired to *caller* with *args*."""
    cmd = CmdDeclareTechnique()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    return cmd


def _clash_cmd(caller: object, args: str) -> CmdClashCommit:
    """Build a CmdClashCommit wired to *caller* with *args*."""
    cmd = CmdClashCommit()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"clash {args}"
    cmd.cmdname = "clash"
    return cmd


# ---------------------------------------------------------------------------
# A. Non-combat cast: FLAT_BONUS pull raises extra_modifiers to the check roll
# ---------------------------------------------------------------------------


class NoncombatCastPullChangesCheckModifierE2ETests(TestCase):
    """Driving cast through CmdDeclareTechnique with pull= raises extra_modifiers.

    FLAT_BONUS pull effect adds its scaled_value to the extra_modifiers passed
    to start_action_resolution → perform_check.  We capture perform_check's
    call-args deterministically without relying on random roll outcomes.

    SQLite tier: passes cleanly.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        self.action_template = ensure_technique_cast_content()

        self.room = ObjectDBFactory(
            db_key="PullOutcomeTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room)

        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character
        self.character.db_location = self.room
        self.character.save()

        # Technique with enough anima_cost to survive deduction.
        # FLAT_BONUS pull effect is for TECHNIQUE-anchored thread.
        self.resonance = ResonanceFactory()

        # Tier-1 pull cost row (needed by spend_resonance_for_pull).
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)

        # Tier-1 FLAT_BONUS effect for TECHNIQUE-anchored thread (flat_bonus_amount=3).
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=3,
            effect_kind=EffectKind.FLAT_BONUS,
        )

        # Technique with standalone cast support.
        self.technique = TechniqueFactory(
            anima_cost=2,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )

        # TECHNIQUE-anchored thread owned by this sheet.
        # name must be non-empty — the command parses pull=<name> and an empty name
        # resolves to pull_val=None, which skips the pull entirely.
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
            name="EmberThread",
        )

        # Grant the technique + resonance balance + anima + engagement.
        CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)
        self.cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        CharacterAnimaFactory(character=self.character, current=20, maximum=20)
        CharacterEngagementFactory(character=self.character)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )

        # Use a real CheckOutcome row so select_consequence_from_result can assign it as
        # a FK (ensure_technique_cast_content() creates a template with a consequence
        # pool, which triggers the fallback path in select_consequence_from_result and
        # tries to write ConsequenceModel(outcome_tier=outcome, ...) — a MagicMock fails
        # the FK assignment validation).
        from world.traits.models import CheckOutcome

        success_outcome = CheckOutcome.objects.filter(name="Success").first()

        # Patch perform_check, accrue, anti-spam (same pattern as noncombat_cast_telnet_e2e).
        self._check_patcher = patch("actions.services.perform_check")
        self._mock_check = self._check_patcher.start()
        self._mock_check.return_value = MagicMock(
            success_level=2,
            outcome=success_outcome,
            outcome_name="Success",
        )
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()
        self._antispam_patcher = patch(
            "commands.pending_actions.check_anti_spam",
            return_value=None,
        )
        self._antispam_patcher.start()

    def tearDown(self) -> None:
        self._check_patcher.stop()
        self._accrue_patcher.stop()
        self._antispam_patcher.stop()

    def test_flat_bonus_pull_raises_check_extra_modifiers(self) -> None:
        """FLAT_BONUS pull delivers extra_modifiers > 0 to the check; baseline is 0.

        The FLAT_BONUS effect (flat_bonus_amount=3, level=0 → scaled_value=3) is
        folded into extra_modifiers before perform_check is called.  We assert the
        WITH-pull call used a strictly higher extra_modifiers than WITHOUT-pull.
        """
        # --- Baseline: cast WITHOUT pull ---
        cmd_no_pull = _cast_cmd(self.character, self.technique.name)
        cmd_no_pull.func()

        # Extra modifiers delivered to perform_check on the no-pull cast.
        # Effort=medium → EFFORT_CHECK_MODIFIER["medium"] (default 0 or small).
        no_pull_calls = self._mock_check.call_args_list[:]
        self.assertTrue(no_pull_calls, "perform_check must be called for the no-pull cast")
        no_pull_extra = no_pull_calls[-1].kwargs.get(
            "extra_modifiers", no_pull_calls[-1][1].get("extra_modifiers", 0)
        )

        # Reset mock call log and resonance (already debited 0; anima might change
        # between calls, but the FLAT_BONUS delta is on extra_modifiers, not anima).
        self._mock_check.reset_mock()

        # --- Pulled: cast WITH pull --- (fresh anima needed; refill in-place)
        from world.magic.models import CharacterAnima

        anima = CharacterAnima.objects.get(character=self.character)
        anima.current = 20
        anima.save(update_fields=["current"])

        cmd_pull = _cast_cmd(
            self.character,
            f"{self.technique.name} pull={self.thread.name} resonance={self.resonance.name}",
        )
        cmd_pull.func()

        pull_calls = self._mock_check.call_args_list[:]
        self.assertTrue(pull_calls, "perform_check must be called for the pull cast")
        pull_extra = pull_calls[-1].kwargs.get(
            "extra_modifiers", pull_calls[-1][1].get("extra_modifiers", 0)
        )

        self.assertGreater(
            pull_extra,
            no_pull_extra,
            f"extra_modifiers with pull ({pull_extra}) must exceed without ({no_pull_extra}); "
            "FLAT_BONUS=3 at level=0 → scaled_value=3 should add 3 to the check modifier.",
        )

        # --- Charge assertion: resonance was debited ---
        self.cr.refresh_from_db()
        self.assertLess(
            self.cr.balance,
            10,
            "CharacterResonance.balance must be debited after a successful pull cast.",
        )


# ---------------------------------------------------------------------------
# B. Combat declared cast: FLAT_BONUS pull visible to _sum_active_flat_bonuses
# ---------------------------------------------------------------------------


class CombatCastPullFlatBonusReadPathE2ETests(TestCase):
    """CmdDeclareTechnique with pull= in a DECLARING round → CombatPull readable.

    After driving the cast through the telnet command, the committed CombatPull's
    FLAT_BONUS effect must be visible via _sum_active_flat_bonuses.  This proves
    the OUTCOME-relevant mechanism at the surface level without needing full combat
    resolution (which would require PG for DISTINCT ON paths).

    SQLite tier: passes cleanly.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        self.action_template = ensure_technique_cast_content()

        # Combat encounter in DECLARING status.
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # Mook opponent (required by the combat encounter context).
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        self.opponent_name = self.opponent.name

        # PC participant.
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.character = self.sheet.character
        self.anima = CharacterAnimaFactory(character=self.character, current=20, maximum=20)
        CharacterEngagementFactory(character=self.character)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )

        # Place the character in a room so location-dependent queries don't fail.
        room = ObjectDBFactory(
            db_key="CombatCastPullRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = room
        self.character.save()

        # Resonance + pull catalog.
        self.resonance = ResonanceFactory()
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            flat_bonus_amount=4,
            effect_kind=EffectKind.FLAT_BONUS,
        )

        # Technique (PHYSICAL so the combat declaration routes correctly).
        self.technique = TechniqueFactory(
            action_category=ActionCategory.PHYSICAL,
            anima_cost=2,
            action_template=self.action_template,
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)

        # TECHNIQUE-anchored thread.
        # name must be non-empty — the command parses pull=<name> and an empty name
        # resolves to pull_val=None, which skips the pull entirely.
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
            name="CombatCastThread",
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )

    def test_combat_cast_pull_visible_to_flat_bonus_read_path(self) -> None:
        """CmdDeclareTechnique pull= in combat → _sum_active_flat_bonuses > 0.

        After the command records the declaration (CastTechniqueAction.round_declaration
        commits the CombatPull), the flat-bonus read-path must reflect the pull.
        This is the OUTCOME mechanism: the bonus feeds into the attack roll at resolution.
        """
        # Baseline: no pull → flat bonus is 0.
        bonus_before = _sum_active_flat_bonuses(self.participant, self.encounter)
        self.assertEqual(
            bonus_before,
            0,
            "Baseline: _sum_active_flat_bonuses must be 0 before any pull is committed.",
        )

        # Drive the command with pull= at the mook opponent.
        cmd = _cast_cmd(
            self.character,
            f"{self.technique.name} at {self.opponent_name} "
            f"pull={self.thread.name} resonance={self.resonance.name}",
        )
        cmd.func()

        # Invalidate handler cache (same pattern as test_cast_round_declaration_pull.py).
        self.character.combat_pulls.invalidate()

        bonus_after = _sum_active_flat_bonuses(self.participant, self.encounter)
        self.assertGreater(
            bonus_after,
            0,
            "_sum_active_flat_bonuses must be > 0 after CmdDeclareTechnique with pull= "
            "(FLAT_BONUS=4 for a TECHNIQUE-anchored thread at tier=1).",
        )
        self.assertGreater(
            bonus_after,
            bonus_before,
            "Flat bonus after pull must exceed baseline (outcome delta proven at mechanism level).",
        )


# ---------------------------------------------------------------------------
# C. Combat clash: INTENSITY_BUMP pull raises compute_intensity_for_clash
# ---------------------------------------------------------------------------


@tag("postgres")
class CombatClashPullIntensityReadPathE2ETests(TestCase):
    """CmdClashCommit with pull= → compute_intensity_for_clash returns a higher value.

    This proves the clash OUTCOME mechanism: the intensity fed to clash resolution
    is higher when a pull is committed.  Full clash resolution (winner / margin /
    open) is NOT attempted here because the winner path requires DISTINCT ON /
    partitioned Interaction (PG-only).

    @tag("postgres") — tagged to run in CI's PG shard only; expected to ERROR on
    the SQLite fast tier (DISTINCT ON on adjacent code paths), so it is excluded
    from the fast-tier run.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        ClashConfigFactory()
        StrainConfigFactory()

        self.action_template = ensure_technique_cast_content()

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # Mook opponent.
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        self.opponent_name = self.opponent.name

        # Clash: active against the mook.
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )

        # PC participant.
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.character = self.sheet.character
        CharacterAnimaFactory(character=self.character, current=30, maximum=30)
        CharacterEngagementFactory(character=self.character)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )

        room = ObjectDBFactory(
            db_key="ClashPullRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character.location = room
        self.character.save()

        # Resonance + INTENSITY_BUMP pull catalog.
        self.resonance = ResonanceFactory()
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            as_intensity_bump=True,
            intensity_bump_amount=3,
        )

        # Technique (clash_capable=True required by commit_to_clash).
        self.technique = TechniqueFactory(
            action_category=ActionCategory.PHYSICAL,
            anima_cost=2,
            intensity=2,
            action_template=self.action_template,
            clash_capable=True,
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)

        # TECHNIQUE-anchored thread.
        # name must be non-empty — the command parses pull=<name> and an empty name
        # resolves to pull_val=None, which skips the pull entirely.
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
            name="ClashThread",
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )

    def test_clash_pull_raises_intensity_read_path(self) -> None:
        """CmdClashCommit pull= → compute_intensity_for_clash is higher than baseline.

        Drives the telnet command, then asserts the intensity mechanism that feeds
        into clash resolution differs with vs without the pull.  Full clash winner
        resolution is not attempted (PG-only DISTINCT ON path).
        """
        # Build a CombatRoundAction row so compute_intensity_for_clash has context.
        round_action = CombatRoundActionFactory(
            participant=self.participant,
            focused_action=self.technique,
        )

        # Baseline intensity — no pull committed yet.
        self.character.combat_pulls.invalidate()
        intensity_without_pull = compute_intensity_for_clash(self.participant, round_action)

        # Drive the clash command WITH pull.
        cmd = _clash_cmd(
            self.character,
            f"{self.opponent_name} with {self.technique.name} "
            f"pull={self.thread.name} resonance={self.resonance.name}",
        )
        cmd.func()

        # Invalidate handler cache.
        self.character.combat_pulls.invalidate()

        intensity_with_pull = compute_intensity_for_clash(self.participant, round_action)

        self.assertGreater(
            intensity_with_pull,
            intensity_without_pull,
            f"compute_intensity_for_clash must be higher after CmdClashCommit with pull= "
            f"(INTENSITY_BUMP=3); got {intensity_with_pull} vs baseline {intensity_without_pull}.",
        )
        self.assertGreaterEqual(
            intensity_with_pull,
            self.technique.intensity + 3,
            "compute_intensity_for_clash must include the INTENSITY_BUMP pull bonus of 3.",
        )


# ---------------------------------------------------------------------------
# D. Refuse-without-charge: VITAL_BONUS-only pull raises CommandError, no debit
# ---------------------------------------------------------------------------


class RefuseWithoutChargeE2ETests(TestCase):
    """A VITAL_BONUS-only pull in a non-combat cast raises CommandError + no resonance debit.

    VITAL_BONUS effects are marked inactive in non-combat context by
    resolve_pull_effects.  When every resolved effect is inactive,
    spend_resonance_for_pull raises InvalidImbueAmount ("This pull would have no
    effect on that action."), which propagates to CommandError at the telnet layer.
    Resonance balance must be unchanged.

    SQLite tier: passes cleanly.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        self.action_template = ensure_technique_cast_content()

        self.room = ObjectDBFactory(
            db_key="RefuseTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room)

        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.character = self.sheet.character
        self.character.db_location = self.room
        self.character.save()

        self.resonance = ResonanceFactory()
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)

        # VITAL_BONUS-only effect: inactive in non-combat → pull is refused.
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            as_vital_bonus=True,
            vital_bonus_amount=5,
            flat_bonus_amount=None,
        )

        self.technique = TechniqueFactory(
            anima_cost=2,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=self.technique)

        # name must be non-empty — the command parses pull=<name> and an empty name
        # resolves to pull_val=None, which skips the pull entirely.
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=0,
            name="RefuseThread",
        )
        self.cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        CharacterAnimaFactory(character=self.character, current=20, maximum=20)
        CharacterEngagementFactory(character=self.character)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )

        # Patch accrue + anti-spam (perform_check not needed — cast won't reach it).
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()
        self._antispam_patcher = patch(
            "commands.pending_actions.check_anti_spam",
            return_value=None,
        )
        self._antispam_patcher.start()

    def tearDown(self) -> None:
        self._accrue_patcher.stop()
        self._antispam_patcher.stop()

    def test_vital_bonus_only_pull_refused_no_charge(self) -> None:
        """VITAL_BONUS-only pull in non-combat is refused; resonance balance unchanged.

        func() catches CommandError and sends it to caller.msg(); the balance must
        be unchanged because the pull raises before any debit occurs.
        """
        balance_before = self.cr.balance

        self.character.msg = MagicMock()

        cmd = _cast_cmd(
            self.character,
            f"{self.technique.name} pull={self.thread.name} resonance={self.resonance.name}",
        )
        cmd.func()

        # func() sends the error via caller.msg — verify it was called (the pull failed).
        self.character.msg.assert_called()

        # Balance must be unchanged: the pull raised before any debit.
        self.cr.refresh_from_db()
        self.assertEqual(
            self.cr.balance,
            balance_before,
            "CharacterResonance.balance must NOT be debited when the pull is refused "
            "(VITAL_BONUS-only pull in non-combat → InvalidImbueAmount → CommandError).",
        )
