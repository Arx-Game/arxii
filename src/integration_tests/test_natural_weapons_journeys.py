"""Journeys for natural weapons (#4898, slice 4 of #4844).

A gift may name a natural weapon: staff point the Khati Claws gift at the "Khati Claws" item
template, an Unarmed weapon worn at the skin layer of both hands with base damage 5. A
character who gains the gift (at creation, or later) gets the claws made and equipped once.
They are part of the body: unequipping, dropping, giving, stealing or trading them is refused
with "That is part of the body and cannot be removed.", and undressing leaves them on. They
sit beside worn gear, since a slot is a region and a layer: a sword in the right hand and
gloves on both hands go on at the base layer while the claws stay on. They cover no skin, so
the hands still feel the sun.

In a fight (``_StrikeField``, the Strike journeys' Steading) the claws are a Strike weapon
listed before bare hands, rolled on "Unarmed Attack", and a landed Strike deals the claws'
own damage: 5 at a Success damage roll (x1), above the Strike's base damage of 3. A Wolf
facet on the claws, with a Wolf thread at shown level 1 and "+2 Strike: base damage" on the
facet, adds 2: the claws take enchantments through the ordinary facet path.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from integration_tests.test_strike_journeys import BARE_HANDS_DAMAGE, _StrikeField
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.combat.services.declarations.strike import strike_weapon_options
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import (
    ItemFacetFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem, ItemInstance
from world.items.services.appearance import covered_regions
from world.magic.constants import GiftKind, TargetKind
from world.magic.factories import FacetFactory, GiftFactory, ResonanceFactory, ThreadFactory
from world.magic.models import FacetEffectBonus
from world.magic.specialization.services import grant_gift_to_character
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.species.factories import SpeciesGiftGrantFactory

CLAWS = "Khati Claws"
CLAWS_DAMAGE = 5
REFUSED = "That is part of the body and cannot be removed."
IN_THE_WAY = "Something that is part of the body is already there."
HANDS = (BodyRegion.LEFT_HAND, BodyRegion.RIGHT_HAND)


def clawed_gift():
    """The Khati Claws gift, naming an Unarmed template at the skin layer of both hands."""
    template = ItemTemplateFactory(
        name=CLAWS,
        gear_archetype=GearArchetype.UNARMED,
        base_weapon_damage=CLAWS_DAMAGE,
        facet_capacity=1,
    )
    for region in HANDS:
        TemplateSlotFactory(
            template=template, body_region=region, equipment_layer=EquipmentLayer.SKIN
        )
    template.__dict__.pop("cached_slots", None)
    gift = GiftFactory(name="Khati Claws", kind=GiftKind.MINOR, natural_weapon_template=template)
    gift.resonances.add(ResonanceFactory())
    return gift


def claws_of(sheet) -> list[ItemInstance]:
    return list(
        ItemInstance.objects.in_play().filter(holder_character_sheet=sheet, template__name=CLAWS)
    )


def worn_slots(sheet, item: ItemInstance) -> set[tuple[str, str]]:
    return set(
        EquippedItem.objects.filter(character=sheet, item_instance=item).values_list(
            "body_region", "equipment_layer"
        )
    )


def hand_wear(character, name: str, *, layer: str) -> ItemInstance:
    """A pair of gloves (or any two-handed hand item) in ``character``'s inventory."""
    from evennia_extensions.factories import ObjectDBFactory
    from world.items.factories import ItemInstanceFactory

    template = ItemTemplateFactory(name=name)
    for region in HANDS:
        TemplateSlotFactory(template=template, body_region=region, equipment_layer=layer)
    template.__dict__.pop("cached_slots", None)
    return ItemInstanceFactory(
        template=template,
        game_object=ObjectDBFactory(db_key=name, location=character),
        holder_character_sheet=character.sheet_data,
    )


class ClawsAtCreation(FinalizationTestMixin, JourneyCase):
    """A Khati finishes character creation with her claws on."""

    def setUp(self) -> None:
        super().setUp()
        from evennia.accounts.models import AccountDB

        self._flush_common_caches()
        self.account = AccountDB.objects.create_user("clawplayer", "claw@test.com", "pw")
        self._setup_finalization_base(self, prefix="Khati", height_min=700, height_max=800)
        # Not ``self.gift``: the mixin's own Major gift lives there.
        SpeciesGiftGrantFactory(species=self.species, gift=clawed_gift())

    def test_finalize_makes_the_claws_equipped_and_strikeable(self) -> None:
        draft = self._create_base_draft(first_name="Ysmay")

        character = finalize_character(draft, add_to_roster=True)

        sheet = character.sheet_data
        (claws,) = claws_of(sheet)
        self.assertEqual(claws.game_object.location, character)
        self.assertEqual(
            worn_slots(sheet, claws), {(region, EquipmentLayer.SKIN) for region in HANDS}
        )
        character.equipped_items.invalidate()
        self.assertEqual(
            [(w.name, w.gear_archetype) for w in strike_weapon_options(character)],
            [(CLAWS, GearArchetype.UNARMED), ("bare hands", GearArchetype.UNARMED)],
        )


class GainingTheGiftInPlay(JourneyCase):
    """Hobb, clawless, gains the Khati Claws gift by being taught or by a staff species edit."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Academy Yard")
        self.hobb = self.make_player("Hobb", room=self.room)
        self.sheet = self.hobb.sheet_data
        self.gift = clawed_gift()

    def test_learning_a_technique_from_the_gift_grants_the_claws_once(self) -> None:
        from world.action_points.models import ActionPointPool
        from world.magic.factories import (
            GiftUnlockFactory,
            TechniqueFactory,
            TechniqueTeachingOfferFactory,
        )
        from world.progression.models.rewards import ExperiencePointsData
        from world.roster.factories import RosterTenureFactory

        ExperiencePointsData.objects.get_or_create(
            account=self.account_of(self.hobb), defaults={"total_earned": 100, "total_spent": 0}
        )
        unlock = GiftUnlockFactory(gift=self.gift, xp_cost=10)
        teacher = RosterTenureFactory()
        for character in (self.hobb, teacher.character):
            pool = ActionPointPool.get_or_create_for_character(character)
            pool.current = 200
            pool.save()
        rake, swipe = (
            TechniqueTeachingOfferFactory(
                teacher=teacher,
                technique=TechniqueFactory(gift=self.gift, name=name),
                learn_ap_cost=5,
                banked_ap=1,
            )
            for name in ("Rake", "Swipe")
        )

        self.telnet(self.hobb, f"learn gift {unlock.pk}")
        self.assertEqual(claws_of(self.sheet), [])
        self.telnet(self.hobb, f"learn technique {rake.pk}")

        (claws,) = claws_of(self.sheet)
        self.assertEqual(
            worn_slots(self.sheet, claws), {(region, EquipmentLayer.SKIN) for region in HANDS}
        )
        self.telnet(self.hobb, f"learn technique {swipe.pk}")
        self.assertEqual(claws_of(self.sheet), [claws])

    def test_a_staff_species_edit_grants_the_claws_once(self) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.species.factories import SpeciesFactory

        khati = SpeciesFactory(name="Khati")
        SpeciesGiftGrantFactory(species=khati, gift=self.gift)
        staff = self.api(AccountFactory(is_staff=True))
        url = f"/api/character-sheets/{self.sheet.pk}/staff-edit/"

        response = staff.patch(url, {"species": khati.pk}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        (claws,) = claws_of(self.sheet)
        self.assertEqual(claws.game_object.location, self.hobb)
        self.assertEqual(
            worn_slots(self.sheet, claws), {(region, EquipmentLayer.SKIN) for region in HANDS}
        )
        again = staff.patch(url, {"species": khati.pk}, format="json")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(claws_of(self.sheet), [claws])


class _ClawedField(_StrikeField):
    """Hobb at the Steading gains the Khati Claws gift (a path or species grant in play)."""

    def setUp(self) -> None:
        super().setUp()
        self.gift = clawed_gift()
        grant_gift_to_character(self.sheet, self.gift)
        (self.claws,) = claws_of(self.sheet)
        self.hobb.equipped_items.invalidate()
        self.wren = self.make_player("Wren", room=self.steading)

    def assert_still_clawed(self) -> None:
        self.assertEqual(claws_of(self.sheet), [self.claws])
        self.assertEqual(self.claws.game_object.location, self.hobb)
        self.assertEqual(
            worn_slots(self.sheet, self.claws),
            {(region, EquipmentLayer.SKIN) for region in HANDS},
        )


class GainingTheGift(_ClawedField):
    def test_gaining_it_again_makes_no_second_pair(self) -> None:
        grant_gift_to_character(self.sheet, self.gift)

        self.assert_still_clawed()

    def test_the_claws_cover_no_skin(self) -> None:
        self.assertEqual(covered_regions(self.hobb) & set(HANDS), set())
        gloves = hand_wear(self.hobb, "Kid Gloves", layer=EquipmentLayer.BASE)
        self.assertIn("You equip Kid Gloves.", self.telnet(self.hobb, "wear Kid Gloves"))

        self.hobb.equipped_items.invalidate()
        self.assertEqual(covered_regions(self.hobb) & set(HANDS), set(HANDS))
        self.assertEqual(
            worn_slots(self.sheet, gloves), {(region, EquipmentLayer.BASE) for region in HANDS}
        )
        self.assert_still_clawed()


class TheClawsNeverComeOff(_ClawedField):
    def test_telnet_remove_drop_and_give_are_refused(self) -> None:
        self.assertIn(REFUSED, self.telnet(self.hobb, f"remove {CLAWS}"))
        self.assertIn(REFUSED, self.telnet(self.hobb, f"drop {CLAWS}"))
        self.assertIn(REFUSED, self.telnet(self.hobb, f"give {CLAWS} to Wren"))

        self.assert_still_clawed()

    def test_web_unequip_drop_and_give_are_refused(self) -> None:
        target = {"kind": "items", "target_id": self.claws.pk}
        for key, extra in (
            ("unequip", {}),
            ("drop", {}),
            ("give", {"recipient_persona_id": self.wren.sheet_data.primary_persona.pk}),
        ):
            result = self.web(self.hobb, key, menu_target=target, **extra)
            self.assertFalse(result.detail.success, key)
            self.assertEqual(result.detail.message, REFUSED, key)

        self.assert_still_clawed()

    def test_nobody_steals_them(self) -> None:
        # Worn gear on a standing character is never on a thief's menu, so Wren is told
        # the claws are not there to take; the natural weapon refusal sits behind that.
        result = self.web(
            self.wren, "steal", menu_target={"kind": "items", "target_id": self.claws.pk}
        )

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "That isn't available.")
        self.assert_still_clawed()

    def test_they_cannot_go_on_the_trade_table(self) -> None:
        proposed = self.web(self.hobb, "propose_trade", target=self.wren.pk)
        self.assertTrue(proposed.detail.success, proposed.detail.message)
        session_id = proposed.detail.data["session_id"]
        accepted = self.web(self.wren, "accept_trade", session_id=session_id)
        self.assertTrue(accepted.detail.success, accepted.detail.message)

        staged = self.web(
            self.hobb, "stage_trade_item", session_id=session_id, target=self.claws.game_object.pk
        )

        self.assertFalse(staged.detail.success)
        self.assertIn(REFUSED, staged.detail.message)
        self.assert_still_clawed()

    def test_undressing_leaves_them_on(self) -> None:
        gloves = hand_wear(self.hobb, "Kid Gloves", layer=EquipmentLayer.BASE)
        self.telnet(self.hobb, "wear Kid Gloves")

        self.telnet(self.hobb, "undress")

        self.assertEqual(worn_slots(self.sheet, gloves), set())
        self.assert_still_clawed()

    def test_a_sword_in_hand_goes_on_beside_them(self) -> None:
        sword = self.equip_sword()

        self.assert_still_clawed()
        self.hobb.equipped_items.invalidate()
        self.assertEqual(
            [w.item_instance for w in strike_weapon_options(self.hobb)],
            [self.claws, sword, None],
        )

    def test_nothing_else_takes_their_layer(self) -> None:
        hand_wear(self.hobb, "Henna Gloves", layer=EquipmentLayer.SKIN)

        self.assertIn(IN_THE_WAY, self.telnet(self.hobb, "wear Henna Gloves"))

        self.assert_still_clawed()


class StrikingWithClaws(_ClawedField):
    def test_the_turn_panel_lists_the_claws_before_bare_hands(self) -> None:
        response = self.api(self.account_of(self.hobb)).get(f"/api/combat/{self.encounter.pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        own = next(
            p for p in response.json()["participants"] if p["character_sheet_id"] == self.sheet.pk
        )
        self.assertEqual(
            own["strike_weapons"],
            [
                {
                    "item_instance_id": self.claws.pk,
                    "name": CLAWS,
                    "gear_kind": "Unarmed",
                    "strike_skill": "Unarmed Combat",
                },
                {
                    "item_instance_id": None,
                    "name": "bare hands",
                    "gear_kind": "Unarmed",
                    "strike_skill": "Unarmed Combat",
                },
            ],
        )

    def test_a_claw_strike_rolls_unarmed_and_deals_the_claws_damage(self) -> None:
        damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=self.claws.pk)

        self.assertEqual(damage, CLAWS_DAMAGE)
        self.assertGreater(damage, BARE_HANDS_DAMAGE)
        self.assertEqual([roll["check_type"] for roll in rolled], [self.unarmed, self.unarmed])

    def test_telnet_strikes_with_the_claws(self) -> None:
        told = self.telnet(self.hobb, f"strike bandit with {CLAWS}")

        self.assertIn(f"You ready a strike at Bandit with your {CLAWS}.", told)

    def test_a_facet_on_the_claws_reaches_the_strike(self) -> None:
        wolf = FacetFactory(name="Wolf")
        ItemFacetFactory(item_instance=self.claws, facet=wolf)
        ThreadFactory(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.FACET,
            target_facet=wolf,
            target_trait=None,
            level=10,
        )
        self.hobb.threads.invalidate()
        target = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name="Strike: base damage",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.STRIKE_BASE_DAMAGE),
        )
        FacetEffectBonus.objects.create(facet=wolf, target=target, amount=2)
        self.hobb.equipped_items.invalidate()

        damage, _rolled = self.strike_and_resolve("Success", "Success", weapon_id=self.claws.pk)

        self.assertEqual(damage, CLAWS_DAMAGE + 2)
