"""Identification check seed + difficulty service (#1107 slice 5, Apostate's ruling).

Truth table: (no disguise / mask-only TEMPORARY persona / mundane overlay DESCRIPTOR / magical
overlay FULL) x (stranger / active relationship / famous true-persona), plus guess-ease exposure
and the auto-fail band.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.models import CheckType, CheckTypeTrait
from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME
from world.forms.factories import CharacterFormFactory
from world.forms.models import ConcealmentLevel, DisguiseKind, FormType
from world.forms.services import apply_disguise
from world.forms.services.identification import (
    AUTO_FAIL_GAP,
    identification_difficulty,
)
from world.relationships.factories import CharacterRelationshipFactory
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.services import create_mask
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import (
    ensure_identification_check,
    seed_investigation_check_content,
)
from world.skills.models import Skill
from world.societies.constants import FameTier
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
        self.assertNotIn("perception", {"intellect", "Investigation"})

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
