"""Journeys through a house and its doors (#3657, tranche 13): ``lock``, ``unlock``,
``pick``, ``break``, ``desc``, ``@set``, ``@name``, ``@sethome``, ``portal`` and
``functionary``.

Hobb holds the Lantern; Ysmay comes and goes; Marrow is staff. Each journey types
what a person types through the command handler and asserts what they were told
and what the rows hold.
"""

from __future__ import annotations

from evennia.utils.ansi import strip_ansi
from evennia.utils.create import create_object

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile, ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from integration_tests.harness import JourneyCase
from typeclasses.companions import CompanionObject
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.services import _room_display_name
from world.buildings.constants import ConditionTier
from world.buildings.factories import BuildingFactory
from world.buildings.upkeep_services import set_condition_tier
from world.character_sheets.models import ProfileTextVersion
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.companions.factories import CompanionFactory
from world.currency.services import get_or_create_purse
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.materialize import materialize_item_game_object_in_room
from world.locations.constants import LocationRole
from world.locations.factories import LocationOwnershipFactory, LocationTenancyFactory
from world.locations.models import LocationTenancy
from world.magic.factories import PortalAnchorKindFactory
from world.magic.models import PortalAnchor
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.functionaries import functionaries_in_room
from world.npc_services.models import Functionary
from world.room_features.models import ExitBarsDetails
from world.societies.models import LegendEntry
from world.traits.factories import CheckOutcomeFactory


def staff(case: JourneyCase, character) -> None:
    account = case.account_of(character)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    account.permissions.add("Admin")


def exit_between(name: str, room, destination):
    """An exit of the game's own typeclass from ``room`` to ``destination``."""
    exit_obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.exits.Exit")
    exit_obj.location = room
    exit_obj.destination = destination
    exit_obj.save()
    return exit_obj


def description_of(obj) -> str:
    """The description ``look`` shows for ``obj``."""
    return SceneDataManagerFactory().initialize_state_for_object(obj).description


class LockingTheDoor(JourneyCase):
    """Hobb, a tenant of the Lantern, locks its gate; Ysmay finds her own way through:
    the "lock_exit", "unlock_exit", "pick_lock" and "break_exit" actions, typed. The
    Lantern is a building in excellent condition, and every break wears it."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.yard = self.make_room("The Yard")
        area = AreaFactory(level=AreaLevel.BUILDING)
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.profile.area = area
        self.profile.save(update_fields=["area"])
        self.building = BuildingFactory(area=area, condition_tier=ConditionTier.EXCELLENT)
        self.gate = exit_between("gate", self.lantern, self.yard)
        exit_between("back", self.yard, self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        LocationTenancyFactory(
            room_profile=self.profile,
            tenant_persona=self.hobb.sheet_data.primary_persona,
            kind=LocationRole.TENANT,
        )
        self.watch(self.hobb)

    def test_a_tenant_locks_the_gate_and_a_guest_is_kept_out(self) -> None:
        self.assertIn("You don't have standing in that room.", self.telnet(self.ysmay, "lock gate"))
        self.assertFalse(self.gate.db.locked)
        self.assertIn("You lock gate.", self.telnet(self.hobb, "lock gate"))
        self.assertTrue(self.gate.db.locked)

        self.assertIn("You cannot go that way.", self.telnet(self.ysmay, "gate"))
        self.assertEqual(self.ysmay.location, self.lantern)
        self.telnet(self.hobb, "gate")
        self.assertEqual(self.hobb.location, self.yard)
        self.telnet(self.hobb, "back")
        self.assertEqual(self.hobb.location, self.lantern)

        self.assertIn(
            "You don't have standing in that room.", self.telnet(self.ysmay, "unlock gate")
        )
        self.assertIn("You unlock gate.", self.telnet(self.hobb, "unlock gate"))
        self.assertFalse(self.gate.db.locked)
        self.telnet(self.ysmay, "gate")
        self.assertEqual(self.ysmay.location, self.yard)

        # An absent exit is the command's own typed line, with the structured frame.
        box = self.mailbox(self.hobb)
        first_frame = len(box.calls)
        self.assertIn(
            "Could not find an exit called 'nowhere'.", self.telnet(self.hobb, "lock nowhere")
        )
        self.assertEqual(
            box.calls[first_frame:],
            [
                ((("Could not find an exit called 'nowhere'.", {"type": "error"}),), {}),
                (
                    (None,),
                    {
                        "command_error": {
                            "error": "Could not find an exit called 'nowhere'.",
                            "command": "lock nowhere",
                        }
                    },
                ),
            ],
        )
        for line, reply in (
            ("lock", "Lock which exit?"),
            ("unlock", "Unlock which exit?"),
            ("pick", "Pick which exit?"),
            ("break", "Break which exit?"),
        ):
            self.assertIn(reply, self.telnet(self.hobb, line), line)

    def test_an_intruder_picks_or_breaks_a_locked_gate(self) -> None:
        self.assertIn("That exit isn't locked.", self.telnet(self.ysmay, "pick gate"))
        self.assertIn("That exit isn't locked.", self.telnet(self.ysmay, "break gate"))
        self.telnet(self.hobb, "lock gate")

        # Lockpicking is a check staff author; without it the attempt is refused.
        self.assertIn(
            "Lockpicking isn't available right now.", self.telnet(self.ysmay, "pick gate")
        )
        self.assertTrue(self.gate.db.locked)
        CheckTypeFactory(name="Lockpicking")
        told = self.telnet(self.ysmay, "pick gate")
        self.assertTrue(
            "You pick the lock on gate." in told or "You fail to pick the lock on gate." in told,
            told,
        )
        picked = not self.gate.db.locked
        self.assertEqual("You pick the lock on gate." in told, picked)
        if picked:
            self.assertTold(self.hobb, "Ysmay picks the lock on gate.")
        else:
            self.assertTold(self.hobb, "Ysmay fumbles with the lock on gate.")
        self.assertTrue(LegendEntry.objects.filter(title="Lockpicking at gate").exists())

        # The same roll forced each way: a fumble leaves the gate locked, a pick opens it.
        if picked:
            self.telnet(self.hobb, "lock gate")
        with force_check_outcome(CheckOutcomeFactory(name="Fumbled", success_level=-1)) as roll:
            told = self.telnet(self.ysmay, "pick gate")
        self.assertEqual(roll.check_type.name, "Lockpicking")
        self.assertIn("You fail to pick the lock on gate.", told)
        self.assertTrue(self.gate.db.locked)
        self.assertTold(self.hobb, "Ysmay fumbles with the lock on gate.")
        with force_check_outcome(CheckOutcomeFactory(name="Picked", success_level=1)):
            told = self.telnet(self.ysmay, "pick gate")
        self.assertIn("You pick the lock on gate.", told)
        self.assertFalse(self.gate.db.locked)
        self.assertTold(self.hobb, "Ysmay picks the lock on gate.")
        self.assertEqual(LegendEntry.objects.filter(title="Lockpicking at gate").count(), 3)

        self.telnet(self.hobb, "lock gate")
        self.assertIn("You break through gate!", self.telnet(self.ysmay, "break gate"))
        self.assertFalse(self.gate.db.locked)
        self.assertTold(
            self.hobb, "Ysmay breaks through gate! A loud crack echoes through the area."
        )
        self.assertTrue(LegendEntry.objects.filter(title="Break-in at gate").exists())
        self.telnet(self.ysmay, "gate")
        self.assertEqual(self.ysmay.location, self.yard)
        # The break wore the house: one tier, from excellent to good.
        self.building.refresh_from_db()
        self.assertEqual(self.building.condition_tier, ConditionTier.GOOD)

    def test_bars_hold_a_guest_until_they_are_broken_down(self) -> None:
        bars = ExitBarsDetails.objects.create(
            exit_profile=ExitProfile.get_or_create_for_exit(self.gate), level=3
        )
        exit_between("side door", self.lantern, self.yard)

        # Unlocked but barred: a guest is held at the gate and not at the side door; the
        # tenant passes; a lock pick finds nothing to pick.
        self.assertFalse(self.gate.db.locked)
        self.assertIn("You cannot go that way.", self.telnet(self.ysmay, "gate"))
        self.assertEqual(self.ysmay.location, self.lantern)
        self.telnet(self.ysmay, "side door")
        self.assertEqual(self.ysmay.location, self.yard)
        self.telnet(self.ysmay, "back")
        self.telnet(self.hobb, "gate")
        self.assertEqual(self.hobb.location, self.yard)
        self.telnet(self.hobb, "back")
        self.assertIn("That exit isn't locked.", self.telnet(self.ysmay, "pick gate"))

        # Locked and barred: one break clears the lock and wears the bars by one; each
        # break wears the house by a tier.
        self.telnet(self.hobb, "lock gate")
        self.assertIn("You break through gate!", self.telnet(self.ysmay, "break gate"))
        self.assertFalse(self.gate.db.locked)
        bars.refresh_from_db()
        self.assertEqual((bars.level, bars.dissolved_at), (2, None))
        self.building.refresh_from_db()
        self.assertEqual(self.building.condition_tier, ConditionTier.GOOD)
        self.assertIn("You cannot go that way.", self.telnet(self.ysmay, "gate"))
        self.assertIn("You break through gate!", self.telnet(self.ysmay, "break gate"))
        bars.refresh_from_db()
        self.assertEqual((bars.level, bars.dissolved_at), (1, None))
        self.assertIn("You cannot go that way.", self.telnet(self.ysmay, "gate"))
        self.assertIn("You break through gate!", self.telnet(self.ysmay, "break gate"))
        bars.refresh_from_db()
        self.assertIsNotNone(bars.dissolved_at)
        self.building.refresh_from_db()
        self.assertEqual(self.building.condition_tier, ConditionTier.WORN)
        self.telnet(self.ysmay, "gate")
        self.assertEqual(self.ysmay.location, self.yard)
        self.telnet(self.ysmay, "back")
        self.assertIn("That exit isn't locked.", self.telnet(self.ysmay, "break gate"))
        self.assertEqual(LegendEntry.objects.filter(title="Break-in at gate").count(), 3)

        # A decayed house can fall no further.
        set_condition_tier(self.building, ConditionTier.DECAYED)
        self.telnet(self.hobb, "lock gate")
        self.assertIn("You break through gate!", self.telnet(self.ysmay, "break gate"))
        self.building.refresh_from_db()
        self.assertEqual(self.building.condition_tier, ConditionTier.DECAYED)


class DescribingTheHouse(JourneyCase):
    """Marrow, staff, writes what the Lantern and the things in it look like."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        staff(self, self.marrow)
        self.rock = ObjectDBFactory(db_key="rock", location=self.lantern)

    def test_a_description_is_what_look_shows(self) -> None:
        self.assertIn(
            "The description was set on The Lantern.",
            self.telnet(self.marrow, "desc A grey hall with no windows."),
        )
        self.assertEqual(description_of(self.lantern), "A grey hall with no windows.")
        self.assertIsNone(self.lantern.attributes.get("desc"))  # noqa: EVENNIA_DESC proves the retired Attribute stays unwritten
        self.assertIn("A grey hall with no windows.", self.telnet(self.ysmay, "look"))

        self.assertIn(
            "The description was set on rock.",
            self.telnet(self.marrow, "desc rock = A rock worn smooth by the river."),
        )
        self.assertIn("A rock worn smooth by the river.", self.telnet(self.ysmay, "look rock"))
        self.telnet(self.marrow, "desc rock = First line.%rSecond line.")
        self.assertEqual(description_of(self.rock), "First line.\nSecond line.")

        # A character's description is her sheet's, with the history kept.
        self.ysmay.sheet_data.additional_desc = "Tall, with ink-stained fingers."
        self.ysmay.sheet_data.save(update_fields=["additional_desc"])
        self.telnet(self.marrow, "desc Ysmay = Tall, with a scar through one brow.")
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(
            self.ysmay.sheet_data.additional_desc, "Tall, with a scar through one brow."
        )
        versions = ProfileTextVersion.objects.filter(
            profile=self.ysmay.sheet_data.true_profile
        ).order_by("pk")
        self.assertEqual(
            [version.text for version in versions],
            ["Tall, with ink-stained fingers.", "Tall, with a scar through one brow."],
        )
        self.assertEqual(versions.last().edited_by, self.account_of(self.marrow))

        # An item's description is its instance's.
        template = ItemTemplateFactory(name="Desc cup", description="A dented copper cup.")
        instance = ItemInstanceFactory(template=template)
        cup = materialize_item_game_object_in_room(instance, self.lantern)
        self.telnet(self.marrow, "desc Desc cup = A copper cup engraved%rwith a heron.")
        instance.refresh_from_db()
        self.assertEqual(instance.custom_description, "A copper cup engraved\nwith a heron.")
        self.assertEqual(description_of(cup), "A copper cup engraved\nwith a heron.")

        # A player has no builder verbs at all: the lock keeps the command itself away.
        self.assertIn(
            "Command 'desc rock = Mine now.' is not available.",
            self.telnet(self.ysmay, "desc rock = Mine now."),
        )
        self.assertEqual(description_of(self.rock), "First line.\nSecond line.")
        self.assertIn("Usage: desc [<obj> =] <description>", self.telnet(self.marrow, "desc"))
        # Evennia's own setdesc (any player, their own character) is gone with it.
        self.assertIn(
            "Command 'setdesc Mine.' is not available.", self.telnet(self.ysmay, "setdesc Mine.")
        )
        self.assertIn(
            "Command 'setdesc Mine.' is not available.", self.telnet(self.marrow, "setdesc Mine.")
        )

    def test_the_line_editor_edits_what_look_shows(self) -> None:
        self.telnet(self.marrow, "desc rock = A river rock.")
        told = self.telnet(self.marrow, "desc/edit rock")
        self.assertIn("Line Editor [desc]", told)
        self.telnet(self.marrow, "A split rock.")
        self.assertIn("Saved.", self.telnet(self.marrow, ":wq"))
        self.assertEqual(description_of(self.rock), "A river rock.\nA split rock.")
        self.assertIsNone(self.rock.attributes.get("desc"))  # noqa: EVENNIA_DESC proves the retired Attribute stays unwritten

        told = self.telnet(self.marrow, "@set/edit rock/desc")
        self.assertIn("Line Editor [desc]", told)
        self.assertIn("A split rock.", self.telnet(self.marrow, ":"))
        self.telnet(self.marrow, ":q")
        self.assertEqual(description_of(self.rock), "A river rock.\nA split rock.")

    def test_set_desc_is_the_same_description(self) -> None:
        self.assertIn(
            "Set the description of rock.",
            self.telnet(self.marrow, "@set rock/desc = A river rock."),
        )
        self.assertEqual(description_of(self.rock), "A river rock.")
        self.assertIsNone(self.rock.attributes.get("desc"))  # noqa: EVENNIA_DESC proves the retired Attribute stays unwritten
        self.assertIn(
            "Description of rock: A river rock.", self.telnet(self.marrow, "@set rock/desc")
        )
        self.telnet(self.marrow, '@set rock/desc = "Mine," it says.')
        self.assertEqual(description_of(self.rock), '"Mine," it says.')
        self.assertIn(
            "Set desc on its own: set <obj>/desc = <text>",
            self.telnet(self.marrow, '@set rock/desc/weight = "Hi"'),
        )
        self.assertIsNone(self.rock.attributes.get("weight"))
        self.telnet(self.marrow, "@set rock/weight = 12")
        self.assertEqual(self.rock.attributes.get("weight"), 12)
        self.assertIn(
            "Cleared the description of rock.", self.telnet(self.marrow, "@set rock/desc =")
        )
        self.assertEqual(ObjectDisplayData.objects.get(object=self.rock).permanent_description, "")
        self.telnet(self.marrow, "@set Ysmay/desc = Grey-eyed.")
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(self.ysmay.sheet_data.additional_desc, "Grey-eyed.")
        self.assertIn(
            "Command '@set rock/desc = Mine' is not available.",
            self.telnet(self.ysmay, "@set rock/desc = Mine"),
        )
        self.assertEqual(ObjectDisplayData.objects.get(object=self.rock).permanent_description, "")

    def test_a_name_reaches_everywhere_it_shows(self) -> None:
        ObjectDisplayData.objects.update_or_create(object=self.lantern, defaults={"longname": ""})
        self.assertIn(
            "Object's name changed to 'Lantern Hall'.",
            self.telnet(self.marrow, "@name here = Lantern Hall"),
        )
        self.lantern.refresh_from_db()
        self.assertEqual(self.lantern.db_key, "Lantern Hall")
        self.assertEqual(
            ObjectDisplayData.objects.get(object=self.lantern).longname, "Lantern Hall"
        )
        self.assertEqual(_room_display_name(self.lantern), "Lantern Hall")

        self.telnet(self.marrow, "@name Ysmay = Ysolde")
        self.ysmay.sheet_data.primary_persona.refresh_from_db()
        self.assertEqual(self.ysmay.key, "Ysolde")
        self.assertEqual(self.ysmay.sheet_data.primary_persona.name, "Ysolde")

        template = ItemTemplateFactory(name="Plain cup")
        instance = ItemInstanceFactory(template=template)
        cup = materialize_item_game_object_in_room(instance, self.lantern)
        self.telnet(self.marrow, "@name Plain cup = Heron cup")
        instance.refresh_from_db()
        self.assertEqual(instance.custom_name, "Heron cup")
        self.assertEqual(cup.key, "Heron cup")

        companion = CompanionFactory(owner=self.ysmay.sheet_data, name="Old Hound")
        hound = create_object(CompanionObject, key="Old Hound", location=self.lantern)
        companion.objectdb = hound
        companion.save(update_fields=["objectdb"])
        self.telnet(self.marrow, "@name Old Hound = Ember")
        companion.refresh_from_db()
        self.assertEqual(companion.name, "Ember")
        self.assertEqual(hound.key, "Ember")

        ObjectDisplayData.objects.update_or_create(
            object=self.rock, defaults={"longname": "A stock rock"}
        )
        self.assertIn(
            "Object's name changed to 'Riverstone' (stone).",
            self.telnet(self.marrow, "@name rock = Riverstone;stone"),
        )
        self.assertEqual(self.rock.key, "Riverstone")
        self.assertEqual(ObjectDisplayData.objects.get(object=self.rock).longname, "Riverstone")
        self.assertIn("stone", self.rock.aliases.all())

        self.assertIn(
            "Command '@name Riverstone = Mine' is not available.",
            self.telnet(self.ysmay, "@name Riverstone = Mine"),
        )
        self.assertEqual(self.rock.key, "Riverstone")
        self.assertIn(
            "Usage: name <obj> = <newname>[;alias;alias;...]", self.telnet(self.marrow, "@name")
        )
        # Evennia's @spawn and @copy, which made objects Arx does not read, are gone.
        self.assertIn(
            "Command '@spawn rock' is not available.", self.telnet(self.marrow, "@spawn rock")
        )
        self.assertIn(
            "Command '@copy rock' is not available.", self.telnet(self.marrow, "@copy rock")
        )

    def test_a_home_needs_standing(self) -> None:
        told = self.telnet(self.marrow, "@sethome Ysmay = here")
        self.assertIn("Ysmay's home was not changed: ", told)
        self.assertFalse(
            LocationTenancy.objects.filter(
                tenant_persona=self.ysmay.sheet_data.primary_persona
            ).exists()
        )
        LocationTenancyFactory(
            room_profile=self.profile,
            tenant_persona=self.ysmay.sheet_data.primary_persona,
            kind=LocationRole.TENANT,
        )
        self.assertIn(
            "Ysmay's home is now The Lantern, as Ysmay.",
            self.telnet(self.marrow, "@sethome Ysmay = here"),
        )
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(self.ysmay.home, self.lantern)
        self.assertEqual(self.ysmay.sheet_data.current_residence, self.profile)
        self.assertTrue(
            LocationTenancy.objects.get(
                tenant_persona=self.ysmay.sheet_data.primary_persona
            ).is_primary_home
        )
        self.telnet(self.marrow, "@sethome rock = here")
        self.assertEqual(self.rock.home, self.lantern)


class OpeningAPortal(JourneyCase):
    """Ysmay furnishes the Lantern with portal anchors; only its owner may clear them."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.persona = self.ysmay.sheet_data.primary_persona
        LocationTenancyFactory(
            room_profile=self.profile, tenant_persona=self.persona, kind=LocationRole.TENANT
        )
        self.purse = get_or_create_purse(self.ysmay.sheet_data)
        self.purse.balance = 10_000
        self.purse.save()
        self.mirror = PortalAnchorKindFactory(name="Mirror")
        self.well = PortalAnchorKindFactory(name="Well")
        self.door = PortalAnchorKindFactory(name="Door")

    def anchors(self) -> list[PortalAnchor]:
        return list(PortalAnchor.objects.active().filter(room_profile=self.profile).order_by("pk"))

    def test_anchors_are_installed_and_dissolved(self) -> None:
        self.assertIn(
            "Usage: portal/install <kind>=<name> | portal/dissolve [<kind>]",
            self.telnet(self.ysmay, "portal"),
        )
        self.assertIn(
            "Usage: portal/install <kind>=<name>", self.telnet(self.ysmay, "portal/install Mirror")
        )
        self.assertIn(
            "There is no portal anchor kind called 'Looking-glass'.",
            self.telnet(self.ysmay, "portal/install Looking-glass=a glass"),
        )
        self.assertIn(
            "You don't have standing to install a portal anchor here.",
            self.telnet(self.hobb, "portal/install Mirror=a tall silvered mirror"),
        )
        self.assertEqual(self.anchors(), [])

        self.assertIn(
            "You install a tall silvered mirror here.",
            self.telnet(self.ysmay, "portal/install Mirror=a tall silvered mirror"),
        )
        (mirror,) = self.anchors()
        self.assertEqual(
            (mirror.kind_id, mirror.installed_by_id), (self.mirror.pk, self.persona.pk)
        )
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 5_000)
        self.assertIn(
            "An anchor of that kind is already installed here.",
            self.telnet(self.ysmay, "portal/install mirror=another mirror"),
        )
        self.assertIn(
            "You install a stone well here.",
            self.telnet(self.ysmay, "portal/install Well=a stone well"),
        )
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 0)
        self.assertIn(
            "You cannot afford to install a portal anchor here.",
            self.telnet(self.ysmay, "portal/install Door=a third"),
        )

        # Clearing an anchor is the owner's; a tenant furnished it and may not.
        self.assertIn(
            "You don't have standing to dissolve this anchor.",
            self.telnet(self.ysmay, "portal/dissolve Mirror"),
        )
        LocationOwnershipFactory(
            on_room=True, room_profile=self.profile, holder_persona=self.persona
        )
        self.assertIn("specify a kind: Mirror, Well.", self.telnet(self.ysmay, "portal/dissolve"))
        self.assertIn(
            "a tall silvered mirror dissolves.", self.telnet(self.ysmay, "portal/dissolve Mirror")
        )
        self.assertIn(
            "There is no active Mirror anchor here.",
            self.telnet(self.ysmay, "portal/dissolve Mirror"),
        )
        self.assertIn("a stone well dissolves.", self.telnet(self.ysmay, "portal/dissolve"))
        self.assertEqual(self.anchors(), [])
        self.assertIn(
            "There is no portal anchor here to dissolve.",
            self.telnet(self.ysmay, "portal/dissolve"),
        )


class KeepingAFunctionary(JourneyCase):
    """Marrow, staff, places a barkeep in the Lantern; everyone sees her there."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        staff(self, self.marrow)
        self.barkeep = NPCRoleFactory(name="Barkeep")

    def test_a_functionary_is_placed_and_removed(self) -> None:
        self.assertIn("No functionaries are here.", self.telnet(self.ysmay, "functionary"))
        self.assertIn(
            "Only staff may place or remove functionaries.",
            self.telnet(self.ysmay, "functionary place Barkeep=Old Marta"),
        )
        self.assertFalse(Functionary.objects.filter(role=self.barkeep).exists())
        self.assertIn(
            "Placed Old Marta (Barkeep) here.",
            self.telnet(self.marrow, "functionary place Barkeep=Old Marta"),
        )
        placed = Functionary.objects.get(role=self.barkeep, room=self.profile)
        self.assertEqual(placed.name_override, "Old Marta")
        self.assertIn(
            "Functionaries here: Old Marta", strip_ansi(self.telnet(self.ysmay, "functionary"))
        )
        self.assertIn("Old Marta", self.telnet(self.ysmay, "look"))

        self.assertIn(
            "No NPC role by that name or id.", self.telnet(self.marrow, "functionary place Nobody")
        )
        self.assertIn(
            "Usage: functionary place <role>[=<name>]",
            self.telnet(self.marrow, "functionary place"),
        )
        self.assertIn(
            "Removed the Barkeep functionary here.",
            self.telnet(self.marrow, f"functionary remove {self.barkeep.pk}"),
        )
        self.assertFalse(functionaries_in_room(self.profile).exists())
        self.assertIn("No functionaries are here.", self.telnet(self.ysmay, "functionary list"))
        self.assertIn(
            "No Barkeep functionary is here.",
            self.telnet(self.marrow, "functionary remove Barkeep"),
        )
        self.assertIn(
            "Only staff may place or remove functionaries.",
            self.telnet(self.ysmay, "functionary remove Barkeep"),
        )
        self.assertIn(
            "Usage: functionary remove <role>", self.telnet(self.marrow, "functionary remove")
        )
        self.assertIn("Usage:", self.telnet(self.marrow, "functionary frobnicate"))
