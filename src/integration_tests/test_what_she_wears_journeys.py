"""Journeys for what a character wears counting with her gods (#4520, slice 3 of #4462).

Linnet worships the Highwind, a wind spirit that favors the Kestrel facet. Corwen, a tailor
she has shared scenes with for months, makes her a riding coat marked as made for her; she
commissions his Kestrel work and writes the coat's name herself. She also wears a Kestrel
brooch bought off a stall for a great deal of silver. Every step goes through the real
commands and actions (`craft create`, `give`, `market/commission`, `wear`, `invoke`,
`check ... /invoke`, `sacrifice`) and reads back the ease, the record the GM's page shows,
the earning rate, and what the pieces fed her once the trickle has run.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse, transfer
from world.items.constants import BodyRegion, EquipmentLayer, MeaningSignalKind
from world.items.crafting.constants import CraftingRecipeKind
from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.market.models import CraftingServiceOffer
from world.items.models import ItemInstance, ItemTemplate
from world.items.services.meaning import item_meaning
from world.magic.constants import TargetKind
from world.magic.factories import CharacterResonanceFactory, FacetFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.services.gain import outfit_daily_trickle_for_character
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTierFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory
from world.traits.models import Trait
from world.worship.constants import BeingResonanceTier, FavorAwardKind
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import earning_rate
from world.worship.invocation_services import get_devotion_config
from world.worship.models import FavorInvocation, WorshipDeclaration


def _carry(item: ItemInstance, holder) -> None:
    """The prop for an item built by a factory, carried by ``holder``."""
    obj = ObjectDBFactory(db_key=item.display_name, db_typeclass_path="typeclasses.objects.Object")
    obj.db_location = holder
    obj.save(update_fields=["db_location"])
    item.game_object = obj
    item.save(update_fields=["game_object"])


class WearingWhatTheWindFavors(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.shop = self.make_room("Corwen's Shop")
        self.profile = RoomProfileFactory(objectdb=self.shop)
        install_full_lab_station(self.profile)
        wire_enchanting_crafting(base_difficulty=0)
        coat_template = ItemTemplate.objects.get(name="Craftable Dagger")
        coat_template.facet_capacity = 2
        coat_template.save(update_fields=["facet_capacity"])
        TemplateSlotFactory(
            template=coat_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
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
        CharacterRelationshipFactory(
            source=self.sheet, target=self.corwen.sheet_data, scene_depth=150, tier=2
        )
        CharacterRelationshipFactory(
            source=self.corwen.sheet_data, target=self.sheet, scene_depth=100, tier=1
        )
        self.ok = CheckOutcomeFactory(name="Ok", success_level=2)

        # The Highwind: favors the Kestrel facet (ease 2 and 1% a point) and the Gale resonance.
        self.highwind = WorshippedBeingFactory(name="Highwind", resonance_pool=0)
        self.kestrel_row = BeingFacetFactory(
            being=self.highwind,
            facet=self.kestrel,
            invocation_ease_points=2,
            earning_bonus_percent=1,
        )
        self.gale = ResonanceFactory(name="Gale")
        BeingResonanceFactory(
            being=self.highwind, resonance=self.gale, tier=BeingResonanceTier.FAVORED
        )
        self.cliff = self.make_room("The Cliff Shrine")
        ShrineDetailsFactory(
            feature_instance__room_profile=RoomProfileFactory(objectdb=self.cliff),
            being=self.highwind,
        )
        WorshipDeclaration.objects.create(character_sheet=self.sheet, public_being=self.highwind)
        DevotionStandingFactory(character_sheet=self.sheet, being=self.highwind, favor=20)
        config = get_devotion_config()
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        for kind in (FavorAwardKind.SACRIFICE, FavorAwardKind.INVOCATION):
            FavorOutcomeAwardFactory(config=config, kind=kind, outcome_tier=self.success, amount=4)

    def _commissioned_coat(self) -> ItemInstance:
        with force_check_outcome(self.ok):
            self.telnet(self.corwen, "craft create Craftable Dagger for=Linnet")
        coat = ItemInstance.objects.get(template__name="Craftable Dagger")
        self.telnet(self.corwen, "give Craftable Dagger to Linnet")
        with force_check_outcome(self.ok):
            self.telnet(
                self.linnet,
                f"market/commission {self.offer.pk}={coat.pk},{self.kestrel.pk}"
                ";Highwind Coat;Grey wool, cut for riding.",
            )
        coat.refresh_from_db()
        # Five months on.
        coat.held_since = timezone.now() - timedelta(days=150)
        coat.save(update_fields=["held_since"])
        return coat

    def _bought_brooch(self) -> ItemInstance:
        brooch = ItemInstanceFactory(
            template=ItemTemplateFactory(name="kestrel brooch", value=4000, facet_capacity=1),
            quality_tier=QualityTierFactory(stat_multiplier=Decimal("1.00")),
            holder_character_sheet=self.sheet,
            held_since=timezone.now() - timedelta(days=200),
        )
        TemplateSlotFactory(
            template=brooch.template,
            body_region=BodyRegion.NECK,
            equipment_layer=EquipmentLayer.BASE,
        )
        ItemFacetFactory(
            item_instance=brooch,
            facet=self.kestrel,
            attachment_quality_tier=QualityTierFactory(stat_multiplier=Decimal("1.00")),
        )
        _carry(brooch, self.linnet)
        return brooch

    def _dress(self) -> tuple[ItemInstance, ItemInstance]:
        coat = self._commissioned_coat()
        brooch = self._bought_brooch()
        self.assertIn("You equip", self.telnet(self.linnet, "wear Highwind Coat"))
        self.assertIn("You equip", self.telnet(self.linnet, "wear kestrel brooch"))
        return coat, brooch

    def test_the_commissioned_coat_eases_the_call_and_the_bought_brooch_does_not(self) -> None:
        coat, brooch = self._dress()
        meaning = item_meaning(coat, self.sheet, config=get_devotion_config(), being=self.highwind)
        # Made by a tie 2, made for 1 (Corwen's tie already counted), gift 1, designed 1, carried 1.
        self.assertGreaterEqual(meaning.points, 5)
        self.assertEqual(item_meaning(brooch, self.sheet, config=get_devotion_config()).points, 0)

        told = self.telnet(self.linnet, "invoke Highwind")

        self.assertIn("What you wear: Highwind Coat", told)
        self.assertIn(
            f"Worn: Highwind Coat (Kestrel, favored): {min(meaning.points, 8)} points x 2", told
        )
        self.assertIn(
            "Worn: kestrel brooch (Kestrel, favored): bought; no history beyond holding it", told
        )
        self.assertIn("Wearing these adds", told)
        # The brooch cost forty times the coat and eases nothing.
        self.assertNotIn("What you wear: Highwind Coat, kestrel brooch", told)

    def test_the_real_invocation_is_eased_once_and_the_gm_page_lists_the_coat(self) -> None:
        self._dress()
        room_scene = SceneFactory(room=self.shop, is_active=True)
        SceneParticipationFactory(scene=room_scene, account=self.account_of(self.linnet))
        CheckTypeFactory(name="Perception")

        with force_check_outcome(self.success):
            self.telnet(self.linnet, "check Perception at hard /invoke Highwind")

        invocation = FavorInvocation.objects.get()
        self.assertGreater(invocation.worn_ease, 0)
        (piece,) = invocation.pieces.all()
        self.assertEqual((piece.item_name, piece.facet_name), ("Highwind Coat", "Kestrel"))
        kinds = {s.kind for s in piece.signals.all()}
        self.assertIn(MeaningSignalKind.MADE_BY_TIE, kinds)
        self.assertIn(MeaningSignalKind.MADE_FOR, kinds)
        self.assertIn(MeaningSignalKind.DESIGNED, kinds)

        staff = AccountDB.objects.create_superuser("gmpage", "gm@example.com", "pw-1234567")
        self.client.force_login(staff)
        body = self.client.get(
            f"/admin/arxii/favorinvocation/{invocation.pk}/change/"
        ).content.decode()
        self.assertIn("Highwind Coat", body)
        self.assertIn("Kestrel (the gate; ease 2 per point)", body)
        self.assertNotIn("kestrel brooch", body)

    def test_the_earning_rate_rises_while_worn_and_falls_when_she_takes_it_off(self) -> None:
        self._dress()
        raised = earning_rate(self.sheet, self.highwind)
        self.assertGreater(raised, 100)

        self.telnet(self.linnet, "remove Highwind Coat")

        self.assertEqual(earning_rate(self.sheet, self.highwind), 100)
        self.assertNotIn("What you wear", self.telnet(self.linnet, "invoke Highwind"))

    def test_resonance_the_coat_fed_her_counts_and_giving_it_up_removes_the_ease(self) -> None:
        coat, _brooch = self._dress()
        resonance = self.gale
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=resonance, balance=0, lifetime_earned=0
        )
        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_facet=self.kestrel,
            level=3,
            developed_points=0,
        )
        config = get_devotion_config()
        before = item_meaning(coat, self.sheet, config=config, being=self.highwind).points

        # Ten daily trickles pay her for both Kestrel pieces; only the coat's history counts.
        for _day in range(10):
            self.assertEqual(outfit_daily_trickle_for_character(self.sheet), 2)
        after = item_meaning(coat, self.sheet, config=config, being=self.highwind)
        fed = {s.kind: s.points for s in after.signals}.get(MeaningSignalKind.RESONANCE_FED, 0)
        self.assertGreater(fed, 0)
        self.assertEqual(after.points, before + fed)
        brooch_meaning = item_meaning(
            ItemInstance.objects.get(template__name="kestrel brooch"),
            self.sheet,
            config=config,
            being=self.highwind,
        )
        self.assertEqual(brooch_meaning.points, 0)  # fed her too, but it has no history

        # She gives the coat up at the cliff shrine: its signals, resonance fed among them,
        # are kept on the offering, and what she wears no longer carries its ease.
        self.linnet.location = self.cliff
        with force_check_outcome(self.success):
            told = self.telnet(self.linnet, "sacrifice Highwind Coat")
        self.assertIn("resonance fed", told.lower())
        self.assertNotIn(
            "What you wear: Highwind Coat", self.telnet(self.linnet, "invoke Highwind")
        )
        self.assertEqual(earning_rate(self.sheet, self.highwind), 100)
