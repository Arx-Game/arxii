"""Player anima ritual names must not collide (#2724)."""

from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings
from evennia.accounts.models import AccountDB

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import RitualExecutionKind
from world.magic.models.rituals import Ritual
from world.magic.services.anima import (
    _RITUAL_NAME_ATTEMPTS,
    _uniquify_ritual_name,
    provision_player_anima_ritual,
)
from world.roster.factories import RosterEntryFactory
from world.skills.factories import SkillFactory
from world.traits.factories import TraitFactory
from world.traits.models import TraitType


class UniquifyRitualNameTests(TestCase):
    """``Ritual.name`` is unique=True and player names derive from first names."""

    def test_free_name_is_returned_unchanged(self) -> None:
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering")

    def test_taken_name_gets_a_numeric_suffix(self) -> None:
        Ritual.objects.create(
            name="Dawn Offering",
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering (2)")

    def test_suffix_increments_past_multiple_collisions(self) -> None:
        for name in ("Dawn Offering", "Dawn Offering (2)", "Dawn Offering (3)"):
            Ritual.objects.create(
                name=name,
                description="",
                narrative_prose="",
                execution_kind=RitualExecutionKind.SCENE_ACTION,
                service_function_path="",
            )
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering (4)")

    def test_result_always_fits_the_column(self) -> None:
        max_length = Ritual._meta.get_field("name").max_length
        base = "X" * max_length
        Ritual.objects.create(
            name=base,
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        result = _uniquify_ritual_name(base)
        self.assertLessEqual(len(result), max_length)
        self.assertNotEqual(result, base)


@override_settings(SEED_SAMPLE_CONTENT=True)  # Arcana Aspect gates on #2698
class ProvisionPlayerAnimaRitualRetryTests(TestCase):
    """The TOCTOU race between _uniquify_ritual_name's check and the create() (#2724).

    ``_uniquify_ritual_name`` only narrows the race; ``provision_player_anima_ritual``
    must retry inside a nested ``transaction.atomic()`` (a savepoint) so a losing
    ``IntegrityError`` doesn't poison the caller's outer atomic block.
    """

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create(username=f"ritualretry_{id(cls)}")
        cls.sheet = CharacterSheetFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        # Explicit stat/skill bypass provision_player_anima_ritual's default-resolution
        # branches (Willpower lookup, highest-skill query) — irrelevant to this race.
        cls.stat = TraitFactory(name="ritualretry_stat", trait_type=TraitType.STAT)
        cls.skill = SkillFactory(trait__name="RitualRetrySkill")

    def _provision(self):
        return provision_player_anima_ritual(
            self.account,
            self.sheet,
            self.roster_entry,
            ritual_name="Whatever",
            stat=self.stat,
            skill=self.skill,
        )

    def test_retries_inside_a_savepoint_when_the_first_candidate_collides(self) -> None:
        """A losing first attempt doesn't poison the retry — the create still succeeds."""
        Ritual.objects.create(
            name="Taken Name",
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        with patch(
            "world.magic.services.anima._uniquify_ritual_name",
            side_effect=["Taken Name", "Free Name"],
        ) as mock_uniquify:
            ritual = self._provision()

        self.assertEqual(mock_uniquify.call_count, 2)
        self.assertIsNotNone(ritual)
        self.assertEqual(ritual.name, "Free Name")
        self.assertEqual(Ritual.objects.filter(name="Free Name").count(), 1)

    def test_exhausting_every_attempt_raises_instead_of_silently_returning_none(self) -> None:
        """Every attempt loses the race — deliberately raises rather than skipping CG."""
        Ritual.objects.create(
            name="Collide",
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        with patch(
            "world.magic.services.anima._uniquify_ritual_name",
            return_value="Collide",
        ) as mock_uniquify:
            with self.assertRaises(IntegrityError):
                self._provision()

        # Capped at the named module constant — not an unbounded/silent retry.
        self.assertEqual(mock_uniquify.call_count, _RITUAL_NAME_ATTEMPTS)
        # No stray row: every attempt's savepoint rolled back cleanly.
        self.assertEqual(Ritual.objects.filter(author_account=self.account).count(), 0)
