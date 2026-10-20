"""Journeys for commissioning a piece that means something (#4512, slice 2 of #4462).

Corwen is a tailor with a shop. Linnet worships the Highwind, whose shrine is on the cliff.
He makes her a coat marked as made for her, she commissions his Kestrel facet work and
writes the coat's name and description herself, she shows it, and she gives it up. Bracken
the cobbler works his grandfather's saddle into boots for his son Abel. Every step goes
through the real commands and actions (`craft create`, `give`, `market/commission`,
`showcase`, `look`, `sacrifice`) and reads back the rows and what the players were told.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse, transfer
from world.items.constants import MeaningSignalKind, OwnershipEventType
from world.items.crafting.constants import CraftingRecipeKind
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.market.models import CraftingServiceOffer
from world.items.models import ItemInstance, ItemLineage, ItemTemplate, OwnershipEvent
from world.items.services.crafted_display import crafted_provenance_line
from world.items.services.fashion_showcase import (
    record_showcase_showing,
    record_showing_engagement,
    settle_fashion_showings,
)
from world.items.services.meaning import item_meaning
from world.magic.factories import FacetFactory
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTierFactory
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory
from world.traits.models import Trait
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    FavorOutcomeAwardFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import WorshipDeclaration


def _give_object(item: ItemInstance, holder) -> None:
    """The prop for an item built by a factory, carried by ``holder``."""
    obj = ObjectDBFactory(db_key=item.display_name, db_typeclass_path="typeclasses.objects.Object")
    obj.db_location = holder
    obj.save(update_fields=["db_location"])
    item.game_object = obj
    item.save(update_fields=["game_object"])


class CommissioningACoat(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.shop = self.make_room("Corwen's Shop")
        self.profile = RoomProfileFactory(objectdb=self.shop)
        install_full_lab_station(self.profile)
        wire_enchanting_crafting(base_difficulty=0)
        coat_template = ItemTemplate.objects.get(name="Craftable Dagger")
        coat_template.facet_capacity = 2
        coat_template.save(update_fields=["facet_capacity"])
        self.corwen = self.make_player("Corwen", room=self.shop)
        self.linnet = self.make_player("Linnet", room=self.shop)
        self.watch(self.corwen, self.linnet)
        self.sheet = self.linnet.sheet_data
        CharacterTraitValueFactory(
            character=self.corwen.sheet_data, trait=Trait.objects.get(name="Enchanting"), value=50
        )
        self.kestrel = FacetFactory(name="Kestrel")
        self.offer = CraftingServiceOffer.objects.create(
            crafter_persona=self.corwen.sheet_data.primary_persona,
            recipe_kind=CraftingRecipeKind.FACET_ATTACH,
            shop_room=self.profile,
            fee=40,
        )
        transfer(amount=500, reason="a purse", to_purse=get_or_create_purse(self.sheet))
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        # Months of shared scenes: the pair's depth reaches tier 2, and Linnet's own side of
        # the tie is claimed to tier 2.
        CharacterRelationshipFactory(
            source=self.sheet, target=self.corwen.sheet_data, scene_depth=150, tier=2
        )
        CharacterRelationshipFactory(
            source=self.corwen.sheet_data, target=self.sheet, scene_depth=100, tier=1
        )
        self.ok = CheckOutcomeFactory(name="Ok", success_level=2)

        # The Highwind's shrine is on the cliff; Linnet worships it.
        self.cliff = self.make_room("The Cliff Shrine")
        self.highwind = WorshippedBeingFactory(name="Highwind", resonance_pool=0)
        ShrineDetailsFactory(
            feature_instance__room_profile=RoomProfileFactory(objectdb=self.cliff),
            being=self.highwind,
        )
        WorshipDeclaration.objects.create(character_sheet=self.sheet, public_being=self.highwind)
        config = get_devotion_config()
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.SACRIFICE, outcome_tier=self.success, amount=4
        )

    def _coat(self) -> ItemInstance:
        return ItemInstance.objects.get(template__name="Craftable Dagger")

    def test_a_coat_made_for_her_commissioned_shown_and_given_up(self) -> None:
        # Corwen makes it, marked as made for Linnet, and leaves the design to her.
        with force_check_outcome(self.ok):
            self.telnet(self.corwen, "craft create Craftable Dagger for=Linnet")
        coat = self._coat()
        self.assertEqual(coat.dedicated_to_persona, self.sheet.primary_persona)
        self.assertEqual(coat.dedicated_by_persona, self.corwen.sheet_data.primary_persona)
        self.assertIsNone(coat.designer_character_sheet)  # blank text leaves the designer empty

        self.telnet(self.corwen, "give Craftable Dagger to Linnet")
        coat.refresh_from_db()
        self.assertEqual(coat.holder_character_sheet, self.sheet)

        # She commissions his Kestrel work and writes the coat's name and description.
        with force_check_outcome(self.ok):
            told = self.telnet(
                self.linnet,
                f"market/commission {self.offer.pk}={coat.pk},{self.kestrel.pk}"
                ";Highwind Coat;Grey wool, cut for riding.",
            )
        self.assertIn("for 40 coppers", told)
        coat.refresh_from_db()
        self.assertEqual(coat.custom_name, "Highwind Coat")
        self.assertEqual(coat.designer_character_sheet, self.sheet)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 460)

        # Examine credits all three, and nothing about points.
        looked = self.telnet(self.linnet, "look Highwind Coat")
        self.assertIn(
            "Made by Corwen for Linnet. Designed by Linnet. Facet work by Corwen.", looked
        )

        # She shows it at a gathering; four others engage; the week settles.
        self.web(self.linnet, "showcase", mode="piece", item_id=coat.pk)
        showing = record_showcase_showing(self.sheet, scene=None, roll_success=True)
        for _ in range(4):
            record_showing_engagement(showing)
        settle_fashion_showings()

        # Months on, the reader counts every signal.
        coat.held_since = timezone.now() - timedelta(days=30)
        coat.save(update_fields=["held_since"])
        config = get_devotion_config()
        meaning = item_meaning(coat, self.sheet, config=config)
        by_kind = {s.kind: s.points for s in meaning.signals}
        self.assertEqual(
            by_kind,
            {
                MeaningSignalKind.CARRIED: 1,
                MeaningSignalKind.MADE_BY_TIE: 2,
                MeaningSignalKind.GIFT: 1,  # Corwen's tie already counted: the further act
                MeaningSignalKind.MADE_FOR: 1,
                MeaningSignalKind.DESIGNED: 1,
                MeaningSignalKind.SHOWN: 2,
            },
        )

        # She gives it up at the cliff shrine; the signals are read and the piece is kept.
        self.linnet.location = self.cliff
        with force_check_outcome(self.success):
            told = self.telnet(self.linnet, "sacrifice Highwind Coat")
        for needle in ("made by a tie", "made for", "designed", "shown"):
            self.assertIn(needle, told.lower())
        gone = ItemInstance.objects.get(pk=coat.pk)
        self.assertIsNotNone(gone.destroyed_at)
        line = crafted_provenance_line(gone)
        self.assertIn("Made by Corwen for Linnet. Designed by Linnet. Facet work by Corwen.", line)
        self.assertIn("Gone: Given up to Highwind", line)

    def test_the_fee_alone_never_credits_a_designer(self) -> None:
        coat = ItemInstanceFactory(
            template=ItemTemplateFactory(name="plain coat", facet_capacity=1),
            holder_character_sheet=self.sheet,
            crafter_character_sheet=self.corwen.sheet_data,
        )
        _give_object(coat, self.linnet)

        with force_check_outcome(self.ok):
            self.telnet(
                self.linnet, f"market/commission {self.offer.pk}={coat.pk},{self.kestrel.pk}"
            )

        coat.refresh_from_db()
        self.assertIsNone(coat.designer_character_sheet)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 460)

    def test_the_refusals_are_told_in_words(self) -> None:
        coat = ItemInstanceFactory(
            template=ItemTemplateFactory(name="plain coat", facet_capacity=2),
            holder_character_sheet=self.sheet,
            crafter_character_sheet=self.corwen.sheet_data,
            custom_name="Corwen's Coat",
            designer_character_sheet=self.corwen.sheet_data,
        )
        _give_object(coat, self.linnet)
        head = f"market/commission {self.offer.pk}={coat.pk},{self.kestrel.pk}"

        self.assertIn("so you cannot write over it", self.telnet(self.linnet, f"{head};Mine now"))
        self.assertIn(
            "A piece can only be made for someone else.",
            self.telnet(self.linnet, f"{head};;;Linnet"),
        )
        with force_check_outcome(self.ok):
            self.telnet(self.linnet, f"{head};;;Corwen")
        self.assertIn("already made for someone", self.telnet(self.linnet, f"{head};;;Corwen"))
        self.assertIn("No one called 'Nobody'.", self.telnet(self.linnet, f"{head};;;Nobody"))
        self.assertEqual(get_or_create_purse(self.sheet).balance, 460)  # one fee, not four
        self.assertIn(
            "A piece can only be made for someone else.",
            self.telnet(self.corwen, "craft create Craftable Dagger for=Corwen"),
        )


class WorkingAnHeirloomIn(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.workshop = self.make_room("The Cobbler's Bench")
        self.profile = RoomProfileFactory(objectdb=self.workshop)
        install_full_lab_station(self.profile)
        wire_enchanting_crafting(base_difficulty=0)
        self.bracken = self.make_player("Bracken", room=self.workshop)
        self.abel = self.make_player("Abel", room=self.workshop)
        self.watch(self.bracken, self.abel)
        CharacterTraitValueFactory(
            character=self.bracken.sheet_data,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        CharacterRelationshipFactory(
            source=self.abel.sheet_data, target=self.bracken.sheet_data, scene_depth=350, tier=3
        )
        CharacterRelationshipFactory(
            source=self.bracken.sheet_data, target=self.abel.sheet_data, scene_depth=0, tier=3
        )
        self.ok = CheckOutcomeFactory(name="Ok", success_level=2)

    def test_boots_worked_from_the_saddle_for_his_son(self) -> None:
        saddle = ItemInstanceFactory(
            template=ItemTemplateFactory(name="worn saddle"),
            holder_character_sheet=self.bracken.sheet_data,
            held_since=timezone.now() - timedelta(days=2200),
        )
        OwnershipEvent.objects.create(
            item_instance=saddle,
            event_type=OwnershipEventType.INHERITED,
            from_character_sheet=self.abel.sheet_data,
            to_character_sheet=self.bracken.sheet_data,
        )
        _give_object(saddle, self.bracken)

        with force_check_outcome(self.ok):
            self.telnet(
                self.bracken,
                f"craft create Craftable Dagger=Riding Boots for=Abel from={saddle.pk}",
            )

        boots = ItemInstance.objects.get(custom_name="Riding Boots")
        saddle.refresh_from_db()
        self.assertIsNotNone(saddle.destroyed_at)
        row = ItemLineage.objects.get(item=boots)
        self.assertEqual((row.source_item, row.source_name), (saddle, "worn saddle"))
        self.assertGreater(row.points, 0)

        # The boots go to Abel; they count the maker's tie, the dedication and the saddle.
        self.telnet(self.bracken, "give Riding Boots to Abel")
        boots.refresh_from_db()
        boots.held_since = timezone.now() - timedelta(days=20)
        boots.save(update_fields=["held_since"])
        meaning = item_meaning(boots, self.abel.sheet_data, config=get_devotion_config())
        by_kind = {s.kind: s.points for s in meaning.signals}
        self.assertEqual(by_kind[MeaningSignalKind.MADE_FROM], min(row.points, 3))
        self.assertIn(MeaningSignalKind.MADE_FOR, by_kind)
        self.assertIn(MeaningSignalKind.MADE_BY_TIE, by_kind)

        looked = self.telnet(self.abel, "look Riding Boots")
        self.assertIn("Made and designed by Bracken for Abel.", looked)
        self.assertIn("Worked from worn saddle, which is gone.", looked)
