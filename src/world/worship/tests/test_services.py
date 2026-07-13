"""Service tests: worship grants, devotion, God's Favorite (#2355)."""

from django.test import TestCase
from django.utils.text import slugify

from world.achievements.models import Achievement, CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Gender
from world.worship.constants import (
    GODS_FAVORITE_CHOSEN,
    GODS_FAVORITE_PRINCE,
    GODS_FAVORITE_PRINCESS,
)
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipGrant
from world.worship.services import bump_devotion, grant_worship


def _seed_favorite_achievements() -> None:
    for name in (GODS_FAVORITE_PRINCESS, GODS_FAVORITE_PRINCE, GODS_FAVORITE_CHOSEN):
        Achievement.objects.get_or_create(
            name=name,
            defaults={"slug": slugify(name), "description": "PLACEHOLDER", "is_active": True},
        )


class GrantWorshipTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.sheet = CharacterSheetFactory()

    def test_grant_updates_pool_lifetime_and_ledger(self) -> None:
        grant_worship(self.being, 25, granted_by=self.sheet, reason="ceremony:test")
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 25)
        self.assertEqual(self.being.lifetime_worship, 25)
        row = WorshipGrant.objects.get(being=self.being)
        self.assertEqual(row.amount, 25)
        self.assertEqual(row.granted_by, self.sheet)

    def test_grant_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            grant_worship(self.being, 0)


class GodsFavoriteTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        _seed_favorite_achievements()
        cls.being = WorshippedBeingFactory()
        cls.female, _ = Gender.objects.get_or_create(
            key="female", defaults={"display_name": "Female"}
        )
        cls.male, _ = Gender.objects.get_or_create(key="male", defaults={"display_name": "Male"})

    def _earned(self, sheet) -> set[str]:
        return set(
            CharacterAchievement.objects.filter(character_sheet=sheet).values_list(
                "achievement__name", flat=True
            )
        )

    def test_first_worshipper_becomes_favorite_with_gender_variant(self) -> None:
        sheet = CharacterSheetFactory(gender=self.female)
        bump_devotion(sheet, self.being, 10)
        self.assertIn(GODS_FAVORITE_PRINCESS, self._earned(sheet))

    def test_nonbinary_or_unset_gender_gets_chosen(self) -> None:
        sheet = CharacterSheetFactory(gender=None)
        bump_devotion(sheet, self.being, 5)
        self.assertIn(GODS_FAVORITE_CHOSEN, self._earned(sheet))

    def test_tie_grants_and_leapfrog_grants_while_prior_holder_keeps(self) -> None:
        first = CharacterSheetFactory(gender=self.male)
        second = CharacterSheetFactory(gender=self.female)
        bump_devotion(first, self.being, 10)
        self.assertIn(GODS_FAVORITE_PRINCE, self._earned(first))
        # Tie at 10 grants to the second character too.
        bump_devotion(second, self.being, 10)
        self.assertIn(GODS_FAVORITE_PRINCESS, self._earned(second))
        # Leapfrog: first pulls ahead again — idempotent re-grant, both keep rows.
        bump_devotion(first, self.being, 5)
        self.assertIn(GODS_FAVORITE_PRINCE, self._earned(first))
        self.assertIn(GODS_FAVORITE_PRINCESS, self._earned(second))

    def test_trailing_worshipper_gets_nothing(self) -> None:
        leader = CharacterSheetFactory(gender=self.male)
        trailer = CharacterSheetFactory(gender=self.female)
        bump_devotion(leader, self.being, 50)
        bump_devotion(trailer, self.being, 10)
        self.assertEqual(self._earned(trailer), set())

    def test_missing_achievement_rows_noop(self) -> None:
        Achievement.objects.all().delete()
        sheet = CharacterSheetFactory()
        standing = bump_devotion(sheet, self.being, 10)
        self.assertEqual(standing.favor, 10)
        self.assertEqual(self._earned(sheet), set())
