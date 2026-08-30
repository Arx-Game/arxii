"""PersonaTitle (#3466): retargeted onto Persona, with a reward branch and a deed branch.

Exactly one of ``reward`` (an authored achievement title) or ``legend_entry`` (a deed that
crossed its station's threshold) is set. ``maybe_grant_deed_title`` is the deed-branch minting
seam, keyed by ``LegendLevelCalibration`` (Task 1) at the deed's ``earned_at_level``.
"""

from django.db import IntegrityError
from django.test import TestCase

from world.achievements.factories import RewardDefinitionFactory
from world.achievements.models import PersonaTitle
from world.achievements.services import maybe_grant_deed_title
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendEntryFactory, LegendLevelCalibrationFactory
from world.societies.models import LegendLevelCalibration


class PersonaTitleBranchTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.reward = RewardDefinitionFactory()
        cls.deed = LegendEntryFactory(persona=cls.persona)

    def test_reward_branch_still_works(self) -> None:
        title = PersonaTitle.objects.create(persona=self.persona, reward=self.reward)
        assert title.legend_entry is None

    def test_deed_branch_works(self) -> None:
        title = PersonaTitle.objects.create(persona=self.persona, legend_entry=self.deed)
        assert title.reward is None

    def test_neither_branch_is_refused(self) -> None:
        with self.assertRaises(IntegrityError):
            PersonaTitle.objects.create(persona=self.persona)

    def test_both_branches_is_refused(self) -> None:
        with self.assertRaises(IntegrityError):
            PersonaTitle.objects.create(
                persona=self.persona, reward=self.reward, legend_entry=self.deed
            )

    def test_reward_unique_per_persona(self) -> None:
        PersonaTitle.objects.create(persona=self.persona, reward=self.reward)
        with self.assertRaises(IntegrityError):
            PersonaTitle.objects.create(persona=self.persona, reward=self.reward)

    def test_deed_unique_per_persona(self) -> None:
        PersonaTitle.objects.create(persona=self.persona, legend_entry=self.deed)
        with self.assertRaises(IntegrityError):
            PersonaTitle.objects.create(persona=self.persona, legend_entry=self.deed)


class MaybeGrantDeedTitleTests(TestCase):
    """The mask guarantee lives here (#3466 Decision 9)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.primary = cls.sheet.primary_persona
        cls.mask = PersonaFactory(character_sheet=cls.sheet, persona_type=PersonaType.ESTABLISHED)

    def test_mints_when_threshold_reached(self) -> None:
        LegendLevelCalibrationFactory(level=2, deed_title_threshold=50)
        deed = LegendEntryFactory(persona=self.primary, base_value=50, earned_at_level=2)
        title = maybe_grant_deed_title(deed)
        assert title is not None
        assert deed.persona.titles.filter(legend_entry=deed).exists()

    def test_no_mint_below_threshold(self) -> None:
        LegendLevelCalibrationFactory(level=2, deed_title_threshold=50)
        deed = LegendEntryFactory(persona=self.primary, base_value=49, earned_at_level=2)
        assert maybe_grant_deed_title(deed) is None

    def test_masked_deed_titles_the_mask_and_never_the_primary(self) -> None:
        """A masked deed still earns its title - it just belongs to that face."""
        LegendLevelCalibrationFactory(level=2, deed_title_threshold=50)
        deed = LegendEntryFactory(persona=self.mask, base_value=50, earned_at_level=2)
        maybe_grant_deed_title(deed)
        assert self.mask.titles.filter(legend_entry=deed).exists()
        assert not self.primary.titles.exists()

    def test_idempotent(self) -> None:
        LegendLevelCalibrationFactory(level=2, deed_title_threshold=50)
        deed = LegendEntryFactory(persona=self.primary, base_value=50, earned_at_level=2)
        maybe_grant_deed_title(deed)
        maybe_grant_deed_title(deed)
        assert self.primary.titles.count() == 1

    def test_missing_calibration_row_raises(self) -> None:
        deed = LegendEntryFactory(persona=self.primary, base_value=50, earned_at_level=7)
        with self.assertRaises(LegendLevelCalibration.DoesNotExist):
            maybe_grant_deed_title(deed)
