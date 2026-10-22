"""Journeys for the builders: a GM staging props mid-scene, and an owner shaping,
staffing and keeping up a house (#3657 tranche 19).

Every line is typed through the command handler (``JourneyCase.telnet``) or sent
through the web dispatcher (``JourneyCase.web``); the rows asserted are the real
ones the services write. ``room/aura`` is magic ground and stays with its own
tests.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.player_interface import get_player_actions
from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import RoomProfile, RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers
from integration_tests.harness import JourneyCase
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingFactory, BuildingKindFactory, DecorationKindFactory
from world.buildings.models import ArchitecturalStyle, InteriorDesignDetails, ProjectTemplate
from world.conditions.factories import CapabilityTypeFactory
from world.currency.services import get_or_create_purse
from world.items.factories import ItemTemplateFactory, ItemTemplatePropertyFactory
from world.items.models import ItemInstance
from world.locations.constants import HolderType, LocationParentType, LocationRole
from world.locations.models import LocationOwnership, LocationTenancy
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ObjectProperty
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.seeds.checks import seed_check_resolution_tables

ROOM_USAGE_FIRST_LINE = "Usage:"


def room_in_building(case: JourneyCase, name: str, area, *, size: RoomSizeTier, grid=(0, 0, 0)):
    """A room of the building's area, sized and placed on the grid."""
    room = case.make_room(name)
    profile, _ = RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={
            "area": area,
            "size": size,
            "grid_x": grid[0],
            "grid_y": grid[1],
            "floor": grid[2],
        },
    )
    return room, profile


def exits_named(room: ObjectDB) -> list[str]:
    return sorted(
        ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit", db_location=room
        ).values_list("db_key", flat=True)
    )


class StagingAProp(JourneyCase):
    """Ysmay runs the scene in the Long Hall; Hobb and Wren play in it."""

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("The Long Hall")
        self.profile = RoomProfileFactory(objectdb=self.hall)
        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.hobb = self.make_player("Hobb", room=self.hall)
        self.wren = self.make_player("Wren", room=self.hall)
        self.scene = SceneFactory(location=self.profile, is_active=True)
        SceneGMParticipationFactory(scene=self.scene, account=self.account_of(self.ysmay))
        self.torch = ItemTemplateFactory(name="Improv Torch")
        self.flammable = PropertyFactory(name="flammable")
        ItemTemplatePropertyFactory(item_template=self.torch, property=self.flammable)
        self.dark = PropertyFactory(name="dark")
        self.sturdy = PropertyFactory(name="sturdy")

    def staged_torch(self) -> ObjectDB:
        return ItemInstance.objects.get(template=self.torch).game_object

    def test_the_gm_conjures_a_torch_and_tags_the_room(self) -> None:
        self.assertIn("Usage: stage prop", self.telnet(self.ysmay, "stage"))
        self.assertIn(
            "Unknown stage action 'frobnicate'. Try: prop, property.",
            self.telnet(self.ysmay, "stage frobnicate"),
        )
        self.assertIn(
            "Only the scene's GM, owner, or staff may stage a prop.",
            self.telnet(self.hobb, "stage prop Improv Torch"),
        )
        self.assertFalse(ItemInstance.objects.filter(template=self.torch).exists())

        self.assertIn(
            "Usage: stage prop <item template name>.", self.telnet(self.ysmay, "stage prop")
        )
        self.assertIn(
            "No item template named 'Nothing'.", self.telnet(self.ysmay, "stage prop Nothing")
        )
        self.assertIn(
            "You conjure Improv Torch into being.",
            self.telnet(self.ysmay, "stage prop Improv Torch"),
        )
        torch = self.staged_torch()
        self.assertEqual(torch.location, self.hall)
        self.assertTrue(
            ObjectProperty.objects.filter(object=torch, property=self.flammable).exists(),
            "a staged prop carries its template's default properties",
        )

        self.assertIn(
            "Usage: stage property <property name> [=<target>].",
            self.telnet(self.ysmay, "stage property"),
        )
        self.assertIn(
            "No property named 'glowing'.", self.telnet(self.ysmay, "stage property glowing")
        )
        self.assertIn("The Long Hall is now dark.", self.telnet(self.ysmay, "stage property dark"))
        self.assertTrue(
            ObjectProperty.objects.filter(object=self.hall, property=self.dark).exists()
        )
        self.assertIn(
            "Improv Torch is now sturdy.",
            self.telnet(self.ysmay, "stage property sturdy = Improv Torch"),
        )
        self.assertTrue(ObjectProperty.objects.filter(object=torch, property=self.sturdy).exists())
        self.assertIn(
            "Could not find 'Nothing'.", self.telnet(self.ysmay, "stage property sturdy = Nothing")
        )
        self.assertIn(
            "Only the scene's GM, owner, or staff may stage a prop.",
            self.telnet(self.hobb, "stage property dark"),
        )

        # The web sends the same two actions with ids.
        result = self.web(self.ysmay, "stage_property", property="dark", target_id=torch.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "Improv Torch is now dark.")
        result = self.web(self.ysmay, "stage_prop", item_template="Improv Torch")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(ItemInstance.objects.filter(template=self.torch).count(), 2)

    def test_a_staged_torch_offers_ignite_to_the_one_who_can(self) -> None:
        seed_check_resolution_tables()
        capability = CapabilityTypeFactory(name="generation", innate_baseline=0)
        technique = TechniqueFactory(intensity=1)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=capability, base_value=5, intensity_multiplier=0
        )
        CharacterTechniqueFactory(character=self.hobb.sheet_data, technique=technique)
        template = ChallengeTemplateFactory(name="Ignite Torch", severity=3)
        application = ApplicationFactory(
            name="Ignite",
            capability=capability,
            target_property=self.flammable,
            default_template=template,
        )
        ChallengeApproachFactory(
            challenge_template=template, application=application, display_name="Ignite it"
        )

        self.telnet(self.ysmay, "stage prop Improv Torch")
        torch = self.staged_torch()

        def ignites_for(character: ObjectDB) -> list:
            return [
                action
                for action in get_player_actions(character)
                if action.backend == ActionBackend.WORLD_INTERACTION
                and action.ref.target_object_id == torch.pk
            ]

        offered = ignites_for(self.hobb)
        self.assertEqual([action.display_name for action in offered], ["Ignite it"])
        self.assertEqual(ignites_for(self.wren), [], "Wren never learned the technique")


class HouseCase(JourneyCase):
    """The Lantern: a one-room townhouse Ysmay owns, with Hobb standing in it."""

    def setUp(self) -> None:
        super().setUp()
        ensure_room_size_tiers()
        self.modest = RoomSizeTier.objects.get(name="Modest")
        self.snug = RoomSizeTier.objects.get(name="Snug")
        self.area = AreaFactory(name="The Lantern", level=AreaLevel.BUILDING)
        self.building = BuildingFactory(
            area=self.area, kind=BuildingKindFactory(name="Townhouse"), space_budget=100
        )
        self.entry, self.entry_profile = room_in_building(
            self, "Entry Hall", self.area, size=self.modest
        )
        self.building.entry_room = self.entry_profile
        self.building.save(update_fields=["entry_room"])
        self.ysmay = self.make_player("Ysmay", room=self.entry)
        self.hobb = self.make_player("Hobb", room=self.entry)
        self.owner = self.ysmay.sheet_data.primary_persona
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.area,
            holder_type=HolderType.PERSONA,
            holder_persona=self.owner,
        )
        self.purse = get_or_create_purse(self.ysmay.sheet_data)
        self.purse.balance = 1_000
        self.purse.save()


class ShapingTheHouse(HouseCase):
    def test_digging_linking_and_dropping_rooms(self) -> None:
        told = self.telnet(self.ysmay, "room")
        self.assertIn(ROOM_USAGE_FIRST_LINE, told)
        self.assertIn("room/dig <direction>=<name>", told)
        self.assertIn(ROOM_USAGE_FIRST_LINE, self.telnet(self.ysmay, "room/frob something"))

        self.assertIn(
            "Usage: room/dig <direction>=<name> [like=<room>] [size=<tier>]",
            self.telnet(self.ysmay, "room/dig"),
        )
        self.assertIn("The new room needs a name.", self.telnet(self.ysmay, "room/dig west="))
        self.assertIn(
            "'sideways' isn't a direction.", self.telnet(self.ysmay, "room/dig sideways=Nook")
        )
        self.assertIn(
            "Kitchen dug. Space: 50/100.", self.telnet(self.ysmay, "room/dig north=Kitchen")
        )
        kitchen = ObjectDB.objects.get(db_key="Kitchen")
        self.assertEqual(exits_named(self.entry), ["north"])
        self.assertEqual(exits_named(kitchen), ["south"])

        self.telnet(self.ysmay, "north")
        self.assertEqual(self.ysmay.location, kitchen)
        self.assertIn(
            "Loft dug. Space: 60/100.",
            self.telnet(self.ysmay, "room/dig up=Loft like=Entry Hall size=Snug"),
        )
        loft = ObjectDB.objects.get(db_key="Loft")
        self.assertEqual(loft.room_profile.size, self.snug)
        self.assertIn("Room is now Snug. Space: 45/100.", self.telnet(self.ysmay, "room/size Snug"))
        self.assertIn(
            "Pick a size: Micro, Cramped, Snug, Modest,", self.telnet(self.ysmay, "room/size Huge")
        )

        self.assertIn("Type 'room/drop confirm' to proceed.", self.telnet(self.ysmay, "room/drop"))
        self.assertIn(
            "Removing this room would cut off: Loft. Re-link them first.",
            self.telnet(self.ysmay, "room/drop confirm"),
        )
        self.telnet(self.ysmay, "south")
        self.assertIn("Usage: room/addexit", self.telnet(self.ysmay, "room/addexit Loft"))
        self.assertIn(
            "Give both exit names", self.telnet(self.ysmay, "room/addexit Loft=up the ladder")
        )
        self.assertIn(
            "No room named 'Nowhere' in this building.",
            self.telnet(self.ysmay, "room/addexit Nowhere=there,back"),
        )
        self.assertIn(
            "Linked to Loft.",
            self.telnet(self.ysmay, "room/addexit Loft=up the ladder,down the ladder"),
        )
        self.assertEqual(exits_named(self.entry), ["north", "up the ladder"])
        self.assertEqual(exits_named(loft), ["down", "down the ladder"])

        self.assertIn(
            "Usage: room/renameexit", self.telnet(self.ysmay, "room/renameexit up the ladder")
        )
        self.assertIn(
            "Exit renamed.", self.telnet(self.ysmay, "room/renameexit up the ladder=the ladder")
        )
        self.assertEqual(exits_named(self.entry), ["north", "the ladder"])
        self.assertIn("No exit 'nowhere' here.", self.telnet(self.ysmay, "room/removeexit nowhere"))
        # Loft still has its way through the Kitchen, so the ladder may go, and come back.
        self.assertIn("Exit removed.", self.telnet(self.ysmay, "room/removeexit the ladder"))
        self.assertEqual(exits_named(self.entry), ["north"])
        self.assertEqual(exits_named(loft), ["down"])
        self.assertIn(
            "Linked to Loft.",
            self.telnet(self.ysmay, "room/addexit Loft=the ladder,down the ladder"),
        )

        self.telnet(self.ysmay, "north")
        self.assertIn("Room removed.", self.telnet(self.ysmay, "room/drop confirm"))
        self.assertEqual(self.ysmay.location, self.entry)
        self.assertFalse(ObjectDB.objects.filter(pk=kitchen.pk).exists())
        # The dropped room's own exits go with it; they had moved into the entry
        # hall with the rest of its contents and outlived it (tranche 19).
        self.assertEqual(exits_named(self.entry), ["the ladder"])
        self.assertEqual(exits_named(loft), ["down the ladder"])
        self.assertIn(
            "Removing that exit would cut off: Loft. Link them another way first.",
            self.telnet(self.ysmay, "room/removeexit the ladder"),
        )

        self.telnet(self.ysmay, "the ladder")
        self.assertEqual(self.ysmay.location, loft)
        self.assertIn("Room removed.", self.telnet(self.ysmay, "room/drop confirm"))
        self.assertEqual(self.ysmay.location, self.entry)
        self.assertEqual(exits_named(self.entry), [])
        self.assertIn(
            "The entry room can't be removed", self.telnet(self.ysmay, "room/drop confirm")
        )

    def test_naming_describing_and_mapping(self) -> None:
        self.assertIn("Give the new room name.", self.telnet(self.ysmay, "room/name"))
        self.assertIn("Room updated.", self.telnet(self.ysmay, "room/name The Solar"))
        self.assertIn("Give the new description.", self.telnet(self.ysmay, "room/desc"))
        self.assertIn("Room updated.", self.telnet(self.ysmay, "room/desc Warm light, worn rugs."))
        self.assertIn("Warm light, worn rugs.", self.telnet(self.ysmay, "look"))
        self.assertIn("Use 'room/public <yes or no>'.", self.telnet(self.ysmay, "room/public"))
        self.assertIn("Room updated.", self.telnet(self.ysmay, "room/public yes"))
        self.assertTrue(RoomProfile.objects.get(pk=self.entry_profile.pk).is_public)
        self.assertIn("Room updated.", self.telnet(self.ysmay, "build/public no"))
        self.assertFalse(RoomProfile.objects.get(pk=self.entry_profile.pk).is_public)
        self.assertIn("Room updated.", self.telnet(self.ysmay, "manageroom/name The Hall"))
        self.assertIn("/100", self.telnet(self.ysmay, "room/map"))

    def test_a_stranger_may_not_restructure(self) -> None:
        for line in (
            "room/dig north=Cellar",
            "room/size Snug",
            "room/name The Squat",
            "room/addexit Nowhere=a,b",
            "room/drop confirm",
        ):
            told = self.telnet(self.hobb, line)
            self.assertNotIn("Room updated.", told)
            self.assertNotIn("dug.", told)
            self.assertTrue(told.strip(), f"{line!r} answered nothing")
        self.assertFalse(ObjectDB.objects.filter(db_key="Cellar").exists())
        self.assertEqual(RoomProfile.objects.get(pk=self.entry_profile.pk).size, self.modest)


class KeepingTheHousehold(HouseCase):
    def grants_for(self, character: ObjectDB) -> list[str]:
        persona = character.sheet_data.primary_persona
        return sorted(
            LocationTenancy.objects.filter(
                room_profile=self.entry_profile, tenant_persona=persona, ends_at__isnull=True
            ).values_list("kind", flat=True)
        )

    def test_keys_tenancies_and_evictions(self) -> None:
        self.assertIn("Usage: room/key <character>", self.telnet(self.ysmay, "room/key"))
        self.assertIn("Usage: room/tenant <character>", self.telnet(self.ysmay, "room/tenant"))
        self.assertIn("Usage: room/trustee <character>", self.telnet(self.ysmay, "room/trustee"))
        told = self.telnet(self.ysmay, "room/key Nobody")
        self.assertEqual(told.count("Could not find 'Nobody'."), 1, told)

        self.assertIn("Hobb now holds a key here.", self.telnet(self.ysmay, "room/key Hobb"))
        self.assertEqual(self.grants_for(self.hobb), [LocationRole.GUEST])
        self.assertIn("Hobb is now a tenant here.", self.telnet(self.ysmay, "room/tenant Hobb"))
        self.assertIn("Hobb is now a trustee here.", self.telnet(self.ysmay, "room/trustee Hobb"))
        self.assertEqual(
            self.grants_for(self.hobb),
            sorted([LocationRole.GUEST, LocationRole.TENANT, LocationRole.TRUSTEE]),
        )

        self.assertIn("Usage: room/evict <character>", self.telnet(self.ysmay, "room/evict"))
        self.assertIn("Tenancy ended.", self.telnet(self.ysmay, "room/evict Hobb"))
        self.assertEqual(
            self.grants_for(self.hobb), sorted([LocationRole.GUEST, LocationRole.TENANT])
        )
        self.assertIn("Tenancy ended.", self.telnet(self.ysmay, "room/evict Hobb"))
        self.assertEqual(self.grants_for(self.hobb), [LocationRole.GUEST])
        self.assertIn("Tenancy ended.", self.telnet(self.ysmay, "room/evict Hobb"))
        self.assertEqual(self.grants_for(self.hobb), [])
        self.assertIn("Hobb holds no grant here.", self.telnet(self.ysmay, "room/evict Hobb"))

    def test_a_tenant_redescribes_and_calls_it_home(self) -> None:
        told = self.telnet(self.hobb, "room/home")
        self.assertNotIn("This is home now.", told)
        self.assertTrue(told.strip())
        self.assertIn("Hobb is now a tenant here.", self.telnet(self.ysmay, "room/tenant Hobb"))
        self.assertIn("Room updated.", self.telnet(self.hobb, "room/desc A tenant's touch."))
        told = self.telnet(self.hobb, "room/dig north=Cellar")
        self.assertNotIn("dug.", told)
        self.assertIn("This is home now.", self.telnet(self.hobb, "room/home"))
        self.assertTrue(
            LocationTenancy.objects.filter(
                room_profile=self.entry_profile,
                tenant_persona=self.hobb.sheet_data.primary_persona,
                is_primary_home=True,
            ).exists()
        )
        self.assertIn("This is home now.", self.telnet(self.ysmay, "room/home"))
        self.assertTrue(
            LocationTenancy.objects.filter(
                room_profile=self.entry_profile, tenant_persona=self.owner, is_primary_home=True
            ).exists(),
            "the owner's home is minted as her own tenancy",
        )


class KeepingTheHouseUp(HouseCase):
    def setUp(self) -> None:
        super().setUp()
        DecorationKindFactory(name="Great Hearth")
        ProjectTemplate.objects.create(name="Gilded Hall", base_cost=10)
        ArchitecturalStyle.objects.create(name="Antique Imperial", is_default=True)
        BuildingKindFactory(name="Workshop")

    def test_fixtures_extensions_decoration_and_style(self) -> None:
        self.assertIn("Pick a fixture: Great Hearth.", self.telnet(self.ysmay, "room/fixture"))
        self.assertIn("Great Hearth placed.", self.telnet(self.ysmay, "room/fixture Great Hearth"))
        self.assertIn(
            "Great Hearth removed.", self.telnet(self.ysmay, "room/removefixture Great Hearth")
        )
        self.assertIn(
            "No 'Great Hearth' fixture here.",
            self.telnet(self.ysmay, "room/removefixture Great Hearth"),
        )

        self.assertIn(
            "The extension must add at least one unit of space.",
            self.telnet(self.ysmay, "room/extend many"),
        )
        told = self.telnet(self.ysmay, "room/extend 50")
        extension = Project.objects.get(kind=ProjectKind.BUILDING_EXTENSION)
        self.assertIn(f"Extension project #{extension.pk} opened (+50 units on completion).", told)
        self.assertEqual(extension.owner_persona, self.owner)

        self.assertIn(
            "Usage: room/decorate <template> [here]", self.telnet(self.ysmay, "room/decorate")
        )
        self.assertIn(
            "No decoration template named 'Nothing'.",
            self.telnet(self.ysmay, "room/decorate Nothing"),
        )
        told = self.telnet(self.ysmay, "room/decorate Gilded Hall here")
        design = InteriorDesignDetails.objects.get(room=self.entry_profile)
        self.assertIn(f"'Gilded Hall' commissioned (project #{design.project_id}).", told)
        told = self.telnet(self.ysmay, "room/decorate Gilded Hall")
        self.assertTrue(
            InteriorDesignDetails.objects.filter(room=None, building=self.building).exists()
        )
        self.assertIn("'Gilded Hall' commissioned", told)

        self.assertIn("Pick a style: Antique Imperial.", self.telnet(self.ysmay, "room/style"))
        self.assertIn(
            "No style named 'Brutalist'.", self.telnet(self.ysmay, "room/style Brutalist")
        )
        self.assertIn(
            "The Lantern is now built in the Antique Imperial style.",
            self.telnet(self.ysmay, "room/style Antique Imperial"),
        )

        self.assertIn("Renovate to: Workshop", self.telnet(self.ysmay, "room/renovate"))
        self.assertIn(
            "The building is already of that kind.",
            self.telnet(self.ysmay, "room/renovate Townhouse"),
        )
        self.assertIn(
            "No building kind named 'Palace'.", self.telnet(self.ysmay, "room/renovate Palace")
        )
        told = self.telnet(self.ysmay, "room/renovate Workshop")
        self.assertIn("'Workshop' renovation commissioned (project #", told)

    def test_the_condition_of_the_house(self) -> None:
        told = self.telnet(self.ysmay, "room/settle")
        self.assertIn("Condition: Excellent.", told)
        self.assertIn("Confirm to settle.", told)
        self.assertIn(
            "Nothing is owed on this building.", self.telnet(self.ysmay, "room/settle confirm")
        )
        self.building.upkeep_arrears = 40
        self.building.save(update_fields=["upkeep_arrears"])
        self.assertIn("Arrears owed: 40 coppers.", self.telnet(self.ysmay, "room/settle"))
        self.assertIn(
            "You settle 40 coppers of back upkeep.", self.telnet(self.ysmay, "room/settle confirm")
        )
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 960)

        self.assertIn("Refurbishing to Excellent costs", self.telnet(self.ysmay, "room/refurbish"))
        self.assertIn(
            "The building is already in excellent condition.",
            self.telnet(self.ysmay, "room/refurbish confirm"),
        )
        self.building.condition_tier = ConditionTier.WORN
        self.building.save(update_fields=["condition_tier"])
        self.assertIn("Condition: Worn.", self.telnet(self.ysmay, "room/refurbish"))
        self.assertIn(
            "Insufficient funds: 9g 6s on hand.",
            self.telnet(self.ysmay, "room/refurbish confirm"),
        )
        self.purse.balance = 1_000_000
        self.purse.save()
        self.assertIn(
            "restored to excellent condition.", self.telnet(self.ysmay, "room/refurbish confirm")
        )
        self.building.refresh_from_db()
        self.assertEqual(self.building.condition_tier, ConditionTier.EXCELLENT)

        self.assertIn("A grand preparation will take", self.telnet(self.ysmay, "room/prepare"))
        told = self.telnet(self.ysmay, "room/prepare confirm")
        preparation = Project.objects.get(kind=ProjectKind.BUILDING_PREPARATION)
        self.assertIn(
            f"The household begins the grand preparation (project #{preparation.pk}).", told
        )
        self.assertIn(
            f"A grand preparation is already underway (project #{preparation.pk}).",
            self.telnet(self.ysmay, "room/prepare confirm"),
        )

        self.assertIn("Ultra upkeep engaged", self.telnet(self.ysmay, "room/ultraupkeep"))
        self.assertIn("Ultra upkeep: ON.", self.telnet(self.ysmay, "room/settle"))
        self.assertIn("Ultra upkeep discontinued.", self.telnet(self.ysmay, "room/ultraupkeep"))

        for line in ("room/settle", "room/refurbish confirm", "room/ultraupkeep"):
            told = self.telnet(self.hobb, line)
            self.assertNotIn("Condition:", told)
            self.assertNotIn("Ultra upkeep", told)
            self.assertTrue(told.strip(), f"{line!r} answered nothing")
