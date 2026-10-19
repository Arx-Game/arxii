"""Journeys through the things a character carries (#3657, tranche 8).

Ysmay picks things up and drops them, wears and packs them, uses what she
carries, and hands things over; a GM grants her a keepsake. Each journey types
what a player types through the command handler, or sends the typed dispatch
the web menu sends, and asserts what the player was told, what the room heard,
and what the rows hold.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from actions.constants import TargetKind
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointPool
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import has_condition, register_detection
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem, ItemInstance, Outfit, OutfitSlot
from world.magic.constants import GiftKind, TargetKind as ThreadTargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique, TechniqueGrant, Thread
from world.progression.models import TechniqueKnownRequirement

NOT_HERE = "Could not find '{}'."


def sheet_of(character: ObjectDB):
    return character.sheet_data


def held_item(character: ObjectDB, name: str, **fields) -> ItemInstance:
    """An item in *character*'s hands: a game object in their inventory and a row they hold."""
    instance_fields = {key: fields.pop(key) for key in ("charges", "is_open") if key in fields}
    obj = ObjectDBFactory(db_key=name, location=character)
    return ItemInstanceFactory(
        template=ItemTemplateFactory(name=name, **fields),
        game_object=obj,
        holder_character_sheet=sheet_of(character),
        **instance_fields,
    )


def floor_item(room: ObjectDB, name: str, **fields) -> ItemInstance:
    """An item lying in *room* that nobody owns."""
    obj = ObjectDBFactory(db_key=name, location=room)
    return ItemInstanceFactory(template=ItemTemplateFactory(name=name, **fields), game_object=obj)


def wearable(character: ObjectDB, name: str) -> ItemInstance:
    """A held item whose template has a torso slot, authored before the item exists, the
    way an authored template is: the template caches its slots on first read."""
    template = ItemTemplateFactory(name=name)
    TemplateSlotFactory(
        template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
    )
    template.__dict__.pop("cached_slots", None)
    obj = ObjectDBFactory(db_key=name, location=character)
    return ItemInstanceFactory(
        template=template, game_object=obj, holder_character_sheet=sheet_of(character)
    )


def holder_of(item: ItemInstance) -> int | None:
    return ItemInstance.objects.filter(pk=item.pk).values_list("holder_character_sheet_id").get()[0]


def inside(item: ItemInstance) -> int | None:
    return ItemInstance.objects.filter(pk=item.pk).values_list("contained_in_id").get()[0]


def charges_of(item: ItemInstance) -> int:
    return ItemInstance.objects.filter(pk=item.pk).values_list("charges", flat=True).get()


def where(item: ItemInstance) -> ObjectDB | None:
    return ObjectDB.objects.get(pk=item.game_object_id).location


def worn_by(character: ObjectDB, item: ItemInstance) -> bool:
    return EquippedItem.objects.filter(character=sheet_of(character), item_instance=item).exists()


def effect_pool(condition_name: str, *, on: str = "self"):
    """A one-consequence pool whose effect applies the named condition."""
    pool = ConsequencePoolFactory()
    consequence = ConsequenceFactory(label=f"{condition_name} effect")
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type="apply_condition",
        target=on,
        condition_template=ConditionTemplateFactory(name=condition_name),
    )
    return pool


def items_wire(item: ItemInstance) -> dict:
    return {"kind": "items", "target_id": item.pk}


class PickingUpAndPuttingDown(JourneyCase):
    """Ysmay picks a lantern off the floor of the Lantern and sets it down again."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.lantern = floor_item(self.room, "Brass Lantern")
        self.watch(self.hobb)

    def test_she_picks_it_up_carries_it_and_drops_it(self) -> None:
        self.assertIn("You are not carrying anything.", self.telnet(self.ysmay, "inventory"))
        self.assertIn("You pick up Brass Lantern.", self.telnet(self.ysmay, "get Brass Lantern"))
        self.assertTold(self.hobb, "Ysmay picks up Brass Lantern.")
        self.assertEqual(where(self.lantern), self.ysmay)
        self.assertEqual(holder_of(self.lantern), sheet_of(self.ysmay).pk)
        self.assertIn("You are carrying: Brass Lantern", self.telnet(self.ysmay, "i"))

        self.assertIn("You drop Brass Lantern.", self.telnet(self.ysmay, "drop Brass Lantern"))
        self.assertTold(self.hobb, "Ysmay drops Brass Lantern.")
        self.assertEqual(where(self.lantern), self.room)
        # Setting a thing down does not disown it.
        self.assertEqual(holder_of(self.lantern), sheet_of(self.ysmay).pk)

        self.assertIn("You pick up Brass Lantern.", self.telnet(self.ysmay, "take Brass Lantern"))
        self.assertEqual(where(self.lantern), self.ysmay)

    def test_what_is_not_hers_and_what_is_not_there(self) -> None:
        purse = held_item(self.hobb, "Leather Purse")
        self.assertIn("You drop Leather Purse.", self.telnet(self.hobb, "drop Leather Purse"))
        self.assertIn("That belongs to someone else.", self.telnet(self.ysmay, "get Leather Purse"))
        self.assertEqual(where(purse), self.room)
        self.assertIn("You pick up Leather Purse.", self.telnet(self.hobb, "get Leather Purse"))

        self.assertIn("Get what?", self.telnet(self.ysmay, "get"))
        self.assertIn("Drop what?", self.telnet(self.ysmay, "drop"))
        # An absent name is answered once (Evennia's own search used to say it too).
        told = self.telnet(self.ysmay, "get Nothing")
        self.assertEqual(told.count(NOT_HERE.format("Nothing")), 1, told)
        self.assertIn(NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "drop Nothing"))
        # Two of a name: Evennia's numbered list, and nothing is picked up.
        floor_item(self.room, "Brass Lantern")
        told = self.telnet(self.ysmay, "get Brass Lantern")
        self.assertIn("More than one match for 'Brass Lantern' (please narrow target):", told)
        self.assertNotIn("Could not find", told)
        self.assertEqual(where(self.lantern), self.room)
        # A thing on the floor is not hers to drop, and a plain object is not an item.
        self.assertIn(
            NOT_HERE.format("Brass Lantern"), self.telnet(self.ysmay, "drop Brass Lantern")
        )
        ObjectDBFactory(db_key="Loose Stone", location=self.room)
        self.assertIn("That can't be picked up.", self.telnet(self.ysmay, "get Loose Stone"))

    def test_the_web_names_the_thing_by_its_row(self) -> None:
        picked = self.web(self.ysmay, "get", menu_target=items_wire(self.lantern))
        self.assertTrue(picked.detail.success, picked.detail.message)
        self.assertEqual(where(self.lantern), self.ysmay)
        dropped = self.web(self.ysmay, "drop", menu_target=items_wire(self.lantern))
        self.assertTrue(dropped.detail.success, dropped.detail.message)
        self.assertEqual(where(self.lantern), self.room)

        purse = held_item(self.hobb, "Leather Purse")
        self.telnet(self.hobb, "drop Leather Purse")
        refused = self.web(self.ysmay, "get", menu_target=items_wire(purse))
        self.assertFalse(refused.detail.success)
        self.assertIn("That belongs to someone else.", refused.detail.message)
        nothing = self.web(self.ysmay, "get", menu_target={"kind": "items", "target_id": 999999999})
        self.assertFalse(nothing.detail.success)
        self.assertIn("That isn't available.", nothing.detail.message)


class DressingAndPacking(JourneyCase):
    """Ysmay wears a shirt, packs a bag, and finds out what will not go where."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.shirt = wearable(self.ysmay, "Linen Shirt")
        self.bag = held_item(
            self.ysmay,
            "Canvas Bag",
            is_container=True,
            container_capacity=2,
            container_max_item_size=5,
            supports_open_close=True,
            is_open=True,
        )
        self.coin = held_item(self.ysmay, "Brass Coin", size=1)
        self.watch(self.hobb)

    def test_she_wears_the_shirt_and_takes_it_off(self) -> None:
        self.assertIn("You equip Linen Shirt.", self.telnet(self.ysmay, "wear Linen Shirt"))
        self.assertTold(self.hobb, "Ysmay equips Linen Shirt.")
        self.assertTrue(worn_by(self.ysmay, self.shirt))

        self.assertIn("You remove Linen Shirt.", self.telnet(self.ysmay, "remove Linen Shirt"))
        self.assertTold(self.hobb, "Ysmay removes Linen Shirt.")
        self.assertFalse(worn_by(self.ysmay, self.shirt))
        self.assertIn("You are not wearing that.", self.telnet(self.ysmay, "remove Linen Shirt"))

        self.assertIn("Wear what?", self.telnet(self.ysmay, "wear"))
        self.assertIn("Remove what?", self.telnet(self.ysmay, "remove"))
        self.assertIn(NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "wear Nothing"))
        ObjectDBFactory(db_key="Pebble", location=self.ysmay)
        self.assertIn("That can't be equipped.", self.telnet(self.ysmay, "wear Pebble"))
        self.assertIn("That can't be removed.", self.telnet(self.ysmay, "remove Pebble"))

        # Dropped while worn, the shirt comes off and lands on the floor.
        self.telnet(self.ysmay, "wear Linen Shirt")
        self.assertIn("You drop Linen Shirt.", self.telnet(self.ysmay, "drop Linen Shirt"))
        self.assertEqual(where(self.shirt), self.room)
        self.assertFalse(worn_by(self.ysmay, self.shirt))

    def test_a_saved_outfit_is_worn_by_name(self) -> None:
        wardrobe = held_item(self.ysmay, "Cedar Wardrobe", is_wardrobe=True, is_container=True)
        OutfitFactory(character_sheet=sheet_of(self.ysmay), wardrobe=wardrobe, name="Court Attire")
        self.assertIn(
            "You change into Court Attire.", self.telnet(self.ysmay, "wear outfit Court Attire")
        )
        self.assertTold(self.hobb, "Ysmay changes into Court Attire.")
        self.assertIn(
            "You change into Court Attire.", self.telnet(self.ysmay, "wear OUTFIT court attire")
        )
        self.assertIn(
            "You have no outfit named 'Nothing'.", self.telnet(self.ysmay, "wear outfit Nothing")
        )

    def test_undress_takes_everything_off(self) -> None:
        self.telnet(self.ysmay, "wear Linen Shirt")
        self.assertTrue(worn_by(self.ysmay, self.shirt))
        self.telnet(self.ysmay, "undress")
        self.assertFalse(worn_by(self.ysmay, self.shirt))
        self.assertEqual(where(self.shirt), self.ysmay)

    def test_she_packs_the_bag_and_unpacks_it(self) -> None:
        told = self.telnet(self.ysmay, "put Brass Coin in Canvas Bag")
        self.assertIn("You put Brass Coin into Canvas Bag.", told)
        self.assertTold(self.hobb, "Ysmay puts Brass Coin into Canvas Bag.")
        self.assertEqual(inside(self.coin), self.bag.pk)
        self.assertEqual(where(self.coin), self.bag.game_object)
        self.assertNotIn("Brass Coin", self.telnet(self.ysmay, "inventory"))

        told = self.telnet(self.ysmay, "withdraw Brass Coin from Canvas Bag")
        self.assertIn("You take Brass Coin out.", told)
        self.assertTold(self.hobb, "Ysmay takes Brass Coin out.")
        self.assertIsNone(inside(self.coin))
        self.assertEqual(where(self.coin), self.ysmay)

        self.telnet(self.ysmay, "put Brass Coin in Canvas Bag")
        self.assertIn(
            "You take Brass Coin out.", self.telnet(self.ysmay, "get Brass Coin from Canvas Bag")
        )
        self.assertIsNone(inside(self.coin))

    def test_what_will_not_go_in(self) -> None:
        self.assertIn(
            "That isn't a container.", self.telnet(self.ysmay, "put Brass Coin in Linen Shirt")
        )
        ObjectDBFactory(db_key="Pebble", location=self.ysmay)
        self.assertIn(
            "That isn't a container.", self.telnet(self.ysmay, "put Brass Coin in Pebble")
        )
        self.bag.is_open = False
        self.bag.save(update_fields=["is_open"])
        self.assertIn(
            "That container is closed.", self.telnet(self.ysmay, "put Brass Coin in Canvas Bag")
        )
        self.bag.is_open = True
        self.bag.save(update_fields=["is_open"])
        anvil = held_item(self.ysmay, "Iron Anvil", size=9)
        self.assertIn(
            "That item is too large to fit in there.",
            self.telnet(self.ysmay, "put Iron Anvil in Canvas Bag"),
        )
        self.assertIsNone(inside(anvil))
        held_item(self.ysmay, "Copper Coin", size=1)
        held_item(self.ysmay, "Tin Coin", size=1)
        self.telnet(self.ysmay, "put Brass Coin in Canvas Bag")
        self.telnet(self.ysmay, "put Copper Coin in Canvas Bag")
        self.assertIn(
            "That container is already full.", self.telnet(self.ysmay, "put Tin Coin in Canvas Bag")
        )

        self.assertIn("Put what in what?", self.telnet(self.ysmay, "put"))
        self.assertIn("Usage: put <item> in <container>", self.telnet(self.ysmay, "put Brass Coin"))
        self.assertIn("Withdraw what?", self.telnet(self.ysmay, "withdraw"))
        self.assertIn(
            "Usage: withdraw <item> from <container>", self.telnet(self.ysmay, "withdraw Tin Coin")
        )
        self.assertIn(
            "Could not find 'Tin Coin' in 'Canvas Bag'.",
            self.telnet(self.ysmay, "withdraw Tin Coin from Canvas Bag"),
        )
        self.assertIn(
            NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "put Tin Coin in Nothing")
        )
        # Hobb cannot reach into a bag she carries.
        self.assertIn(
            NOT_HERE.format("Canvas Bag"), self.telnet(self.hobb, "get Brass Coin from Canvas Bag")
        )

    def test_the_web_wears_and_packs_by_row(self) -> None:
        worn = self.web(self.ysmay, "equip", menu_target=items_wire(self.shirt))
        self.assertTrue(worn.detail.success, worn.detail.message)
        self.assertTrue(worn_by(self.ysmay, self.shirt))
        removed = self.web(self.ysmay, "unequip", menu_target=items_wire(self.shirt))
        self.assertTrue(removed.detail.success, removed.detail.message)
        self.assertFalse(worn_by(self.ysmay, self.shirt))
        again = self.web(self.ysmay, "unequip", menu_target=items_wire(self.shirt))
        self.assertFalse(again.detail.success)
        self.assertIn("That isn't available.", again.detail.message)

        packed = self.web(
            self.ysmay, "put_in", menu_target=items_wire(self.coin), container_item_id=self.bag.pk
        )
        self.assertTrue(packed.detail.success, packed.detail.message)
        self.assertEqual(inside(self.coin), self.bag.pk)
        # A packed thing is named with the bag it sits in; bare, it is out of scope.
        bare = self.web(self.ysmay, "take_out", menu_target=items_wire(self.coin))
        self.assertFalse(bare.detail.success)
        self.assertIn("That isn't available.", bare.detail.message)
        unpacked = self.web(
            self.ysmay,
            "take_out",
            menu_target={**items_wire(self.coin), "container_item_id": self.bag.pk},
        )
        self.assertTrue(unpacked.detail.success, unpacked.detail.message)
        self.assertIsNone(inside(self.coin))
        not_a_bag = self.web(
            self.ysmay, "put_in", menu_target=items_wire(self.coin), container_item_id=self.shirt.pk
        )
        self.assertFalse(not_a_bag.detail.success)
        self.assertIn("That isn't available.", not_a_bag.detail.message)


class UsingWhatSheCarries(JourneyCase):
    """Ysmay drinks a draught, salves a friend, and studies a grimoire."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.warmed = ConditionTemplateFactory(name="Warmed")
        self.soothed = ConditionTemplateFactory(name="Soothed")
        self.draught = held_item(
            self.ysmay,
            "Warming Draught",
            is_consumable=True,
            max_charges=2,
            on_use_pool=effect_pool("Warmed"),
            on_use_check_type=None,
            charges=2,
        )
        self.salve = held_item(
            self.ysmay,
            "Soothing Salve",
            is_consumable=True,
            max_charges=2,
            on_use_pool=effect_pool("Soothed", on="target"),
            on_use_check_type=None,
            on_use_target_kind=TargetKind.CHARACTER,
            charges=2,
        )
        self.rock = held_item(self.ysmay, "Plain Rock")
        self.watch(self.hobb)

    def test_a_draught_is_drunk_until_it_runs_out(self) -> None:
        self.assertIn("You use Warming Draught.", self.telnet(self.ysmay, "use Warming Draught"))
        self.assertTold(self.hobb, "Ysmay uses Warming Draught.")
        self.assertTrue(has_condition(self.ysmay, self.warmed))
        self.assertEqual(charges_of(self.draught), 1)
        self.assertIn("You use Warming Draught.", self.telnet(self.ysmay, "use Warming Draught"))
        # The last swallow destroys the draught; there is nothing left to use.
        self.assertFalse(ItemInstance.objects.in_play().filter(pk=self.draught.pk).exists())
        self.assertIn(
            NOT_HERE.format("Warming Draught"), self.telnet(self.ysmay, "use Warming Draught")
        )

    def test_what_cannot_be_used_or_is_not_in_hand(self) -> None:
        self.assertIn("That item can't be used.", self.telnet(self.ysmay, "use Plain Rock"))
        held_item(
            self.ysmay,
            "Empty Vial",
            is_consumable=True,
            max_charges=1,
            on_use_pool=effect_pool("Nothing much"),
            on_use_check_type=None,
            charges=0,
        )
        self.assertIn("That item has no uses left.", self.telnet(self.ysmay, "use Empty Vial"))
        self.assertIn("Use what?", self.telnet(self.ysmay, "use"))
        self.assertIn(NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "use Nothing"))
        self.telnet(self.ysmay, "drop Warming Draught")
        self.assertIn("You aren't holding that.", self.telnet(self.ysmay, "use Warming Draught"))
        self.assertIn("You aren't holding that.", self.telnet(self.hobb, "use Warming Draught"))
        self.assertEqual(charges_of(self.draught), 2)

    def test_a_salve_is_for_someone_else(self) -> None:
        self.assertIn("Use it on what?", self.telnet(self.ysmay, "use Soothing Salve"))
        self.assertIn(
            "That can't be used on others.", self.telnet(self.ysmay, "use Warming Draught on Hobb")
        )
        self.assertIn(
            "That can only be used on a character.",
            self.telnet(self.ysmay, "use Soothing Salve on Plain Rock"),
        )
        self.assertIn(
            "You use Soothing Salve.", self.telnet(self.ysmay, "apply Soothing Salve on Hobb")
        )
        self.assertTold(self.hobb, "Ysmay uses Soothing Salve.")
        self.assertTrue(has_condition(self.hobb, self.soothed))
        self.assertFalse(has_condition(self.ysmay, self.soothed))
        self.assertEqual(charges_of(self.salve), 1)

        hidden = ConditionTemplateFactory(
            name="Shrouded", category=ConditionCategoryFactory(conceals_from_perception=True)
        )
        ConditionInstanceFactory(target=self.hobb, condition=hidden)
        self.assertIn("You can't see that.", self.telnet(self.ysmay, "use Soothing Salve on Hobb"))
        self.assertEqual(charges_of(self.salve), 1)

        elsewhere = self.make_room("The Yard")
        self.hobb.location = elsewhere
        self.hobb.save()
        self.assertIn(
            NOT_HERE.format("Hobb"), self.telnet(self.ysmay, "use Soothing Salve on Hobb")
        )

    def test_a_whetstone_is_for_a_blade(self) -> None:
        keen = ConditionTemplateFactory(name="Keen")
        held_item(
            self.ysmay,
            "Whetstone",
            on_use_pool=effect_pool("Keen", on="target"),
            on_use_check_type=None,
            on_use_target_kind=TargetKind.ITEM,
        )
        dagger = held_item(self.ysmay, "Dagger")
        self.assertIn(
            "You can't use that on that.", self.telnet(self.ysmay, "use Whetstone on Hobb")
        )
        self.assertIn("You use Whetstone.", self.telnet(self.ysmay, "use Whetstone on Dagger"))
        self.assertTrue(has_condition(dagger.game_object, keen))
        # A whetstone is not spent; it is used again and again.
        self.assertIn("You use Whetstone.", self.telnet(self.ysmay, "use Whetstone on Dagger"))

    def test_a_grimoire_teaches_only_what_she_is_ready_for(self) -> None:
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 200
        pool.save()
        gift = GiftFactory(name="Emberwork", kind=GiftKind.MINOR)
        resonance = ResonanceFactory()
        gift.resonances.add(resonance)
        CharacterGift.objects.create(character=sheet_of(self.ysmay), gift=gift)
        Thread.objects.create(
            owner=sheet_of(self.ysmay),
            resonance=resonance,
            target_kind=ThreadTargetKind.GIFT,
            target_gift=gift,
            level=0,
        )
        lance = TechniqueFactory(gift=gift, name="Ember Lance")
        advanced = TechniqueFactory(gift=gift, name="Ember Storm")
        TechniqueKnownRequirement.objects.create(
            technique=advanced,
            required_technique=TechniqueFactory(name="Cinder Step"),
            is_active=True,
        )
        sunfall = UltimateTechniqueFactory(gift=gift, name="Sunfall")

        def grimoire(name: str, technique) -> ItemInstance:
            item = held_item(
                self.ysmay,
                name,
                is_consumable=True,
                max_charges=1,
                on_use_pool=effect_pool(f"{name} glow"),
                on_use_check_type=None,
                charges=1,
            )
            TechniqueGrant.objects.create(
                technique=technique, item_template=item.template, verb="study"
            )
            return item

        primer = grimoire("Ember Primer", lance)
        sealed = grimoire("Sealed Grimoire", advanced)
        forbidden = grimoire("Sunfall Codex", sunfall)

        self.assertIn("You use Ember Primer.", self.telnet(self.ysmay, "use Ember Primer"))
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=sheet_of(self.ysmay), technique=lance
            ).exists()
        )
        self.assertFalse(ItemInstance.objects.in_play().filter(pk=primer.pk).exists())

        self.assertIn(
            "You have not yet met what this technique requires: Need to know Cinder Step",
            self.telnet(self.ysmay, "use Sealed Grimoire"),
        )
        self.assertEqual(charges_of(sealed), 1)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=sheet_of(self.ysmay), technique=advanced
            ).exists()
        )

        self.assertIn(
            "That technique can only be used in Audere.",
            self.telnet(self.ysmay, "use Sunfall Codex"),
        )
        self.assertEqual(charges_of(forbidden), 1)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=sheet_of(self.ysmay), technique=sunfall
            ).exists()
        )

    def test_the_web_uses_by_row_and_names_the_target_by_object(self) -> None:
        drunk = self.web(self.ysmay, "use_item", menu_target=items_wire(self.draught))
        self.assertTrue(drunk.detail.success, drunk.detail.message)
        self.assertEqual(drunk.detail.data["charges_remaining"], 1)
        self.assertTrue(has_condition(self.ysmay, self.warmed))

        salved = self.web(
            self.ysmay,
            "use_item",
            menu_target=items_wire(self.salve),
            use_target={"kind": "objects", "target_id": self.hobb.pk},
        )
        self.assertTrue(salved.detail.success, salved.detail.message)
        self.assertTrue(has_condition(self.hobb, self.soothed))

        rock = self.web(self.ysmay, "use_item", menu_target=items_wire(self.rock))
        self.assertFalse(rock.detail.success)
        self.assertIn("That item can't be used.", rock.detail.message)


class HandingThingsOver(JourneyCase):
    """Ysmay gives Hobb a coin; Ravenna, a Junior GM, grants her a keepsake."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.ravenna = self.make_player("Ravenna", room=self.room)
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.JUNIOR)
        self.coin = held_item(self.ysmay, "Brass Coin")
        self.watch(self.hobb)

    def test_a_coin_changes_hands_in_the_room(self) -> None:
        self.assertIn(
            "You give Brass Coin to Hobb.", self.telnet(self.ysmay, "give Brass Coin to Hobb")
        )
        self.assertTold(self.hobb, "Ysmay gives Brass Coin to")
        self.assertEqual(holder_of(self.coin), sheet_of(self.hobb).pk)
        self.assertEqual(where(self.coin), self.hobb)
        self.assertIn("You are carrying: Brass Coin", self.telnet(self.hobb, "inventory"))

        self.assertIn("Give what to whom?", self.telnet(self.ysmay, "give"))
        self.assertIn(
            "Usage: give <item> to <recipient>", self.telnet(self.ysmay, "give Brass Coin")
        )
        self.assertIn(NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "give Nothing to Hobb"))
        self.assertIn(
            NOT_HERE.format("Brass Coin"), self.telnet(self.ysmay, "give Brass Coin to Hobb")
        )
        self.assertIn(
            NOT_HERE.format("Nobody"), self.telnet(self.hobb, "give Brass Coin to Nobody")
        )

        # A worn shirt comes off as it is handed over.
        shirt = wearable(self.ysmay, "Linen Shirt")
        self.telnet(self.ysmay, "wear Linen Shirt")
        self.assertIn(
            "You give Linen Shirt to Hobb.", self.telnet(self.ysmay, "give Linen Shirt to Hobb")
        )
        self.assertFalse(worn_by(self.ysmay, shirt))
        self.assertEqual(where(shirt), self.hobb)

    def test_the_web_names_the_recipient_by_face(self) -> None:
        given = self.web(
            self.ysmay,
            "give",
            menu_target=items_wire(self.coin),
            recipient_persona_id=sheet_of(self.hobb).primary_persona.pk,
        )
        self.assertTrue(given.detail.success, given.detail.message)
        self.assertEqual(holder_of(self.coin), sheet_of(self.hobb).pk)
        to_herself = self.web(
            self.hobb,
            "give",
            menu_target=items_wire(self.coin),
            recipient_persona_id=sheet_of(self.hobb).primary_persona.pk,
        )
        self.assertFalse(to_herself.detail.success)
        self.assertIn("That isn't available.", to_herself.detail.message)

    def test_a_gm_grants_a_keepsake(self) -> None:
        locket = ItemTemplateFactory(name="Silver Locket")
        told = self.telnet(self.ravenna, "grant_item Ysmay=Silver Locket")
        self.assertIn("Granted 'Silver Locket' to Ysmay.", told)
        self.assertTrue(
            ItemInstance.objects.filter(
                template=locket, holder_character_sheet=sheet_of(self.ysmay)
            ).exists()
        )
        usage = "Usage: grant_item <character>=<item template name>"
        self.assertIn(usage, self.telnet(self.ravenna, "grant_item"))
        self.assertIn(usage, self.telnet(self.ravenna, "grant_item Ysmay"))
        self.assertIn(
            "No item template found named 'Nothing'.",
            self.telnet(self.ravenna, "grant_item Ysmay=Nothing"),
        )
        # Once, and typed: the action's own line, not Evennia's bare one (tranche 10). The
        # frames are what the web composer receives for the typed line.
        box = self.mailbox(self.ravenna)
        first_frame = len(box.calls)
        self.assertEqual(
            NOT_HERE.format("Nobody"),
            self.telnet(self.ravenna, "grant_item Nobody=Silver Locket").strip(),
        )
        self.assertEqual(
            box.calls[first_frame:], [(((NOT_HERE.format("Nobody"), {"type": "error"}),), {})]
        )
        ObjectDBFactory(db_key="Pebble", location=self.room)
        self.assertIn(
            "That is not a character.", self.telnet(self.ravenna, "grant_item Pebble=Silver Locket")
        )

        self.assertIn(
            "GM trust required.", self.telnet(self.hobb, "grant_item Ysmay=Silver Locket")
        )
        GMProfileFactory(account=self.account_of(self.hobb), level=GMLevel.STARTING)
        self.assertIn(
            "Requires Junior GM or higher.",
            self.telnet(self.hobb, "grant_item Ysmay=Silver Locket"),
        )
        self.assertEqual(ItemInstance.objects.filter(template=locket).count(), 1)

        dagny = self.make_player("Dagny", room=self.room)
        account = self.account_of(dagny)
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        self.assertIn(
            "Granted 'Silver Locket' to Hobb.", self.telnet(dagny, "grant_item Hobb=Silver Locket")
        )


class LookingAtThings(JourneyCase):
    """Ysmay looks at what Hobb wears and what sits in a bag; what she cannot see, she is
    told is not there, in the same words whether it is hidden or absent."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.shirt = wearable(self.hobb, "Linen Shirt")
        self.telnet(self.hobb, "wear Linen Shirt")
        self.bag = held_item(
            self.ysmay, "Canvas Bag", is_container=True, supports_open_close=True, is_open=True
        )
        self.coin = held_item(self.ysmay, "Brass Coin", size=1)
        self.telnet(self.ysmay, "put Brass Coin in Canvas Bag")

    def test_she_looks_at_what_he_wears_and_what_her_bag_holds(self) -> None:
        self.assertIn(
            "Linen Shirt\nA Linen Shirt.", self.telnet(self.ysmay, "look Hobb's Linen Shirt")
        )
        self.assertIn(
            "Linen Shirt\nA Linen Shirt.", self.telnet(self.ysmay, "look Linen Shirt on Hobb")
        )
        self.assertIn(
            "You don't see anything by that name on Hobb.",
            self.telnet(self.ysmay, "look Hobb's Crown"),
        )
        self.assertIn(
            "Brass Coin\nA Brass Coin.", self.telnet(self.ysmay, "look Brass Coin in Canvas Bag")
        )
        self.assertIn(
            "You don't see anything by that name in the Canvas Bag.",
            self.telnet(self.ysmay, "look Ruby in Canvas Bag"),
        )
        self.bag.is_open = False
        self.bag.save(update_fields=["is_open"])
        self.assertIn(
            "That container is closed.", self.telnet(self.ysmay, "look Brass Coin in Canvas Bag")
        )
        ObjectDBFactory(db_key="Pebble", location=self.ysmay)
        self.assertIn(
            "That isn't a container.", self.telnet(self.ysmay, "look Brass Coin in Pebble")
        )
        # A plain look at a thing in the room, and at a thing that is not there.
        floor_item(self.room, "Brass Lantern")
        self.assertIn("Brass Lantern", self.telnet(self.ysmay, "look Brass Lantern"))
        # Once, not twice: the plain look had let Evennia's search say it first, as a
        # bare untyped line the web composer could not place, before the command's
        # own typed error. The frames are what a typed line sends the session, on
        # telnet and on the web alike: the one text line typed ``error`` and the
        # structured ``command_error`` frame a CommandError always carries, no bare line.
        box = self.mailbox(self.ysmay)
        first_frame = len(box.calls)
        self.assertEqual(
            NOT_HERE.format("Nothing"), self.telnet(self.ysmay, "look Nothing").strip()
        )
        self.assertEqual(
            box.calls[first_frame:],
            [
                (((NOT_HERE.format("Nothing"), {"type": "error"}),), {}),
                (
                    (None,),
                    {
                        "command_error": {
                            "error": NOT_HERE.format("Nothing"),
                            "command": "look Nothing",
                        }
                    },
                ),
            ],
        )
        self.assertEqual(
            NOT_HERE.format("Nobody's hat"), self.telnet(self.ysmay, "look Nobody's hat").strip()
        )

    def test_a_thing_named_like_a_drilled_form_is_still_found(self) -> None:
        floor_item(self.room, "Bob's Hat")
        floor_item(self.room, "Bob in Armor")
        self.assertIn("Bob's Hat", self.telnet(self.ysmay, "look Bob's Hat"))
        self.assertIn("Bob in Armor", self.telnet(self.ysmay, "look Bob in Armor"))

    def test_a_hidden_hobb_is_not_there_until_she_sees_him(self) -> None:
        hidden = ConditionTemplateFactory(
            name="Shrouded", category=ConditionCategoryFactory(conceals_from_perception=True)
        )
        ConditionInstanceFactory(target=self.hobb, condition=hidden)
        self.assertIn(
            NOT_HERE.format("Hobb's Linen Shirt"),
            self.telnet(self.ysmay, "look Hobb's Linen Shirt"),
        )
        self.assertIn(
            NOT_HERE.format("Linen Shirt on Hobb"),
            self.telnet(self.ysmay, "look Linen Shirt on Hobb"),
        )
        # A prefix of his name, in lower case, is answered in the words an absent name gets.
        self.assertEqual(
            self.telnet(self.ysmay, "look hob").strip(),
            self.telnet(self.ysmay, "look nob").strip().replace("nob", "hob"),
        )
        self.assertEqual(NOT_HERE.format("hob"), self.telnet(self.ysmay, "look hob").strip())
        register_detection(sheet_of(self.ysmay), self.hobb)
        self.assertIn(
            "Linen Shirt\nA Linen Shirt.", self.telnet(self.ysmay, "look Hobb's Linen Shirt")
        )

    def test_a_hidden_bag_is_not_there_either(self) -> None:
        self.telnet(self.ysmay, "drop Canvas Bag")
        hidden = ConditionTemplateFactory(
            name="Shrouded", category=ConditionCategoryFactory(conceals_from_perception=True)
        )
        ConditionInstanceFactory(target=self.bag.game_object, condition=hidden)
        self.assertIn(
            NOT_HERE.format("Brass Coin in Canvas Bag"),
            self.telnet(self.hobb, "look Brass Coin in Canvas Bag"),
        )


class KeepingAWardrobe(JourneyCase):
    """Ysmay saves what she wears as an outfit, edits it, wears it back and lets it go."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.shirt = wearable(self.ysmay, "Linen Shirt")
        self.wardrobe = held_item(self.ysmay, "Cedar Wardrobe", is_wardrobe=True, is_container=True)
        self.watch(self.hobb)

    def slots_of(self, outfit: Outfit) -> list[tuple[int, str, str]]:
        return list(
            OutfitSlot.objects.filter(outfit=outfit).values_list(
                "item_instance_id", "body_region", "equipment_layer"
            )
        )

    def test_an_outfit_is_saved_edited_worn_and_deleted(self) -> None:
        self.assertIn("You have no saved outfits.", self.telnet(self.ysmay, "outfit"))
        usage = "Usage: outfit save <name> wardrobe=<id>"
        self.assertIn(usage, self.telnet(self.ysmay, "outfit save"))
        self.assertIn(usage, self.telnet(self.ysmay, "outfit save Court Attire"))
        # Once, not twice: the dbref search had said "Could not find" first.
        self.assertEqual(
            "You aren't holding that wardrobe.",
            self.telnet(self.ysmay, "outfit save Court Attire wardrobe=999999").strip(),
        )

        # What she wears now is the outfit.
        self.telnet(self.ysmay, "wear Linen Shirt")
        self.assertIn(
            "Saved outfit 'Court Attire'.",
            self.telnet(
                self.ysmay, f"outfit save Court Attire wardrobe={self.wardrobe.game_object_id}"
            ),
        )
        outfit = Outfit.objects.get(character_sheet=sheet_of(self.ysmay), name="Court Attire")
        self.assertEqual(
            self.slots_of(outfit), [(self.shirt.pk, BodyRegion.TORSO, EquipmentLayer.BASE)]
        )
        hub = self.telnet(self.ysmay, "outfit list")
        self.assertIn("Your saved outfits:", hub)
        self.assertIn(f"#{outfit.pk}", hub)
        self.assertIn("Court Attire", hub)

        # Renamed, a slot taken out and put back.
        self.assertIn(
            "Renamed to 'Gala Dress'.",
            self.telnet(self.ysmay, f"outfit rename {outfit.pk}=Gala Dress"),
        )
        self.assertIn("No such outfit.", self.telnet(self.ysmay, "outfit rename 999999=Nothing"))
        self.assertIn(usage, self.telnet(self.ysmay, "outfit rename abc=Nothing"))
        self.assertIn(usage, self.telnet(self.ysmay, f"outfit rename {outfit.pk}="))
        self.assertIn(
            "Slot removed.",
            self.telnet(self.ysmay, f"outfit removeslot {outfit.pk} region=torso layer=base"),
        )
        self.assertEqual(self.slots_of(outfit), [])
        self.assertIn(usage, self.telnet(self.ysmay, f"outfit removeslot {outfit.pk} region=torso"))
        self.assertIn(
            "Slot added.",
            self.telnet(
                self.ysmay,
                f"outfit addslot {outfit.pk} item={self.shirt.game_object_id} "
                "region=torso layer=base",
            ),
        )
        self.assertEqual(
            self.slots_of(outfit), [(self.shirt.pk, BodyRegion.TORSO, EquipmentLayer.BASE)]
        )
        self.assertEqual(
            "You aren't holding that item.",
            self.telnet(
                self.ysmay, f"outfit addslot {outfit.pk} item=999999 region=torso layer=base"
            ).strip(),
        )
        self.assertIn(usage, self.telnet(self.ysmay, f"outfit addslot {outfit.pk} item=1"))

        # Worn back by number, the room watching; undressed the same way.
        self.telnet(self.ysmay, "remove Linen Shirt")
        self.assertFalse(worn_by(self.ysmay, self.shirt))
        self.telnet(self.ysmay, f"outfit wear {outfit.pk}")
        self.assertTold(self.hobb, "Ysmay changes into Gala Dress.")
        self.assertTrue(worn_by(self.ysmay, self.shirt))
        self.assertIn(usage, self.telnet(self.ysmay, "outfit wear abc"))
        self.assertIn(
            "That outfit no longer exists.", self.telnet(self.ysmay, "outfit wear 999999")
        )
        self.telnet(self.ysmay, "outfit undress")
        self.assertTold(self.hobb, "Ysmay undresses.")
        self.assertFalse(worn_by(self.ysmay, self.shirt))

        # Presenting needs an event that exists; deleting leaves the clothes alone.
        self.assertIn(
            "Usage: outfit present <id> event=<event id>.",
            self.telnet(self.ysmay, f"outfit present {outfit.pk}"),
        )
        self.assertIn(
            "That event no longer exists.",
            self.telnet(self.ysmay, f"outfit present {outfit.pk} event=999999"),
        )
        self.assertIn("Outfit deleted.", self.telnet(self.ysmay, f"outfit delete {outfit.pk}"))
        self.assertFalse(Outfit.objects.filter(pk=outfit.pk).exists())
        self.assertTrue(ItemInstance.objects.filter(pk=self.shirt.pk).exists())
        self.assertIn(
            "Unknown outfit action 'frobnicate'.", self.telnet(self.ysmay, "outfit frobnicate")
        )
