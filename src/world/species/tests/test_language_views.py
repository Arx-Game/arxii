"""API tests for GET /api/species/my-languages/ (#2993).

The requester's own active character's known languages — fluency, comprehension
band, and which one is the sticky ``current_language``. Self-scoped only: no
``character`` query parameter, and an account with no active character gets an
empty list, never a 403/500 (mirrors the items app's visible-worn contract).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.conditions.factories import ConditionInstanceFactory
from world.mechanics.models import ModifierTarget
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.species.language_constants import FLUENT_GRANT_VALUE, Fluency, fluency_band
from world.species.models import Language
from world.species.tests.test_language_comprehension import (
    make_language_with_target,
    make_understanding_condition,
)
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType

URL = "/api/species/my-languages/"


class MyLanguagesViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.khatic_trait = Trait.objects.create(
            name="Khatic",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.khatic = Language.objects.create(name="Khatic", trait=cls.khatic_trait)

        cls.arvani_trait = Trait.objects.create(
            name="Arvani",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.arvani = Language.objects.create(
            name="Arvani", trait=cls.arvani_trait, is_universal=True
        )

    def setUp(self) -> None:
        self.user = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.user)
        self.entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=self.entry, player_data=self.player_data)
        self.sheet = self.entry.character_sheet

    def test_requires_authentication(self) -> None:
        response = self.client.get(URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_lists_own_languages_with_fluency_and_band(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.khatic_trait, value=15)
        CharacterTraitValue.objects.create(
            character=self.sheet, trait=self.arvani_trait, value=FLUENT_GRANT_VALUE
        )
        self.sheet.current_language = self.khatic
        self.sheet.save(update_fields=["current_language"])

        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        rows = {row["name"]: row for row in response.data}
        assert set(rows) == {"Khatic", "Arvani"}

        khatic_row = rows["Khatic"]
        assert khatic_row["language_id"] == self.khatic.pk
        assert khatic_row["fluency"] == 15
        assert khatic_row["band"] == fluency_band(15).value
        assert khatic_row["band"] == Fluency.BROKEN.value
        assert khatic_row["is_current"] is True

        arvani_row = rows["Arvani"]
        assert arvani_row["fluency"] == FLUENT_GRANT_VALUE
        assert arvani_row["band"] == Fluency.FLUENT.value
        assert arvani_row["is_current"] is False

    def test_no_active_character_returns_empty_list(self) -> None:
        no_character_user = AccountFactory()
        self.client.force_authenticate(user=no_character_user)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_language_never_trained_is_absent(self) -> None:
        """A Language row with no CharacterTraitValue for this sheet isn't listed."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def _understanding(self, name: str, *, severity: int):
        ModifierTarget.clear_trait_cache()
        language, target = make_language_with_target(name)
        condition = make_understanding_condition(f"Placeholder {name} Charm", target)
        instance = ConditionInstanceFactory(
            target=self.sheet.character, condition=condition, severity=severity
        )
        return language, instance

    def test_condition_only_language_appears_marked_temporary(self) -> None:
        language, _instance = self._understanding("SheetTongueA", severity=4)
        self.client.force_authenticate(user=self.user)
        rows = {row["name"]: row for row in self.client.get(URL).data}
        row = rows[language.name]
        assert row["fluency"] == 0
        assert row["band"] == Fluency.NONE.value
        assert row["effective_fluency"] == 80
        assert row["effective_band"] == Fluency.FLUENT.value
        assert row["temporary_sources"] == ["Placeholder SheetTongueA Charm"]

    def test_trained_language_raised_by_condition_keeps_trained_level(self) -> None:
        language, _instance = self._understanding("SheetTongueB", severity=2)
        CharacterTraitValue.objects.create(character=self.sheet, trait=language.trait, value=20)
        self.client.force_authenticate(user=self.user)
        row = next(r for r in self.client.get(URL).data if r["name"] == language.name)
        assert (row["fluency"], row["band"]) == (20, Fluency.BROKEN.value)
        assert (row["effective_fluency"], row["effective_band"]) == (
            60,
            Fluency.CONVERSATIONAL.value,
        )

    def test_condition_only_row_disappears_when_condition_ends(self) -> None:
        language, instance = self._understanding("SheetTongueC", severity=4)
        instance.delete()
        self.client.force_authenticate(user=self.user)
        names = [row["name"] for row in self.client.get(URL).data]
        assert language.name not in names

    def test_trained_row_without_condition_has_no_temporary_sources(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.khatic_trait, value=15)
        self.client.force_authenticate(user=self.user)
        row = next(r for r in self.client.get(URL).data if r["name"] == "Khatic")
        assert row["effective_fluency"] == 15
        assert row["temporary_sources"] == []

    def _query_count_fixture(self, count: int) -> None:
        """count trained languages plus count condition-only languages (query-count pin)."""
        for i in range(count):
            trait = Trait.objects.create(
                name=f"QueryCountTrained{i}",
                trait_type=TraitType.LANGUAGE,
                category=TraitCategory.GENERAL,
            )
            Language.objects.create(name=f"QueryCountTrained{i}", trait=trait)
            CharacterTraitValue.objects.create(character=self.sheet, trait=trait, value=20)
        for i in range(count):
            self._understanding(f"QueryCountCond{i}", severity=2)

    def test_query_count_fixed_for_one_language(self) -> None:
        self._query_count_fixture(1)
        self.client.force_authenticate(user=self.user)
        with self.assertNumQueries(13):
            response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK

    def test_query_count_fixed_for_three_languages(self) -> None:
        self._query_count_fixture(3)
        self.client.force_authenticate(user=self.user)
        with self.assertNumQueries(13):
            response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
