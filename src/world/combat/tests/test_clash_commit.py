"""Tests for commit_to_clash — the per-round clash contribution pipeline."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat import clash as clash_module
from world.combat.clash import commit_to_clash, outcome_to_delta
from world.combat.constants import RiskLevel
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
        """Committing more strain than the anima pool → was_overburn=True and soulfray fires.

        Overburn/soulfray is a lethal-encounter behavior: a non-lethal encounter
        clamps the effective cost to available anima so it can never deficit. The
        clash must therefore run in a LETHAL encounter for the overburn path to
        fire (#1182 threads lethal=clash.encounter.is_lethal into use_technique).
        """
        # SoulfrayConfig and ConditionTemplate needed for the soulfray accumulation path.
        SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.10"), severity_scale=5, deficit_scale=5
        )
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)

        lethal_clash = ClashFactory(encounter__risk_level=RiskLevel.LETHAL)
        # Give the character very little anima
        character_sheet, _anima = self._make_character_with_anima(current=2, maximum=10)
        # Technique with minimal base cost so only the strain causes overburn
        technique = self._make_technique_with_template(intensity=3, control=10, anima_cost=1)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=character_sheet,
                technique=technique,
                clash=lethal_clash,
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

    # -------------------------------------------------------------------------
    # 7. #2014 — the caster's personal check wins over the template's fallback
    # -------------------------------------------------------------------------

    def test_commit_rolls_personal_check_when_provisioned(self) -> None:
        """#2014: a provisioned caster's clash contribution rolls THEIR check."""
        from evennia.accounts.models import AccountDB

        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import RitualCheckConfigFactory
        from world.magic.models.rituals import Ritual

        character_sheet, _anima = self._make_character_with_anima()
        technique = self._make_technique_with_template(anima_cost=3)

        account = AccountDB.objects.create(username=f"clash_cc_{id(self)}")
        ritual = Ritual.objects.create(
            name=f"clash_cc_ritual_{id(self)}",
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        config = RitualCheckConfigFactory(ritual=ritual)
        character_sheet.character.db_account = account
        character_sheet.character.save(update_fields=["db_account"])

        captured = []
        from world.checks.services import perform_check as real_perform_check

        def recording_perform_check(objectdb, check_type, **kwargs):
            captured.append(check_type)
            return real_perform_check(objectdb, check_type, **kwargs)

        with (
            force_check_outcome(self.success_outcome),
            patch(
                "world.checks.services.perform_check",
                recording_perform_check,
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
            )

        self.assertEqual(captured, [config.check_type])
        self.assertNotEqual(config.check_type, technique.action_template.check_type)


class CommitToClashLethalFlagTests(TestCase):
    """commit_to_clash threads lethal=clash.encounter.is_lethal into use_technique (#1182).

    Latent today (PvP mirror surfaces never form a clash), but the cap must hold
    if a non-lethal clash path is ever enabled. A spy wraps the real
    use_technique so the rest of the pipeline runs unchanged.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="lethal_flag_success", success_level=1)

    def _make_character_with_anima(self) -> CharacterSheetFactory:
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        return sheet

    def _make_technique(self) -> object:
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(intensity=5, control=10, anima_cost=3, action_template=template)

    def _captured_lethal(self, *, risk_level: str) -> bool:
        sheet = self._make_character_with_anima()
        technique = self._make_technique()
        clash = ClashFactory(encounter__risk_level=risk_level)
        with force_check_outcome(self.success_outcome):
            with patch.object(
                clash_module, "use_technique", wraps=clash_module.use_technique
            ) as spy:
                commit_to_clash(
                    character_sheet=sheet,
                    technique=technique,
                    clash=clash,
                    strain_commitment=0,
                    action_slot="FOCUSED",
                    config_clash=self.config_clash,
                    config_strain=self.config_strain,
                )
        return spy.call_args.kwargs["lethal"]

    def test_non_lethal_encounter_threads_lethal_false(self) -> None:
        self.assertIs(self._captured_lethal(risk_level=RiskLevel.MODERATE), False)

    def test_lethal_encounter_threads_lethal_true(self) -> None:
        self.assertIs(self._captured_lethal(risk_level=RiskLevel.LETHAL), True)


class CommitToClashSituationContextTests(TestCase):
    """commit_to_clash threads situation_ctx into use_technique (#2536, Task 4
    review fix) — the clash cast path was previously silently un-threaded even
    though a CombatParticipant is genuinely resolvable at this call site (the
    step-9 Interaction-recording block already resolved one, just too late to
    reach use_technique). Mirrors CommitToClashLethalFlagTests' spy pattern.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="situation_ctx_success", success_level=1)

    def _make_character_with_anima(self) -> CharacterSheetFactory:
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        return sheet

    def _make_technique(self) -> object:
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(intensity=5, control=10, anima_cost=3, action_template=template)

    def test_situation_ctx_threaded_when_participant_resolves(self) -> None:
        from world.combat.factories import CombatParticipantFactory
        from world.combat.round_context import CombatRoundContext

        sheet = self._make_character_with_anima()
        technique = self._make_technique()
        clash = ClashFactory()
        participant = CombatParticipantFactory(encounter=clash.encounter, character_sheet=sheet)

        with force_check_outcome(self.success_outcome):
            with patch.object(
                clash_module, "use_technique", wraps=clash_module.use_technique
            ) as spy:
                commit_to_clash(
                    character_sheet=sheet,
                    technique=technique,
                    clash=clash,
                    strain_commitment=0,
                    action_slot="FOCUSED",
                    config_clash=self.config_clash,
                    config_strain=self.config_strain,
                )

        captured_ctx = spy.call_args.kwargs["situation_ctx"]
        self.assertIsInstance(captured_ctx, CombatRoundContext)
        self.assertEqual(captured_ctx.participant, participant)

    def test_situation_ctx_none_when_no_participant_resolves(self) -> None:
        """Legacy fixtures / isolated unit tests without a wired CombatParticipant
        degrade gracefully to situation_ctx=None, exactly like a non-combat cast —
        never an exception."""
        sheet = self._make_character_with_anima()
        technique = self._make_technique()
        clash = ClashFactory()  # no CombatParticipant created for `sheet`

        with force_check_outcome(self.success_outcome):
            with patch.object(
                clash_module, "use_technique", wraps=clash_module.use_technique
            ) as spy:
                commit_to_clash(
                    character_sheet=sheet,
                    technique=technique,
                    clash=clash,
                    strain_commitment=0,
                    action_slot="FOCUSED",
                    config_clash=self.config_clash,
                    config_strain=self.config_strain,
                )

        self.assertIsNone(spy.call_args.kwargs["situation_ctx"])


class CommitToClashSituationalPerkTests(TestCase):
    """A combat-positioning situational perk (AT_RANGE) fires for POWER_BONUS
    through the clash contribution path now that situation_ctx is threaded
    (#2536, Task 4 review fix). Mirrors
    world.magic.tests.test_power_derivation
    .VowSituationalPowerTermTests.test_perk_fires_with_combat_situation_ctx_exact_arithmetic
    but exercised through commit_to_clash end-to-end instead of calling the
    provider directly.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="clash_at_range_success", success_level=1)

    def _make_character_with_anima(self) -> CharacterSheetFactory:
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        return sheet

    def _make_technique(self) -> object:
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(intensity=5, control=10, anima_cost=3, action_template=template)

    def _commit_with_at_range_perk(self, *, at_range: bool) -> int:
        """Build a fresh clash + PC + AT_RANGE-gated SELF perk (magnitude 13,
        thread level 7) and return the resulting result.power. `at_range`
        controls whether the opponent shares the PC's position (IN_MELEE) or
        not (AT_RANGE)."""
        from world.areas.positioning.services import (
            connect_positions,
            create_position,
            place_in_position,
        )
        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            EngagementLockFactory,
        )
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.factories import ThreadFactory

        sheet = self._make_character_with_anima()
        technique = self._make_technique()
        clash = ClashFactory()

        room = clash.encounter.room
        pos_a = create_position(room, "pos_a")
        pos_b = create_position(room, "pos_b")
        connect_positions(pos_a, pos_b, is_passable=True)

        sheet.character.location = room
        sheet.character.save()
        place_in_position(sheet.character, pos_a)

        participant = CombatParticipantFactory(encounter=clash.encounter, character_sheet=sheet)
        opponent = CombatOpponentFactory(encounter=clash.encounter)
        place_in_position(opponent.objectdb, pos_a if not at_range else pos_b)
        EngagementLockFactory(encounter=clash.encounter, participant=participant, opponent=opponent)

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=CovenantFactory(), covenant_role=role, engaged=True
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=13,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)
        ThreadFactory(owner=sheet, level=7)

        with force_check_outcome(self.success_outcome):
            result = commit_to_clash(
                character_sheet=sheet,
                technique=technique,
                clash=clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )
        return result.power

    def test_at_range_perk_raises_clash_power(self) -> None:
        power_at_range = self._commit_with_at_range_perk(at_range=True)
        power_in_melee = self._commit_with_at_range_perk(at_range=False)
        # 7 * 13 / 10 = 9.1 -> 9, mirrors the round-path arithmetic exactly.
        self.assertEqual(power_at_range - power_in_melee, 9)
