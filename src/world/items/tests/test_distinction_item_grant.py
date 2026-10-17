"""Keepsake: a distinction that mints an item into the inventory at finalize (#4398)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Gender
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.serializers import DistinctionListSerializer
from world.items.factories import DistinctionItemGrantFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.narrative_grants import apply_item_grants


class ApplyItemGrantsTests(TestCase):
    def test_mints_the_authored_keepsake_into_the_holders_inventory(self):
        sheet = CharacterSheetFactory()
        pendant = ItemTemplateFactory(name="A Chimera Pendant")
        distinction = DistinctionFactory(name="A Mother's Keepsake")
        DistinctionItemGrantFactory(distinction=distinction, item_template=pendant)
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)

        minted = apply_item_grants(char_dist)

        assert [item.template for item in minted] == [pendant]
        assert (
            ItemInstance.objects.filter(holder_character_sheet=sheet, template=pendant).count() == 1
        )

    def test_a_kit_is_several_rows(self):
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(name="A Burglar's Kit")
        picks = ItemTemplateFactory(name="Lockpicks")
        cloak = ItemTemplateFactory(name="A Dark Cloak")
        DistinctionItemGrantFactory(distinction=distinction, item_template=picks)
        DistinctionItemGrantFactory(distinction=distinction, item_template=cloak)
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)

        apply_item_grants(char_dist)

        held = ItemInstance.objects.filter(holder_character_sheet=sheet)
        assert sorted(held.values_list("template__name", flat=True)) == [
            "A Dark Cloak",
            "Lockpicks",
        ]

    def test_a_retired_template_is_not_minted(self):
        sheet = CharacterSheetFactory()
        retired = ItemTemplateFactory(name="A Withdrawn Trinket", is_active=False)
        distinction = DistinctionFactory(name="An Old Keepsake")
        DistinctionItemGrantFactory(distinction=distinction, item_template=retired)
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=distinction)

        assert apply_item_grants(char_dist) == []
        assert not ItemInstance.objects.filter(holder_character_sheet=sheet).exists()

    def test_a_distinction_without_a_grant_mints_nothing(self):
        sheet = CharacterSheetFactory()
        char_dist = CharacterDistinctionFactory(character=sheet, distinction=DistinctionFactory())

        assert apply_item_grants(char_dist) == []
        assert not ItemInstance.objects.filter(holder_character_sheet=sheet).exists()


class ItemGrantSummaryTests(TestCase):
    def test_the_effects_summary_says_what_the_character_comes_with(self):
        distinction = DistinctionFactory(name="A Mother's Keepsake")
        DistinctionItemGrantFactory(
            distinction=distinction, item_template=ItemTemplateFactory(name="A Chimera Pendant")
        )
        texts = [e["text"] for e in DistinctionListSerializer(distinction).data["effects_summary"]]
        assert "Comes with A Chimera Pendant" in texts

    def test_a_retired_template_is_not_advertised(self):
        distinction = DistinctionFactory(name="An Old Keepsake")
        DistinctionItemGrantFactory(
            distinction=distinction,
            item_template=ItemTemplateFactory(name="A Withdrawn Trinket", is_active=False),
        )
        texts = [e["text"] for e in DistinctionListSerializer(distinction).data["effects_summary"]]
        assert not any(t.startswith("Comes with") for t in texts)

    def test_a_distinction_without_a_grant_has_no_such_line(self):
        distinction = DistinctionFactory()
        texts = [e["text"] for e in DistinctionListSerializer(distinction).data["effects_summary"]]
        assert not any(t.startswith("Comes with") for t in texts)


class ItemGrantFinalizeTests(FinalizationTestMixin, TestCase):
    """A picked keepsake is in the finalized character's inventory, once."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="keepsake_holder")
        self._setup_finalization_base(self, prefix="Keepsake", height_min=700, height_max=800)
        Gender.objects.get_or_create(key="female", defaults={"display_name": "Female"})

    def test_finalize_mints_the_keepsake_once(self):
        pendant = ItemTemplateFactory(name="A Chimera Pendant")
        distinction = DistinctionFactory(name="A Mother's Keepsake", cost_per_rank=5, max_rank=1)
        DistinctionItemGrantFactory(distinction=distinction, item_template=pendant)
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

        held = ItemInstance.objects.filter(
            holder_character_sheet=character.sheet_data, template=pendant
        )
        assert held.count() == 1
