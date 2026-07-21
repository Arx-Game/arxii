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
from world.worship.models import PatronageValence, WorshipGrant
from world.worship.services import (
    active_patronage_for,
    best_patronage_favor,
    bump_devotion,
    establish_patronage,
    get_chosen_favor_config,
    grant_worship,
    release_patronage,
)


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


class EstablishPatronageTests(TestCase):
    """Patronage establishment, active filtering, and release (#2550)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.sheet = CharacterSheetFactory()

    def test_establish_patronage_sets_valence_and_established_at(self) -> None:
        standing = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        self.assertEqual(standing.valence, PatronageValence.DEVOTIONAL)
        self.assertIsNotNone(standing.established_at)
        self.assertIsNone(standing.released_at)

    def test_establish_patronage_idempotent_does_not_reset_established_at(self) -> None:
        first = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        original_at = first.established_at
        second = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.established_at, original_at)

    def test_establish_patronage_on_existing_worship_preserves_favor(self) -> None:
        bump_devotion(self.sheet, self.being, 15)
        standing = establish_patronage(self.sheet, self.being, valence=PatronageValence.PACT)
        self.assertEqual(standing.favor, 15)
        self.assertEqual(standing.valence, PatronageValence.PACT)


class ActivePatronageTests(TestCase):
    """active_patronage_for and best_patronage_favor (#2550)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.being_a = WorshippedBeingFactory()
        cls.being_b = WorshippedBeingFactory()
        cls.sheet = CharacterSheetFactory()

    def test_active_patronage_excludes_ordinary_worship(self) -> None:
        bump_devotion(self.sheet, self.being_a, 10)  # ordinary worship, no valence
        patronages = active_patronage_for(self.sheet)
        self.assertEqual(patronages, [])

    def test_active_patronage_includes_patronage_rows(self) -> None:
        establish_patronage(self.sheet, self.being_a, valence=PatronageValence.DEVOTIONAL)
        patronages = active_patronage_for(self.sheet)
        self.assertEqual(len(patronages), 1)
        self.assertEqual(patronages[0].being, self.being_a)

    def test_active_patronage_ordered_by_favor_desc(self) -> None:
        establish_patronage(self.sheet, self.being_a, valence=PatronageValence.DEVOTIONAL)
        establish_patronage(self.sheet, self.being_b, valence=PatronageValence.DEVOTIONAL)
        bump_devotion(self.sheet, self.being_b, 20)
        bump_devotion(self.sheet, self.being_a, 5)
        patronages = active_patronage_for(self.sheet)
        self.assertEqual(patronages[0].being, self.being_b)
        self.assertEqual(patronages[1].being, self.being_a)

    def test_best_patronage_favor_returns_highest(self) -> None:
        establish_patronage(self.sheet, self.being_a, valence=PatronageValence.DEVOTIONAL)
        bump_devotion(self.sheet, self.being_a, 20)
        self.assertEqual(best_patronage_favor(self.sheet), 20)

    def test_best_patronage_favor_zero_when_no_patronage(self) -> None:
        self.assertEqual(best_patronage_favor(self.sheet), 0)

    def test_best_patronage_favor_excludes_released(self) -> None:
        standing = establish_patronage(
            self.sheet, self.being_a, valence=PatronageValence.DEVOTIONAL
        )
        bump_devotion(self.sheet, self.being_a, 20)
        release_patronage(standing)
        self.assertEqual(best_patronage_favor(self.sheet), 0)


class ReleasePatronageTests(TestCase):
    """release_patronage marks bonds dormant (#2550)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.sheet = CharacterSheetFactory()

    def test_release_sets_released_at(self) -> None:
        standing = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        release_patronage(standing)
        standing.refresh_from_db()
        self.assertIsNotNone(standing.released_at)

    def test_released_bond_excluded_from_active(self) -> None:
        standing = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        release_patronage(standing)
        self.assertEqual(active_patronage_for(self.sheet), [])


class ChosenFavorConfigTests(TestCase):
    """Lazy singleton creation (#2550)."""

    def test_get_chosen_favor_config_creates_singleton(self) -> None:
        config = get_chosen_favor_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.anima_recovery_threshold, 10)
        self.assertEqual(config.anima_recovery_bonus, 5)

    def test_get_chosen_favor_config_idempotent(self) -> None:
        first = get_chosen_favor_config()
        second = get_chosen_favor_config()
        self.assertEqual(first.pk, second.pk)
