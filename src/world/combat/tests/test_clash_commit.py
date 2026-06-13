"""Tests for commit_to_clash — the per-round clash contribution pipeline."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.clash import commit_to_clash, outcome_to_delta
from world.combat.factories import ClashConfigFactory, ClashFactory, StrainConfigFactory
from world.combat.types import ClashContributionResult
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import CharacterAnimaFactory, SoulfrayConfigFactory, TechniqueFactory
from world.mechanics.factories import CharacterEngagementFactory
from world.traits.factories import CheckOutcomeFactory


class CommitToClashTests(TestCase):
    """Tests for commit_to_clash routing a PC contribution through use_technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="commit_success", success_level=1)
        cls.clash = ClashFactory()

    def _make_character_with_anima(self, current: int = 20, maximum: int = 20) -> tuple:
        """Create a character with a CharacterAnima pool and engagement record.

        Returns (CharacterSheet, anima).  commit_to_clash now takes a CharacterSheet;
        the ObjectDB is resolved internally via CharacterSheet.character.

        CharacterSheetFactory creates the ObjectDB (CharacterFactory) and
        CharacterSheet together.  We then attach an anima pool and engagement
        record to the same ObjectDB.
        """
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=current, maximum=maximum)
        # CharacterEngagementFactory expects an ObjectDB.
        CharacterEngagementFactory(character=sheet.character)
        return sheet, anima

    def _make_technique_with_template(
        self, intensity: int = 5, control: int = 10, anima_cost: int = 3
    ) -> object:
        """Create a Technique that has an action_template with a known check_type."""
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(
            intensity=intensity,
            control=control,
            anima_cost=anima_cost,
            action_template=template,
        )

    # -------------------------------------------------------------------------
    # 1. Basic commit returns a valid ClashContributionResult
    # -------------------------------------------------------------------------

    def test_basic_commit_writes_contribution_result(self) -> None:
        """Zero strain commitment + plenty of anima → valid ClashContributionResult."""
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertIsNotNone(result.check_outcome)
        self.assertEqual(result.anima_committed, 0)
        self.assertFalse(result.was_overburn)
        expected_delta = outcome_to_delta(
            check_outcome=self.success_outcome,
            power=result.power,
            config=self.config_clash,
        )
        self.assertEqual(result.progress_delta, expected_delta)
        self.assertIsNotNone(result.technique_use_result)

    # -------------------------------------------------------------------------
    # 2. Strain routes to power (not check modifier)
    # -------------------------------------------------------------------------

    def test_strain_anima_recorded_on_result(self) -> None:
        """A positive strain commitment must be recorded on result.anima_committed.

        Strain no longer raises the check modifier — it feeds power_intensity_bonus
        so higher strain → higher power → higher progress_delta on a success.
        """
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        strain_n = 10

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=strain_n,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertEqual(result.anima_committed, strain_n)
        # The technique_use_result.anima_cost.effective_cost must reflect the strain on top
        effective_cost = result.technique_use_result.anima_cost.effective_cost
        # effective_cost >= strain_n (strain adds ON TOP of floor-0)
        self.assertGreaterEqual(effective_cost, strain_n)

    def test_higher_strain_yields_higher_power(self) -> None:
        """Strain feeds power via power_intensity_bonus, so a higher strain_commitment
        must produce a higher result.power on identical forced outcomes."""
        character_sheet_lo, _anima_lo = self._make_character_with_anima(current=20, maximum=20)
        technique_lo = self._make_technique_with_template(anima_cost=3)

        character_sheet_hi, _anima_hi = self._make_character_with_anima(current=20, maximum=20)
        technique_hi = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result_lo = commit_to_clash(
                character_sheet=character_sheet_lo,
                technique=technique_lo,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        with force_check_outcome(self.success_outcome):
            result_hi = commit_to_clash(
                character_sheet=character_sheet_hi,
                technique=technique_hi,
                clash=self.clash,
                strain_commitment=10,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertGreater(
            result_hi.power,
            result_lo.power,
            "Higher strain_commitment must yield higher power (via power_intensity_bonus)",
        )

    # -------------------------------------------------------------------------
    # 2b. Check breakdown has NO Strain source; affinity tilt still threaded
    # -------------------------------------------------------------------------

    def test_strain_not_in_check_breakdown(self) -> None:
        """Strain must NOT appear as a 'Strain' ModifierContribution in the check
        breakdown — it has been moved to power_intensity_bonus instead."""
        from unittest.mock import patch

        from world.checks import services as checks_services
        from world.checks.constants import ModifierSourceKind

        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        captured: dict = {}
        real_collect = checks_services.collect_check_modifiers

        def _spy_collect(sheet, check_type, **kwargs):
            breakdown = real_collect(sheet, check_type, **kwargs)
            captured["extra_contributions"] = kwargs.get("extra_contributions") or []
            return breakdown

        with (
            force_check_outcome(self.success_outcome),
            patch(
                "world.checks.services.collect_check_modifiers",
                side_effect=_spy_collect,
            ),
        ):
            commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=10,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        # No STRAIN-kind contribution with source_label "Strain" must appear.
        extras = captured["extra_contributions"]
        strain_contribs = [
            c
            for c in extras
            if c.source_kind == ModifierSourceKind.STRAIN and c.source_label == "Strain"
        ]
        self.assertEqual(
            len(strain_contribs),
            0,
            "Strain must not appear in the check breakdown — it feeds power now",
        )

    def test_affinity_tilt_still_routed_to_check(self) -> None:
        """check_modifier_extra (affinity tilt) must still appear as a ModifierContribution
        in the check breakdown even after strain is removed from the check."""
        from unittest.mock import patch

        from world.checks import services as checks_services
        from world.checks.constants import ModifierSourceKind

        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        captured: dict = {}
        real_collect = checks_services.collect_check_modifiers

        def _spy_collect(sheet, check_type, **kwargs):
            breakdown = real_collect(sheet, check_type, **kwargs)
            captured["extra_contributions"] = kwargs.get("extra_contributions") or []
            return breakdown

        with (
            force_check_outcome(self.success_outcome),
            patch(
                "world.checks.services.collect_check_modifiers",
                side_effect=_spy_collect,
            ),
        ):
            commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
                check_modifier_extra=5,
            )

        extras = captured["extra_contributions"]
        affinity_contribs = [
            c
            for c in extras
            if c.source_kind == ModifierSourceKind.STRAIN and c.source_label == "Affinity tilt"
        ]
        self.assertEqual(len(affinity_contribs), 1)
        self.assertEqual(affinity_contribs[0].value, 5)

    def test_affinity_tilt_routed_as_labeled_contribution(self) -> None:
        """commit_to_clash must express the affinity tilt (check_modifier_extra) as a
        labeled AFFINITY ModifierContribution — distinct from STRAIN — so the
        provenance UI attributes the tilt to its real source rather than folding it
        under strain."""
        from unittest.mock import patch

        from world.checks import services as checks_services
        from world.checks.constants import ModifierSourceKind

        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        tilt = 4
        captured: dict = {}
        real_collect = checks_services.collect_check_modifiers

        def _spy_collect(sheet, check_type, **kwargs):
            captured["extra_contributions"] = kwargs.get("extra_contributions")
            return real_collect(sheet, check_type, **kwargs)

        with (
            force_check_outcome(self.success_outcome),
            patch(
                "world.checks.services.collect_check_modifiers",
                side_effect=_spy_collect,
            ),
        ):
            commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
                check_modifier_extra=tilt,
            )

        extras = captured["extra_contributions"]
        affinity_contribs = [c for c in extras if c.source_kind == ModifierSourceKind.AFFINITY]
        self.assertEqual(len(affinity_contribs), 1)
        self.assertEqual(affinity_contribs[0].value, tilt)
        self.assertEqual(affinity_contribs[0].source_label, "Affinity tilt")
        # The tilt must NOT be mislabeled as STRAIN (no strain committed here).
        strain_contribs = [c for c in extras if c.source_kind == ModifierSourceKind.STRAIN]
        self.assertEqual(strain_contribs, [])

    # -------------------------------------------------------------------------
    # 3. Overburn when strain exceeds anima pool
    # -------------------------------------------------------------------------

    def test_overburn_when_strain_exceeds_pool(self) -> None:
        """Committing more strain than the anima pool → was_overburn=True and soulfray fires."""
        # SoulfrayConfig and ConditionTemplate needed for the soulfray accumulation path.
        SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.10"), severity_scale=5, deficit_scale=5
        )
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)

        # Give the character very little anima
        character_sheet, _anima = self._make_character_with_anima(current=2, maximum=10)
        # Technique with minimal base cost so only the strain causes overburn
        technique = self._make_technique_with_template(intensity=3, control=10, anima_cost=1)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=20,  # far exceeds current=2
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result, ClashContributionResult)
        self.assertTrue(result.was_overburn, "Expected was_overburn=True on strain-induced deficit")
        self.assertGreater(
            result.soulfray_severity_accrued,
            0,
            "Expected soulfray severity > 0 when overburning",
        )

    # -------------------------------------------------------------------------
    # 4. Missing action_template raises ValueError
    # -------------------------------------------------------------------------

    def test_technique_without_action_template_raises(self) -> None:
        """A technique with action_template=None must raise ValueError."""
        character_sheet, _anima = self._make_character_with_anima()
        technique = TechniqueFactory(action_template=None)

        with self.assertRaises(ValueError):
            commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

    # -------------------------------------------------------------------------
    # 5. Power + ledger captured from the magic pipeline
    # -------------------------------------------------------------------------

    def test_power_captured_on_result(self) -> None:
        """result.power must be a non-negative int populated from the magic pipeline."""
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsInstance(result.power, int)
        self.assertGreaterEqual(result.power, 0)

    def test_power_ledger_captured_on_result(self) -> None:
        """result.power_ledger must be non-None (captured from the magic pipeline)."""
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsNotNone(result.power_ledger)

    def test_progress_delta_matches_power_scaled_formula(self) -> None:
        """progress_delta must equal outcome_to_delta(check_outcome, power, config)."""
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        expected = outcome_to_delta(
            check_outcome=result.check_outcome,
            power=result.power,
            config=self.config_clash,
        )
        self.assertEqual(result.progress_delta, expected)

    # -------------------------------------------------------------------------
    # 6. clash_interaction is None when no CombatParticipant exists
    # -------------------------------------------------------------------------

    def test_clash_interaction_none_without_participant(self) -> None:
        """When no CombatParticipant is wired to the clash encounter, clash_interaction
        must be None (the pipeline degrades gracefully for unit tests)."""
        character_sheet, _anima = self._make_character_with_anima(current=20, maximum=20)
        technique = self._make_technique_with_template(anima_cost=3)

        # ClashFactory does NOT wire a CombatParticipant, so the lookup returns None.
        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=self.clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        self.assertIsNone(result.clash_interaction)
