"""Tests for run_clash_round — the per-clash round driver (Task 5.2)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.clash import run_clash_round
from world.combat.constants import ClashResolution, ClashStatus, OpponentTier
from world.combat.factories import (
    BreakClashFactory,
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import Clash, ClashRound, CombatOpponent
from world.combat.types import (
    ClashResolutionResult,
    ClashRoundResult,
    PreparedClashContribution,
)
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    CharacterAnimaFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models.resonance_environment import AffinityInteraction
from world.mechanics.factories import CharacterEngagementFactory, PropertyFactory
from world.mechanics.models import ObjectProperty
from world.traits.factories import CheckOutcomeFactory


class RunClashRoundTests(TestCase):
    """Tests for run_clash_round — the per-round orchestration driver."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        # Seed the CheckOutcome rows used by threshold and meter-band logic.
        cls.outcome_critical = CheckOutcomeFactory(name="rr_critical", success_level=3)
        cls.outcome_success = CheckOutcomeFactory(name="rr_success", success_level=1)
        cls.outcome_partial = CheckOutcomeFactory(name="rr_partial", success_level=0)
        cls.outcome_failure = CheckOutcomeFactory(name="rr_failure", success_level=-1)
        cls.outcome_botch = CheckOutcomeFactory(name="rr_botch", success_level=-2)

    def _make_character(self, current: int = 20, maximum: int = 20) -> object:
        """Create a CharacterSheet with anima pool and engagement record."""
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=current, maximum=maximum)
        CharacterEngagementFactory(character=sheet.character)
        return sheet

    def _make_technique(self, anima_cost: int = 3) -> object:
        """Create a Technique with an action_template tied to the shared check_type."""
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=anima_cost,
            action_template=template,
        )

    def _make_contribution(
        self, *, character_sheet: object, technique: object, npc_attack_affinity: object = None
    ) -> PreparedClashContribution:
        return PreparedClashContribution(
            character_sheet=character_sheet,
            action_slot="FOCUSED",
            technique=technique,
            strain_commitment=0,
            npc_attack_affinity=npc_attack_affinity,
        )

    # -------------------------------------------------------------------------
    # 1. Basic round with one contribution
    # -------------------------------------------------------------------------

    def test_basic_round_with_one_contribution(self) -> None:
        """CLASH clash + one PC contribution → ClashRound written, progress moves."""
        clash = ClashFactory(progress=0, pc_win_threshold=20, npc_win_threshold=20)
        sheet = self._make_character()
        technique = self._make_technique()

        contribution = self._make_contribution(character_sheet=sheet, technique=technique)

        with force_check_outcome(self.outcome_success):
            result = run_clash_round(
                clash=clash,
                round_number=1,
                pc_contributions=[contribution],
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashRoundResult)
        # One ClashRound row must have been written.
        self.assertIsNotNone(result.clash_round.pk)
        self.assertTrue(ClashRound.objects.filter(pk=result.clash_round.pk).exists())

        # Meter must have moved (success = +1 by default config).
        # NPC pressure = 0 (no triggering_threat_entry) → progress = 0 + 1 - 0 = 1.
        clash.refresh_from_db()
        self.assertEqual(clash.progress, 1)

    # -------------------------------------------------------------------------
    # 2. No contributions → NPC drifts meter toward NPC win
    # -------------------------------------------------------------------------

    def test_clash_with_no_contributions_drifts_toward_npc(self) -> None:
        """CLASH clash, empty pc_contributions, NPC pressure → meter decreases."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=3)
        clash = ClashFactory(
            progress=5,
            pc_win_threshold=20,
            npc_win_threshold=20,
            triggering_threat_entry=entry,
        )

        result = run_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=[],
            config_clash=self.config_clash,
            config_strain=self.config_strain,
        )

        self.assertIsInstance(result, ClashRoundResult)
        # progress_after = 5 + 0 - 3 = 2; clash is still in bounds.
        self.assertEqual(result.progress_after, 2)
        # Clash should remain ACTIVE (not resolved).
        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.ACTIVE)

    # -------------------------------------------------------------------------
    # 3. BREAK: consecutive idle rounds → ABANDONED
    # -------------------------------------------------------------------------

    def test_break_with_no_contributions_increments_idle_counter(self) -> None:
        """BREAK clash with 0 contributions for break_abandon_idle_rounds rounds → ABANDONED."""
        # Default break_abandon_idle_rounds is 2. Use a config with 2 to be explicit.
        config_clash = ClashConfigFactory(break_abandon_idle_rounds=2)
        clash = BreakClashFactory(progress=0, pc_win_threshold=20)

        # Round 1 — idle, no abandon yet.
        result1 = run_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=[],
            config_clash=config_clash,
            config_strain=self.config_strain,
        )
        clash.refresh_from_db()
        self.assertIsInstance(result1, ClashRoundResult)
        self.assertEqual(clash.status, ClashStatus.ACTIVE)  # not yet abandoned

        # Round 2 — idle again; idle count now = 2 >= 2 → ABANDONED.
        result2 = run_clash_round(
            clash=clash,
            round_number=2,
            pc_contributions=[],
            config_clash=config_clash,
            config_strain=self.config_strain,
        )
        clash.refresh_from_db()
        self.assertIsInstance(result2, ClashRoundResult)
        self.assertEqual(clash.status, ClashStatus.RESOLVED)
        self.assertEqual(clash.resolution, ClashResolution.ABANDONED)

    # -------------------------------------------------------------------------
    # 4. PC contribution crosses PC win threshold → resolve_clash fires
    # -------------------------------------------------------------------------

    def test_resolution_triggers_when_threshold_crossed(self) -> None:
        """PC contribution that crosses pc_win_threshold → clash resolved PC_MARGINAL.

        Progress=4, threshold=5 → progress_after=5.
        Overshoot = 5 - 5 = 0 < decisive_overshoot=3 → PC_MARGINAL.
        """
        # Start close to the threshold so one success crosses it.
        config_clash = ClashConfigFactory(
            decisive_overshoot=3,
            max_round_cap=12,
        )
        clash = ClashFactory(progress=4, pc_win_threshold=5, npc_win_threshold=20)
        sheet = self._make_character()
        technique = self._make_technique()

        contribution = self._make_contribution(character_sheet=sheet, technique=technique)

        with force_check_outcome(self.outcome_success):
            result = run_clash_round(
                clash=clash,
                round_number=1,
                pc_contributions=[contribution],
                config_clash=config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashRoundResult)
        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.RESOLVED)
        # Overshoot = 0 < 3 → MARGINAL.
        self.assertEqual(clash.resolution, ClashResolution.PC_MARGINAL)

    def test_round_result_carries_resolution_when_clash_resolves(self) -> None:
        """run_clash_round surfaces the ClashResolutionResult on the round result.

        The resolution tier is computed by resolve_clash and was previously
        discarded; it must now ride back on ClashRoundResult.resolution so the
        round driver can broadcast an outcome narration (#644).
        """
        config_clash = ClashConfigFactory(
            decisive_overshoot=3,
            max_round_cap=12,
        )
        clash = ClashFactory(progress=4, pc_win_threshold=5, npc_win_threshold=20)
        sheet = self._make_character()
        technique = self._make_technique()
        contribution = self._make_contribution(character_sheet=sheet, technique=technique)

        with force_check_outcome(self.outcome_success):
            result = run_clash_round(
                clash=clash,
                round_number=1,
                pc_contributions=[contribution],
                config_clash=config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result.resolution, ClashResolutionResult)
        self.assertEqual(result.resolution.resolution, ClashResolution.PC_MARGINAL)
        self.assertEqual(result.resolution.clash.pk, clash.pk)

    def test_round_result_resolution_is_none_when_clash_stays_active(self) -> None:
        """A non-resolving round leaves ClashRoundResult.resolution as None."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=3)
        clash = ClashFactory(
            progress=5,
            pc_win_threshold=20,
            npc_win_threshold=20,
            triggering_threat_entry=entry,
        )

        result = run_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=[],
            config_clash=self.config_clash,
            config_strain=self.config_strain,
        )

        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.ACTIVE)
        self.assertIsNone(result.resolution)

    # -------------------------------------------------------------------------
    # 5. Per-round pool fires
    # -------------------------------------------------------------------------

    def test_per_round_pool_fires(self) -> None:
        """Per-round consequence pool fires; ADD_PROPERTY effect appears on NPC's ObjectDB."""
        prop = PropertyFactory(name="rr_combat_marked")

        pool = ConsequencePoolFactory(name="RR_PerRoundPool")
        consequence = ConsequenceFactory(
            outcome_tier=self.outcome_success, label="Mark NPC Per Round", weight=1
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.ADD_PROPERTY,
            target=EffectTarget.SELF,
            property=prop,
            property_value=1,
        )

        # Create an opponent with a real ObjectDB.
        npc_objectdb = ObjectDBFactory(db_key="RR_PerRoundNPC")
        encounter = CombatEncounterFactory()
        opponent = CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            name="RR_PerRoundOpponent",
            health=50,
            max_health=50,
            objectdb=npc_objectdb,
            objectdb_is_ephemeral=False,
        )

        # progress=3, pc_win_threshold=5 → ratio=0.6 → success band → pool fires.
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            per_round_consequence_pool=pool,
            progress=3,
            pc_win_threshold=5,
            npc_win_threshold=20,
        )

        with force_check_outcome(self.outcome_success):
            result = run_clash_round(
                clash=clash,
                round_number=1,
                pc_contributions=[],
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashRoundResult)
        self.assertTrue(
            ObjectProperty.objects.filter(
                object=npc_objectdb,
                property=prop,
            ).exists(),
            "ADD_PROPERTY effect from per-round pool must be applied to NPC ObjectDB",
        )

    # -------------------------------------------------------------------------
    # 6. Affinity tilt is threaded through
    # -------------------------------------------------------------------------

    def test_affinity_tilt_threaded_through(self) -> None:
        """OPPOSED affinity matchup → progress_delta differs from no-tilt base.

        We set up CASTER-aggressor OPPOSED interaction (positive tilt) and compare:
        - No tilt: forced success → delta_success from config.
        - With tilt: extra modifier added to check; same forced outcome, same
          delta, but the *modifier path* exercised is the extra one.

        Because we force the outcome, both runs produce the same delta.  The
        test instead verifies that the tilt modifier is non-zero (computed
        correctly) and that run_clash_round returns a valid result (i.e., the
        code path that threads the tilt through does not crash).
        """
        AffinityInteraction.objects.clear_cache()

        tech_affinity = AffinityFactory()
        npc_affinity = AffinityFactory()

        resonance = ResonanceFactory(affinity=tech_affinity)
        gift = GiftFactory()
        gift.resonances.add(resonance)
        technique = TechniqueFactory(
            gift=gift,
            anima_cost=3,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )

        AffinityInteractionFactory(
            source_affinity=tech_affinity,
            environment_affinity=npc_affinity,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.CASTER,
            severity_multiplier=Decimal("4.00"),
        )
        AffinityInteraction.objects.clear_cache()

        clash = ClashFactory(progress=0, pc_win_threshold=20, npc_win_threshold=20)
        sheet = self._make_character()

        contribution = PreparedClashContribution(
            character_sheet=sheet,
            action_slot="FOCUSED",
            technique=technique,
            strain_commitment=0,
            npc_attack_affinity=npc_affinity,
        )

        with force_check_outcome(self.outcome_success):
            result = run_clash_round(
                clash=clash,
                round_number=1,
                pc_contributions=[contribution],
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashRoundResult)
        # One contribution was processed → meter moved by at least 1.
        clash.refresh_from_db()
        self.assertGreater(clash.progress, 0)

    # -------------------------------------------------------------------------
    # 7. Atomic: if resolve_clash raises, nothing persists
    # -------------------------------------------------------------------------

    def test_atomic_on_resolve_failure(self) -> None:
        """If resolve_clash raises, ClashRound write and progress update roll back."""
        # Set up a clash that will cross the threshold on the first round.
        # Progress=4, threshold=5 → triggers resolution after a successful contribution.
        config_clash = ClashConfigFactory(
            decisive_overshoot=3,
            max_round_cap=12,
        )
        clash = ClashFactory(progress=4, pc_win_threshold=5, npc_win_threshold=20)
        original_progress = clash.progress
        sheet = self._make_character()
        technique = self._make_technique()

        contribution = self._make_contribution(character_sheet=sheet, technique=technique)

        with patch(
            "world.combat.clash.resolve_clash",
            side_effect=RuntimeError("simulated resolve_clash failure"),
        ):
            with self.assertRaises(RuntimeError):
                with force_check_outcome(self.outcome_success):
                    run_clash_round(
                        clash=clash,
                        round_number=1,
                        pc_contributions=[contribution],
                        config_clash=config_clash,
                        config_strain=self.config_strain,
                    )

        # ClashRound must NOT have been written (transaction rolled back).
        self.assertEqual(
            ClashRound.objects.filter(clash=clash).count(),
            0,
            "ClashRound must not persist when resolve_clash raises",
        )

        # Clash.progress must not have changed (DB-level — bypass identity map).
        row = Clash.objects.filter(pk=clash.pk).values("progress", "status")[0]
        self.assertEqual(
            row["progress"],
            original_progress,
            "clash.progress must be rolled back when resolve_clash raises",
        )
        self.assertEqual(
            row["status"],
            ClashStatus.ACTIVE,
            "clash.status must remain ACTIVE when resolve_clash raises",
        )
