"""Inheritance: a distinction that pays a flat sum into the purse at finalize (#4062)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Gender
from world.currency.models import CharacterPurse, CurrencyTransfer, DistinctionStartingGrant
from world.currency.services import apply_starting_grant
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.serializers import DistinctionListSerializer


class ApplyStartingGrantTests(TestCase):
    def test_pays_the_authored_sum_into_the_purse_as_an_audited_transfer(self):
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(name="Grandmother's Savings")
        DistinctionStartingGrant.objects.create(distinction=distinction, coppers=12_345)
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)

        transfer = apply_starting_grant(char_dist)

        assert transfer is not None
        assert CharacterPurse.objects.get(character_sheet=sheet).balance == 12_345
        assert CurrencyTransfer.objects.filter(pk=transfer.pk, amount=12_345).exists()

    def test_a_distinction_without_a_grant_pays_nothing(self):
        sheet = CharacterSheetFactory()
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=DistinctionFactory())

        assert apply_starting_grant(char_dist) is None
        assert not CharacterPurse.objects.filter(character_sheet=sheet).exists()


class StartingGrantSummaryTests(TestCase):
    def test_the_effects_summary_says_what_the_character_starts_with(self):
        distinction = DistinctionFactory(name="Grandmother's Savings")
        DistinctionStartingGrant.objects.create(distinction=distinction, coppers=1_234)

        texts = [e["text"] for e in DistinctionListSerializer(distinction).data["effects_summary"]]

        assert "Starts with 12g 3s 4c" in texts

    def test_a_distinction_without_a_grant_has_no_such_line(self):
        distinction = DistinctionFactory()

        texts = [e["text"] for e in DistinctionListSerializer(distinction).data["effects_summary"]]

        assert not any(t.startswith("Starts with") for t in texts)


class StartingGrantFinalizeTests(FinalizationTestMixin, TestCase):
    """A picked inheritance lands in the finalized character's purse."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="inheritor")
        self._setup_finalization_base(self, prefix="Inheritance", height_min=700, height_max=800)
        Gender.objects.get_or_create(key="female", defaults={"display_name": "Female"})

    def test_finalize_pays_the_inheritance_once(self):
        distinction = DistinctionFactory(name="An Inheritance", cost_per_rank=5, max_rank=1)
        DistinctionStartingGrant.objects.create(distinction=distinction, coppers=50_000)
        draft = self._create_base_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": distinction.id,
                "distinction_name": distinction.name,
                "distinction_slug": distinction.slug,
                "category_slug": distinction.category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            }
        ]
        draft.save(update_fields=["draft_data"])

        character = finalize_character(draft, add_to_roster=True)

        purse = CharacterPurse.objects.get(character_sheet=character.sheet_data)
        assert purse.balance == 50_000
        assert CurrencyTransfer.objects.filter(to_purse=purse).count() == 1
