"""Identification check seed + difficulty service (#1107 slice 5, Apostate's ruling).

Truth table: (no disguise / mask-only TEMPORARY persona / mundane overlay DESCRIPTOR / magical
overlay FULL) x (stranger / active relationship / famous true-persona), plus guess-ease exposure
and the auto-fail band.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.models import CheckType, CheckTypeTrait
from world.checks.test_helpers import force_check_outcome
from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME
from world.forms.factories import CharacterFormFactory
from world.forms.models import ConcealmentLevel, DisguiseKind, FormType
from world.forms.services import apply_disguise
from world.forms.services.identification import (
    AUTO_FAIL_GAP,
    attempt_identification,
    identification_difficulty,
)
from world.forms.types import IdentificationOutcome
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.models import Functionary
from world.relationships.factories import CharacterRelationshipFactory
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.models import PersonaDiscovery
from world.scenes.services import create_mask
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import (
    ensure_identification_check,
    seed_investigation_check_content,
)
from world.skills.models import Skill
from world.societies.constants import FameTier
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import Trait, TraitType


class IdentificationCheckSeedTests(TestCase):
    """The seeded ``CheckType`` — intellect + Investigation (Decision 1)."""

    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_investigation_check_content()

    def test_seeds_identification_check_as_intellect_plus_investigation(self):
        check = CheckType.objects.get(name=IDENTIFICATION_CHECK_TYPE_NAME)
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check).values_list("trait__name", flat=True)
        )
        self.assertEqual(trait_names, {"intellect", "Investigation"})
        self.assertEqual(Trait.objects.get(name="intellect").trait_type, TraitType.STAT)
        self.assertEqual(Trait.objects.get(name="Investigation").trait_type, TraitType.SKILL)

    def test_distinct_from_search_stat_pairing(self):
        # Search is perception + Investigation (#1705); Identification is intellect +
        # Investigation — same skill, deliberately different stat (Decision 1).
        search = CheckType.objects.get(name="Search")
        search_stats = set(
            CheckTypeTrait.objects.filter(check_type=search).values_list("trait__name", flat=True)
        )
        self.assertIn("perception", search_stats)
        identification = CheckType.objects.get(name=IDENTIFICATION_CHECK_TYPE_NAME)
        identification_stats = set(
            CheckTypeTrait.objects.filter(check_type=identification).values_list(
                "trait__name", flat=True
            )
        )
        self.assertNotIn("perception", identification_stats)

    def test_shares_investigation_skill_row_with_search(self):
        skill = Skill.objects.get(trait__name="Investigation")
        composed_types = set(
            CheckTypeTrait.objects.filter(trait=skill.trait).values_list(
                "check_type__name", flat=True
            )
        )
        self.assertEqual(composed_types, {"Search", IDENTIFICATION_CHECK_TYPE_NAME})

    def test_idempotent(self):
        ensure_identification_check()
        ensure_identification_check()
        check = CheckType.objects.get(name=IDENTIFICATION_CHECK_TYPE_NAME)
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check).count(), 2)


class IdentificationDifficultyTests(TestCase):
    """``identification_difficulty`` — the truth table + guess-ease + auto-fail band."""

    @classmethod
    def setUpTestData(cls):
        cls.viewer_character = CharacterFactory()
        cls.viewer_sheet = CharacterSheetFactory(character=cls.viewer_character)
        cls.target_character = CharacterFactory()
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)

    def _apply_overlay(self, *, kind: str, concealment_level: str) -> None:
        disguise = CharacterFormFactory(
            character=self.target_character, form_type=FormType.DISGUISE
        )
        apply_disguise(
            self.target_character, disguise, kind=kind, concealment_level=concealment_level
        )

    def _apply_mask(self) -> None:
        create_mask(self.target_sheet, name="Nobody in Particular")

    def _make_active_relationship(self) -> None:
        CharacterRelationshipFactory(
            source=self.viewer_sheet, target=self.target_sheet, is_active=True
        )

    def _make_famous(self, tier: str) -> None:
        persona = self.target_sheet.primary_persona
        persona.fame_tier = tier
        persona.save()

    # --- No disguise: nothing to identify, regardless of familiarity -------------------------

    def test_no_disguise_not_applicable(self):
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertFalse(odds.applicable)
        self.assertEqual(odds.difficulty, 0)
        self.assertFalse(odds.auto_fail)

    def test_no_disguise_not_applicable_even_with_relationship(self):
        self._make_active_relationship()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertFalse(odds.applicable)

    # --- Mask-only TEMPORARY persona (the mask floor) -----------------------------------------

    def test_mask_only_stranger(self):
        self._apply_mask()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertTrue(odds.applicable)
        self.assertEqual(odds.baseline, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])
        self.assertEqual(odds.familiarity_ease, 0)
        self.assertEqual(odds.difficulty, odds.baseline)
        self.assertFalse(odds.auto_fail)

    def test_mask_only_active_relationship_eases(self):
        self._apply_mask()
        self._make_active_relationship()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertGreater(odds.familiarity_ease, 0)
        self.assertEqual(odds.difficulty, max(0, odds.baseline - odds.familiarity_ease))

    def test_mask_only_famous_true_persona_eases(self):
        self._apply_mask()
        self._make_famous(FameTier.CELEBRITY)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertGreater(odds.familiarity_ease, 0)
        self.assertEqual(odds.difficulty, max(0, odds.baseline - odds.familiarity_ease))

    # --- Mundane overlay, DESCRIPTOR concealment -----------------------------------------------

    def test_mundane_descriptor_stranger(self):
        self._apply_overlay(
            kind=DisguiseKind.MUNDANE, concealment_level=ConcealmentLevel.DESCRIPTOR
        )
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertTrue(odds.applicable)
        self.assertEqual(odds.baseline, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])
        self.assertEqual(odds.familiarity_ease, 0)
        self.assertEqual(odds.difficulty, odds.baseline)
        self.assertFalse(odds.auto_fail)

    def test_mundane_descriptor_active_relationship(self):
        self._apply_overlay(
            kind=DisguiseKind.MUNDANE, concealment_level=ConcealmentLevel.DESCRIPTOR
        )
        self._make_active_relationship()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertLess(odds.difficulty, odds.baseline)

    def test_mundane_descriptor_famous_true_persona(self):
        self._apply_overlay(
            kind=DisguiseKind.MUNDANE, concealment_level=ConcealmentLevel.DESCRIPTOR
        )
        self._make_famous(FameTier.WORLD_FAMOUS)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertLess(odds.difficulty, odds.baseline)

    # --- Magical overlay, FULL concealment (the hardest band) ----------------------------------

    def test_magical_full_stranger_auto_fails(self):
        self._apply_overlay(kind=DisguiseKind.MAGICAL, concealment_level=ConcealmentLevel.FULL)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertTrue(odds.applicable)
        self.assertGreater(odds.baseline, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])
        # A total stranger gets no ease against a vast gap — Decision 4 auto-fail.
        self.assertTrue(odds.auto_fail)

    def test_magical_full_active_relationship_still_hard_but_maybe_not_auto_fail(self):
        self._apply_overlay(kind=DisguiseKind.MAGICAL, concealment_level=ConcealmentLevel.FULL)
        self._make_active_relationship()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertLess(odds.difficulty, odds.baseline)

    def test_magical_full_famous_and_related_stacks_eases_below_auto_fail(self):
        self._apply_overlay(kind=DisguiseKind.MAGICAL, concealment_level=ConcealmentLevel.FULL)
        self._make_active_relationship()
        self._make_famous(FameTier.WORLD_FAMOUS)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        # Both eases stack (Decision 2): knowing AND recognizing a world-famous face together
        # close even the vast magical-FULL gap.
        self.assertFalse(odds.auto_fail)

    # --- guess_ease is exposed, not applied (Decision 3 — attempt_identification applies it) ---

    def test_guess_ease_exposed_but_not_subtracted(self):
        self._apply_mask()
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertGreater(odds.guess_ease, 0)
        self.assertEqual(odds.difficulty, odds.baseline)

    def test_guess_ease_not_applicable_case_is_zero(self):
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertEqual(odds.guess_ease, 0)

    # --- auto-fail band ------------------------------------------------------------------------

    def test_auto_fail_gap_is_positive(self):
        self.assertGreater(AUTO_FAIL_GAP, 0)

    def test_easy_bands_never_auto_fail(self):
        self._apply_overlay(kind=DisguiseKind.MUNDANE, concealment_level=ConcealmentLevel.NONE)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertFalse(odds.auto_fail)

    # --- kit-quality bonus (#2249): a kit-crafted disguise raises the baseline ---

    def _apply_overlay_with_kit(self, *, kit_multiplier: float) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.items.models import QualityTier

        tier = QualityTier.objects.create(
            name=f"Kit Tier {kit_multiplier}",
            color_hex="#123456",
            numeric_min=0,
            numeric_max=100,
            stat_multiplier=kit_multiplier,
            sort_order=99,
        )
        template = ItemTemplateFactory(name=f"Disguise Kit {kit_multiplier}")
        kit_instance = ItemInstanceFactory(template=template, quality_tier=tier)
        disguise = CharacterFormFactory(
            character=self.target_character, form_type=FormType.DISGUISE
        )
        apply_disguise(
            self.target_character,
            disguise,
            kind=DisguiseKind.MUNDANE,
            concealment_level=ConcealmentLevel.DESCRIPTOR,
            kit_instance=kit_instance,
        )

    def test_kit_quality_raises_baseline(self):
        self._apply_overlay_with_kit(kit_multiplier=2.0)
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertTrue(odds.applicable)
        self.assertGreater(odds.kit_quality_bonus, 0)
        self.assertEqual(
            odds.baseline, DIFFICULTY_VALUES[DifficultyChoice.NORMAL] + odds.kit_quality_bonus
        )

    def test_no_kit_means_no_quality_bonus(self):
        # Narratively-applied disguise (no kit instance) — baseline unchanged.
        self._apply_overlay(
            kind=DisguiseKind.MUNDANE, concealment_level=ConcealmentLevel.DESCRIPTOR
        )
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertEqual(odds.kit_quality_bonus, 0)
        self.assertEqual(odds.baseline, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    def test_high_quality_kit_makes_auto_fail_reachable(self):
        # A magical FULL disguise with a very high-quality kit pushes past the
        # auto-fail threshold even for a stranger.
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.items.models import QualityTier

        tier = QualityTier.objects.create(
            name="Godlike Kit",
            color_hex="#FF0000",
            numeric_min=0,
            numeric_max=100,
            stat_multiplier=10.0,
            sort_order=999,
        )
        template = ItemTemplateFactory(name="Godlike Disguise Kit")
        kit_instance = ItemInstanceFactory(template=template, quality_tier=tier)
        disguise = CharacterFormFactory(
            character=self.target_character, form_type=FormType.DISGUISE
        )
        apply_disguise(
            self.target_character,
            disguise,
            kind=DisguiseKind.MAGICAL,
            concealment_level=ConcealmentLevel.FULL,
            kit_instance=kit_instance,
        )
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        self.assertTrue(odds.auto_fail)


class AttemptIdentificationTests(TestCase):
    """``attempt_identification`` — the roll + ``PersonaDiscovery``-write orchestrator (Task 2).

    ``target_character`` wears a mask (a TEMPORARY fake-name persona) in ``setUpTestData`` so
    every test has a distinct presented/true persona pair to link — the same fixture shape
    ``IdentificationDifficultyTests._apply_mask`` uses. Rolls are forced deterministic via
    ``force_check_outcome`` rather than depending on trait values / dice.
    """

    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_investigation_check_content()
        cls.viewer_character = CharacterFactory()
        cls.viewer_sheet = CharacterSheetFactory(character=cls.viewer_character)
        cls.target_character = CharacterFactory()
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)
        cls.mask = create_mask(cls.target_sheet, name="Nobody in Particular")

    def _magical_full_target(self):
        """A fresh, unrelated target wearing a magical FULL disguise — the auto-fail band
        against a total stranger (mirrors ``IdentificationDifficultyTests``'s equivalent)."""
        target = CharacterFactory()
        CharacterSheetFactory(character=target)
        disguise = CharacterFormFactory(character=target, form_type=FormType.DISGUISE)
        apply_disguise(
            target, disguise, kind=DisguiseKind.MAGICAL, concealment_level=ConcealmentLevel.FULL
        )
        return target

    # --- nothing to identify -> FAILURE (defensive fallback; Task 3 gates this normally) --------

    def test_no_disguise_no_mask_is_failure(self):
        stranger = CharacterFactory()
        CharacterSheetFactory(character=stranger)
        result = attempt_identification(self.viewer_character, stranger)
        self.assertEqual(result.outcome, IdentificationOutcome.FAILURE)
        self.assertFalse(PersonaDiscovery.objects.exists())

    # --- AUTO_FAIL short-circuits before rolling -------------------------------------------------

    def test_auto_fail_short_circuits(self):
        magical_target = self._magical_full_target()
        result = attempt_identification(self.viewer_character, magical_target)
        self.assertEqual(result.outcome, IdentificationOutcome.AUTO_FAIL)
        self.assertFalse(PersonaDiscovery.objects.exists())

    # --- SUCCESS writes PersonaDiscovery; a second attempt is ALREADY_KNOWN, not a duplicate -----

    def test_success_writes_persona_discovery_idempotently(self):
        success = CheckOutcomeFactory(name="Identification Test Success", success_level=2)
        with force_check_outcome(success):
            result = attempt_identification(self.viewer_character, self.target_character)
        self.assertEqual(result.outcome, IdentificationOutcome.SUCCESS)
        self.assertEqual(result.revealed_name, self.target_sheet.primary_persona.name)
        self.assertIsNotNone(result.persona_discovery)
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

        with force_check_outcome(success):
            result_again = attempt_identification(self.viewer_character, self.target_character)
        self.assertEqual(result_again.outcome, IdentificationOutcome.ALREADY_KNOWN)
        self.assertEqual(result_again.revealed_name, self.target_sheet.primary_persona.name)
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

    # --- plain FAILURE persists nothing ----------------------------------------------------------

    def test_plain_failure_persists_nothing(self):
        failure = CheckOutcomeFactory(name="Identification Test Failure", success_level=-1)
        with force_check_outcome(failure):
            result = attempt_identification(self.viewer_character, self.target_character)
        self.assertEqual(result.outcome, IdentificationOutcome.FAILURE)
        self.assertFalse(PersonaDiscovery.objects.exists())

    # --- BOTCH fake-IDs a seeded Functionary, never a PC ------------------------------------------

    def test_botch_fake_ids_a_seeded_functionary_never_a_pc(self):
        role = NPCRoleFactory(name="Gate Clerk")
        functionary = FunctionaryFactory(role=role, name_override="Old Marta")
        botch = CheckOutcomeFactory(name="Identification Test Botch", success_level=-2)
        with force_check_outcome(botch):
            result = attempt_identification(self.viewer_character, self.target_character)
        self.assertEqual(result.outcome, IdentificationOutcome.BOTCH_FAKE_ID)
        self.assertEqual(result.revealed_name, functionary.display_name)
        pc_names = {
            self.viewer_sheet.primary_persona.name,
            self.target_sheet.primary_persona.name,
            self.mask.name,
        }
        self.assertNotIn(result.revealed_name, pc_names)
        self.assertFalse(PersonaDiscovery.objects.exists())

    def test_botch_degrades_to_failure_when_no_functionary_exists(self):
        self.assertFalse(Functionary.objects.exists())
        botch = CheckOutcomeFactory(name="Identification Test Botch No NPC", success_level=-3)
        with force_check_outcome(botch):
            result = attempt_identification(self.viewer_character, self.target_character)
        self.assertEqual(result.outcome, IdentificationOutcome.FAILURE)
        self.assertFalse(PersonaDiscovery.objects.exists())

    # --- oracle rule: FAILURE and AUTO_FAIL are player-indistinguishable -------------------------

    def test_failure_and_auto_fail_share_identical_player_message(self):
        magical_target = self._magical_full_target()
        auto_fail_result = attempt_identification(self.viewer_character, magical_target)

        failure = CheckOutcomeFactory(name="Identification Test Failure Msg", success_level=-1)
        with force_check_outcome(failure):
            failure_result = attempt_identification(self.viewer_character, self.target_character)

        self.assertEqual(auto_fail_result.outcome, IdentificationOutcome.AUTO_FAIL)
        self.assertEqual(failure_result.outcome, IdentificationOutcome.FAILURE)
        self.assertEqual(auto_fail_result.player_message, failure_result.player_message)
        self.assertTrue(auto_fail_result.player_message)

    # --- guess ease: a correct guess eases the roll (proven via a botch surviving to success) ----

    def test_correct_guess_eases_the_roll(self):
        # A correct guess subtracts guess_ease from target_difficulty (Decision 3); an incorrect
        # guess doesn't. Forced to a plain FAILURE (not SUCCESS/BOTCH) so neither call writes a
        # PersonaDiscovery — an ALREADY_KNOWN short-circuit on the second call would never reach
        # perform_check, leaving nothing to assert on. Asserted via the captured target_difficulty
        # perform_check actually saw.
        odds = identification_difficulty(self.viewer_sheet, self.target_character)
        failure = CheckOutcomeFactory(name="Identification Test Guess Failure", success_level=-1)

        with force_check_outcome(failure) as capture:
            attempt_identification(
                self.viewer_character,
                self.target_character,
                guess_name=self.target_sheet.primary_persona.name,
            )
        self.assertEqual(capture.target_difficulty, max(0, odds.difficulty - odds.guess_ease))

        with force_check_outcome(failure) as capture_wrong:
            attempt_identification(
                self.viewer_character, self.target_character, guess_name="Definitely Not Them"
            )
        self.assertEqual(capture_wrong.target_difficulty, odds.difficulty)

    # --- ruling 1b (#1107 Task 3 review): overlay-only degenerate pair short-circuits ------------

    def test_overlay_only_degenerate_pair_short_circuits_before_rolling(self):
        # apply_disguise alone (no create_mask) never swaps active_persona_for_sheet, so
        # presented == true even though identification_difficulty computes a rollable baseline
        # from the overlay (MUNDANE/DESCRIPTOR — well under the auto-fail band, so this is NOT
        # the AUTO_FAIL short-circuit). Forced to a SUCCESS-level outcome to prove the guard wins
        # BEFORE any roll happens: if it reached perform_check, a forced success would hit the
        # (pre-fix) SUCCESS path and mint a no-op PersonaDiscovery.
        target = CharacterFactory()
        CharacterSheetFactory(character=target)
        disguise = CharacterFormFactory(character=target, form_type=FormType.DISGUISE)
        apply_disguise(
            target,
            disguise,
            kind=DisguiseKind.MUNDANE,
            concealment_level=ConcealmentLevel.DESCRIPTOR,
        )
        success = CheckOutcomeFactory(
            name="Identification Test Overlay Degenerate", success_level=2
        )
        with force_check_outcome(success):
            result = attempt_identification(self.viewer_character, target)

        self.assertEqual(result.outcome, IdentificationOutcome.FAILURE)
        self.assertIsNone(result.persona_discovery)
        self.assertEqual(result.revealed_name, "")
        self.assertFalse(PersonaDiscovery.objects.exists())

        # No success message leaks through — it's the same oracle-rule FAILURE/AUTO_FAIL string.
        auto_fail = attempt_identification(self.viewer_character, self._magical_full_target())
        self.assertEqual(result.player_message, auto_fail.player_message)
