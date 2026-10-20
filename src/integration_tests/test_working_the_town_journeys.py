"""Journeys through the town (#3657, tranche 14): ``hire``, ``game``, ``craft``,
``network``, ``identify`` and ``travel``.

Ysmay works the town; Hobb and Maud are the people she meets there. Each journey
types what a person types through the command handler and asserts what they were
told and what the rows hold.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.assets.factories import NPCAssetFactory
from world.assets.models import NPCAsset
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse, transfer
from world.items.crafting.constants import CraftingRecipeKind
from world.items.factories import (
    CraftingRecipeFactory,
    GemDetailsFactory,
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    StyleFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.gems.constants import GemAxis
from world.items.models import ItemFacet, ItemInstance, ItemStyle
from world.locations.factories import LocationOwnershipFactory
from world.magic.factories import FacetFactory
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInstance
from world.npc_services.constants import OfferKind, SummonsStatus
from world.npc_services.factories import (
    FunctionaryFactory,
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.models import NPCStanding, OfferSummons
from world.npc_services.summons import create_summons
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.factories import PersonaFactory, PlaceFactory
from world.scenes.models import Interaction, PersonaDiscovery
from world.secrets.factories import SecretFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.consent import seed_social_consent_categories
from world.seeds.investigation_checks import ensure_identification_check
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.tasking.constants import TaskStatus
from world.tasking.factories import TaskTemplateFactory
from world.tasking.models import ListenerHarvest, ListenerPost, OrgTask
from world.tavern_games.constants import GameSessionState
from world.tavern_games.models import GameSession
from world.tavern_games.seeds import DICE_GAME_NAME, ensure_dice_game
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory
from world.traits.models import Trait


def exit_between(name: str, room, destination):
    """An exit of the game's own typeclass from ``room`` to ``destination``."""
    exit_obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.exits.Exit")
    exit_obj.location = room
    exit_obj.destination = destination
    exit_obj.save()
    return exit_obj


def fund(character, coppers: int) -> None:
    transfer(
        amount=coppers,
        reason="a purse for the journey",
        to_purse=get_or_create_purse(character.sheet_data),
    )


def balance_of(character) -> int:
    return get_or_create_purse(character.sheet_data).balance


def mission_offer(role, *, label: str, risk_tier: int = 1):
    """A MISSION offer of ``role`` whose template can really be run."""
    offer = NPCServiceOfferFactory(role=role, kind=OfferKind.MISSION, label=label)
    details = MissionOfferDetailsFactory(
        offer=offer, mission_template=MissionTemplateFactory(name=label, risk_tier=risk_tier)
    )
    MissionNodeFactory(template=details.mission_template, is_entry=True)
    return offer


class HiringAnNPC(JourneyCase):
    """Ysmay walks up to Old Marta, the Lantern's barkeep, and takes her work."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.role = NPCRoleFactory(name="Barkeep")
        FunctionaryFactory(role=self.role, room=self.profile, name_override="Old Marta")
        self.letter = mission_offer(self.role, label="Carry a letter")
        self.watch(self.ysmay)

    def test_she_takes_the_barkeeps_work(self) -> None:
        told = self.telnet(self.ysmay, "hire")
        self.assertIn("No interaction in progress. Use 'hire <name>' to start one.", told)
        self.assertIn("Here: Old Marta", strip_ansi(told))
        for line, reply in (
            ("hire end", "No interaction is in progress."),
            ("hire offer 1", "No interaction is in progress."),
            ("hire Nobody", "No one like that is here, and no NPC role by that name or id."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))

        told = strip_ansi(self.telnet(self.ysmay, "hire Old Marta"))
        self.assertIn("You begin speaking with Old Marta.", told)
        self.assertIn(f"[#{self.letter.pk}] Carry a letter (final) [mission]", told)
        self.assertIn(
            "You already have an interaction in progress. Use 'hire end' first.",
            self.telnet(self.ysmay, "hire Old Marta"),
        )
        told = strip_ansi(self.telnet(self.ysmay, "hire"))
        self.assertIn("Speaking with Barkeep", told)
        self.assertIn("rapport 0", told)
        self.assertIn("Carry a letter", told)
        self.assertIn(
            "Usage: hire offer <offer id> [acknowledge_risk=yes]",
            self.telnet(self.ysmay, "hire offer soon"),
        )
        self.assertIn("That offer was not found.", self.telnet(self.ysmay, "hire offer 99999"))
        # An offer of another role is not this barkeep's to give.
        elsewhere = mission_offer(NPCRoleFactory(name="Smith"), label="Shoe a horse")
        self.assertIn(
            "That offer is not available from this NPC.",
            self.telnet(self.ysmay, f"hire offer {elsewhere.pk}"),
        )
        # One the barkeep holds back until she likes you better is not listed, nor granted.
        guarded = mission_offer(self.role, label="Guard the cellar")
        guarded.rapport_requirement = 5
        guarded.save(update_fields=["rapport_requirement"])
        self.assertNotIn("Guard the cellar", strip_ansi(self.telnet(self.ysmay, "hire")))
        self.assertIn(
            "That offer is not currently available.",
            self.telnet(self.ysmay, f"hire offer {guarded.pk}"),
        )

        self.assertIn(
            "Mission 'Carry a letter' accepted.",
            self.telnet(self.ysmay, f"hire offer {self.letter.pk}"),
        )
        run = MissionInstance.objects.get(source_offer=self.letter)
        self.assertEqual(run.accepted_as_persona, self.ysmay.sheet_data.primary_persona)
        self.assertTrue(run.participants.filter(character=self.ysmay.sheet_data).exists())
        # A final offer closes the conversation.
        self.assertIn("No interaction in progress.", self.telnet(self.ysmay, "hire"))

    def test_a_dangerous_job_is_offered_twice(self) -> None:
        marsh = mission_offer(self.role, label="Cross the marsh", risk_tier=3)
        self.telnet(self.ysmay, "hire Old Marta")
        told = self.telnet(self.ysmay, f"hire offer {marsh.pk}")
        self.assertIn("This job is dangerous (risk tier 3). At stake:", told)
        self.assertIn("Accept again with acknowledge_risk=yes to take the job anyway.", told)
        self.assertFalse(MissionInstance.objects.filter(source_offer=marsh).exists())
        self.assertIn(
            "Mission 'Cross the marsh' accepted.",
            self.telnet(self.ysmay, f"hire offer {marsh.pk} acknowledge_risk=yes"),
        )
        self.assertTrue(MissionInstance.objects.filter(source_offer=marsh).exists())

    def test_a_named_npc_remembers_her(self) -> None:
        gerald = PersonaFactory(name="Gerald")
        self.assertIn(
            "Could not find persona 'Nobody'.", self.telnet(self.ysmay, "hire Barkeep as Nobody")
        )
        self.assertIn(
            "You begin speaking with Gerald.", self.telnet(self.ysmay, "hire Barkeep as Gerald")
        )
        self.assertIn("You conclude the conversation.", self.telnet(self.ysmay, "hire end"))
        standing = NPCStanding.objects.get(
            persona=self.ysmay.sheet_data.primary_persona, npc_persona=gerald
        )
        self.assertEqual(standing.affection, 0)

    def test_a_summons_is_answered(self) -> None:
        hobb = self.make_player("Hobb", room=self.lantern)
        summons = create_summons(
            self.letter, self.ysmay.sheet_data.primary_persona, message="Come at once."
        )
        for line, reply in (
            ("hire accept", "Usage: hire accept <summons-id> [confirm]"),
            ("hire decline", "Usage: hire decline <summons-id>"),
            (
                "hire accept soon",
                "Usage: hire accept <summons-id> [confirm] / hire decline <summons-id>",
            ),
            ("hire accept 99999", "No summons #99999 found."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertIn(
            f"Summons #{summons.pk} is not directed at you.",
            self.telnet(hobb, f"hire accept {summons.pk}"),
        )
        told = self.telnet(self.ysmay, f"hire accept {summons.pk}")
        run = MissionInstance.objects.get(source_offer=self.letter)
        self.assertIn(f"Mission accepted (instance #{run.pk}).", told)
        self.assertEqual(run.accepted_as_persona, self.ysmay.sheet_data.primary_persona)
        self.assertEqual(OfferSummons.objects.get(pk=summons.pk).status, SummonsStatus.ACCEPTED)
        self.assertIn(
            f"Summons #{summons.pk} is already accepted.",
            self.telnet(self.ysmay, f"hire decline {summons.pk}"),
        )

        other = mission_offer(self.role, label="Sweep the yard")
        declined = create_summons(other, self.ysmay.sheet_data.primary_persona)
        self.telnet(self.ysmay, f"hire decline {declined.pk}")
        self.assertEqual(OfferSummons.objects.get(pk=declined.pk).status, SummonsStatus.DECLINED)


class PlayingAtTheTable(JourneyCase):
    """Ysmay and Hobb sit at the Rowdy Table and roll for coppers."""

    def setUp(self) -> None:
        super().setUp()
        self.tavern = self.make_room("The Rowdy Tavern")
        self.profile = RoomProfileFactory(objectdb=self.tavern, is_social_hub=True)
        PlaceFactory(room=self.profile, name="The Rowdy Table")
        ensure_dice_game()
        self.ysmay = self.make_player("Ysmay", room=self.tavern)
        self.hobb = self.make_player("Hobb", room=self.tavern)
        fund(self.ysmay, 100)
        fund(self.hobb, 100)
        self.watch(self.ysmay, self.hobb)
        self.telnet(self.ysmay, "places join The Rowdy Table")
        self.telnet(self.hobb, "places join The Rowdy Table")

    def test_a_hand_is_played_and_the_pot_paid(self) -> None:
        self.assertIn("There's no open game here.", self.telnet(self.ysmay, "game"))
        self.assertIn(
            "There's no open game here. Start one with 'game open <name>=<ante>'.",
            self.telnet(self.hobb, "game roll"),
        )
        self.assertIn(
            f"You open a game of {DICE_GAME_NAME} at The Rowdy Table (ante 10).",
            self.telnet(self.ysmay, f"game open {DICE_GAME_NAME}=10"),
        )
        self.assertShownRow(self.hobb, f"opens a game of {DICE_GAME_NAME} at the table (ante 10")
        self.assertEqual(balance_of(self.ysmay), 90)
        self.assertIn(
            "You need another player at the table before you can roll.",
            self.telnet(self.ysmay, "game roll"),
        )
        self.assertIn("You're already seated at that table.", self.telnet(self.ysmay, "game join"))
        self.assertIn("You ante 10 coppers and join the game.", self.telnet(self.hobb, "game join"))
        self.assertEqual(balance_of(self.hobb), 90)
        told = strip_ansi(self.telnet(self.hobb, "game"))
        self.assertIn(f"{DICE_GAME_NAME} at The Rowdy Table: ante 10, pot 20.", told)
        self.assertIn("Ysmay: waiting", told)
        self.assertIn("Hobb: waiting", told)

        rolls = iter([2, 6])
        with patch(
            "world.tavern_games.services._TABLE_RNG.randint", side_effect=lambda *_a: next(rolls)
        ):
            self.assertIn("You roll a 2!", self.telnet(self.ysmay, "game roll"))
            self.assertIn("You've already rolled this hand.", self.telnet(self.ysmay, "game roll"))
            self.assertIn("Ysmay: rolled 2", strip_ansi(self.telnet(self.hobb, "game")))
            self.assertIn("You roll a 6!", self.telnet(self.hobb, "game roll"))
        self.assertShownRow(self.ysmay, f"Hobb wins the pot of 20 coppers at {DICE_GAME_NAME}!")
        session = GameSession.objects.get()
        self.assertEqual(session.state, GameSessionState.RESOLVED)
        self.assertEqual(session.pot, 0)
        self.assertEqual(balance_of(self.ysmay), 90)
        self.assertEqual(balance_of(self.hobb), 110)
        self.assertIn("There's no open game here.", self.telnet(self.ysmay, "game"))

    def test_leaving_refunds_and_the_table_has_its_rules(self) -> None:
        self.telnet(self.ysmay, f"game open {DICE_GAME_NAME}=15")
        self.telnet(self.hobb, "game join")
        self.assertEqual(balance_of(self.hobb), 85)
        self.assertIn(
            "You leave the table and take back your ante.", self.telnet(self.hobb, "game leave")
        )
        self.assertEqual(balance_of(self.hobb), 100)
        self.assertIn("You aren't seated at that table.", self.telnet(self.hobb, "game leave"))
        session = GameSession.objects.get()
        self.assertEqual(session.pot, 15)
        self.telnet(self.ysmay, "game leave")
        self.assertEqual(GameSession.objects.get().state, GameSessionState.ABANDONED)
        self.assertEqual(balance_of(self.ysmay), 100)

        for line, reply in (
            ("game open Not A Real Game=10", "No such game: 'Not A Real Game'."),
            (f"game open {DICE_GAME_NAME}=ten", "The ante must be a whole number of coppers."),
            (f"game open {DICE_GAME_NAME}", "Usage: game open <game name>=<ante>"),
            ("game frob", "Usage:\n  game  |  game open <game name>=<ante>"),
            (f"game open {DICE_GAME_NAME}=900", "That ante is outside the game's allowed range."),
            ("game join", "There's no open game here."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertEqual(GameSession.objects.count(), 1)

        # The weekly loss cap counts every ante, refunded or not.
        fund(self.ysmay, 900)
        self.telnet(self.ysmay, f"game open {DICE_GAME_NAME}=300")
        self.telnet(self.ysmay, "game leave")
        self.assertEqual(balance_of(self.ysmay), 1000)
        self.assertIn(
            "That ante would push you past your weekly loss cap for the week.",
            self.telnet(self.ysmay, f"game open {DICE_GAME_NAME}=300"),
        )

    def test_an_empty_purse_and_the_wrong_room(self) -> None:
        maud = self.make_player("Maud", room=self.tavern)
        self.assertIn("You aren't at a place.", self.telnet(maud, "game"))
        self.telnet(maud, "places join The Rowdy Table")
        self.telnet(self.ysmay, f"game open {DICE_GAME_NAME}=10")
        fund(maud, 5)
        self.assertIn(
            "You don't have the coppers to cover the ante.", self.telnet(maud, "game join")
        )
        self.assertEqual(balance_of(maud), 5)
        self.assertEqual(GameSession.objects.get().pot, 10)

        parlour = self.make_room("The Quiet Parlour")
        PlaceFactory(room=RoomProfileFactory(objectdb=parlour), name="The Settle")
        self.hobb.location = parlour
        self.telnet(self.hobb, "places leave")
        self.telnet(self.hobb, "places join The Settle")
        self.assertIn(
            "There is no room here for a coin game - this isn't a social hub.",
            self.telnet(self.hobb, f"game open {DICE_GAME_NAME}=10"),
        )


class CraftingAtTheBench(JourneyCase):
    """Ysmay works a facet, a style and a new blade at the workshop's bench."""

    def setUp(self) -> None:
        super().setUp()
        self.workshop = self.make_room("The Workshop")
        self.profile = RoomProfileFactory(objectdb=self.workshop)
        install_full_lab_station(self.profile)
        wire_enchanting_crafting(base_difficulty=0)
        self.ysmay = self.make_player("Ysmay", room=self.workshop)
        self.sheet = self.ysmay.sheet_data
        CharacterTraitValueFactory(
            character=self.sheet, trait=Trait.objects.get(name="Enchanting"), value=50
        )
        self.sword_object = ObjectDBFactory(
            db_key="plain sword", db_typeclass_path="typeclasses.objects.Object"
        )
        self.sword_object.location = self.ysmay
        self.sword_object.save()
        self.sword = ItemInstanceFactory(
            template=ItemTemplateFactory(name="plain sword", facet_capacity=1, style_capacity=1),
            holder_character_sheet=self.sheet,
            game_object=self.sword_object,
        )
        self.rock = ObjectDBFactory(db_key="rock", db_typeclass_path="typeclasses.objects.Object")
        self.rock.location = self.ysmay
        self.rock.save()
        self.glow = FacetFactory(name="Glow")
        FacetFactory(name="Hum")
        StyleFactory(name="Sharp")
        self.ok = CheckOutcomeFactory(name="Ok", success_level=2)
        self.botch = CheckOutcomeFactory(name="Botch", success_level=-2)
        self.watch(self.ysmay)

    def test_a_facet_is_worked_in_and_out(self) -> None:
        sword = self.sword_object.pk
        for line, reply in (
            ("craft", "Usage: craft facet <name> item=<id>"),
            ("craft bogus", "Unknown craft action 'bogus'."),
            ("craft facet Glow", "Usage: craft facet <name> item=<id>"),
            ("craft facet Glow item=abc", "Usage: craft facet <name> item=<id>"),
            ("craft facet Glow item=99999", "You aren't holding that item."),
            (f"craft facet Glow item={self.rock.pk}", "That isn't an item."),
            (f"craft facet Nothing item={sword}", "No facet called 'Nothing'."),
            (f"craft quote item={sword}", "Usage: craft facet <name> item=<id>"),
            (f"craft quote style=Nothing item={sword}", "No style called 'Nothing'."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertIn(
            "Affordable: True. Max quality tier: Fine.",
            self.telnet(self.ysmay, f"craft quote facet=Glow item={sword}"),
        )

        with force_check_outcome(self.botch):
            self.assertIn(
                "The work fails; Glow does not take.",
                self.telnet(self.ysmay, f"craft facet Glow item={sword}"),
            )
        self.assertFalse(ItemFacet.objects.filter(item_instance=self.sword).exists())
        with force_check_outcome(self.ok):
            self.assertIn(
                "You work Glow into plain sword (Common quality).",
                self.telnet(self.ysmay, f"craft facet Glow item={sword}"),
            )
        attached = ItemFacet.objects.get(item_instance=self.sword, facet=self.glow)
        self.assertEqual(attached.attachment_quality_tier.name, "Common")
        self.assertIn(
            "That facet is already attached to this item.",
            self.telnet(self.ysmay, f"craft facet Glow item={sword}"),
        )
        self.assertIn(
            "This item has no remaining facet slots.",
            self.telnet(self.ysmay, f"craft facet Hum item={sword}"),
        )

        inherent = ItemFacetFactory(item_instance=self.sword, facet=FacetFactory(name="Steel"))
        inherent.is_inherent = True
        inherent.save(update_fields=["is_inherent"])
        for line, reply in (
            ("craft removefacet", "Usage: craft removefacet <item_facet id>."),
            ("craft removefacet 99999", "No such attached facet."),
            (
                f"craft removefacet {inherent.pk}",
                "That facet is part of what this item is, and cannot be removed.",
            ),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertIn(
            "You strip Glow from plain sword.",
            self.telnet(self.ysmay, f"craft removefacet {attached.pk}"),
        )
        self.assertIsNotNone(ItemFacet.objects.get(pk=attached.pk).removed_at)
        self.assertIn(
            "No such attached facet.", self.telnet(self.ysmay, f"craft removefacet {attached.pk}")
        )

    def test_a_style_a_new_blade_and_a_cut_stone(self) -> None:
        sword = self.sword_object.pk
        with force_check_outcome(self.ok):
            self.assertIn(
                "You work Sharp into plain sword (Common quality).",
                self.telnet(self.ysmay, f"craft style Sharp item={sword}"),
            )
        self.assertTrue(
            ItemStyle.objects.filter(item_instance=self.sword, style__name="Sharp").exists()
        )
        self.assertIn(
            "That style is already attached to this item.",
            self.telnet(self.ysmay, f"craft style Sharp item={sword}"),
        )
        self.assertIn(
            "Affordable: True. Max quality tier: Fine.",
            self.telnet(self.ysmay, f"craft quote style=Sharp item={sword}"),
        )

        self.assertIn(
            "No craftable template called 'Nothing'.",
            self.telnet(self.ysmay, "craft create Nothing"),
        )
        with force_check_outcome(self.ok):
            self.assertIn(
                "You craft Fang (Common quality).",
                self.telnet(self.ysmay, "craft create Craftable Dagger=Fang, A thin blade"),
            )
        fang = ItemInstance.objects.get(custom_name="Fang")
        self.assertEqual(fang.holder_character_sheet, self.sheet)
        self.assertEqual(fang.custom_description, "A thin blade")
        self.assertEqual(fang.template.name, "Craftable Dagger")
        # A making never fails to make (#2886): a botched blade lands at the floor tier.
        with force_check_outcome(self.botch):
            self.assertIn(
                "You craft Splinter (Common quality).",
                self.telnet(self.ysmay, "craft create Craftable Dagger=Splinter"),
            )
        self.assertEqual(
            ItemInstance.objects.get(custom_name="Splinter").quality_tier.name, "Common"
        )

        # Until staff author the gem-cut recipe, there is no cutting at all.
        self.assertIn(
            "Crafting is not available yet.", self.telnet(self.ysmay, f"craft cut item={sword}")
        )
        CraftingRecipeFactory(
            kind=CraftingRecipeKind.GEM_CUT,
            check_type=CheckTypeFactory(name="Enchanting"),
            skill_trait=Trait.objects.get(name="Enchanting"),
        )
        self.assertIn("That is not a gem.", self.telnet(self.ysmay, f"craft cut item={sword}"))
        rough = GemGradeFactory(axis=GemAxis.CUT, label="Rough", sort_order=0)
        GemGradeFactory(axis=GemAxis.CUT, label="Brilliant", sort_order=1)
        stone_object = ObjectDBFactory(
            db_key="garnet", db_typeclass_path="typeclasses.objects.Object"
        )
        stone_object.location = self.ysmay
        stone_object.save()
        stone_template = ItemTemplateFactory(name="garnet", value=40)
        GemDetailsFactory(item_template=stone_template)
        stone = ItemInstanceFactory(
            template=stone_template, holder_character_sheet=self.sheet, game_object=stone_object
        )
        GemInstanceDetailsFactory(item_instance=stone, cut_grade=rough)
        with force_check_outcome(self.ok):
            told = self.telnet(self.ysmay, f"craft cut item={stone_object.pk}")
        self.assertIn("The cut improves to Brilliant, now worth", told)
        self.assertEqual(stone.gem_or_none.cut_grade.label, "Brilliant")
        with force_check_outcome(self.botch):
            self.assertIn(
                "The stone shatters! You lose",
                self.telnet(self.ysmay, f"craft cut item={stone_object.pk}"),
            )
        # A bare stone carries no prose or provenance, so the shattering removes it outright.
        self.assertFalse(ItemInstance.objects.filter(pk=stone.pk).exists())

    def test_no_bench_no_work(self) -> None:
        self.ysmay.location = self.make_room("The Lane")
        self.assertIn(
            "This crafting requires an installed workspace here.",
            self.telnet(self.ysmay, f"craft facet Glow item={self.sword_object.pk}"),
        )
        self.assertFalse(ItemFacet.objects.filter(item_instance=self.sword).exists())


class RunningASpyNetwork(JourneyCase):
    """Ysmay leads the Ledger, posts Wren to listen at the docks; Hobb works against her."""

    def setUp(self) -> None:
        super().setUp()
        seed_social_consent_categories()
        for name in ("Intimidation", "Seduction", "Perception"):
            CheckTypeFactory(name=name)
        self.docks = self.make_room("The Docks")
        self.profile = RoomProfileFactory(objectdb=self.docks)
        self.ysmay = self.make_player("Ysmay", room=self.docks)
        self.hobb = self.make_player("Hobb", room=self.docks)
        self.maud = self.make_player("Maud", room=self.docks)
        self.persona = self.ysmay.sheet_data.primary_persona
        self.ledger = OrganizationFactory(name="The Ledger")
        OrganizationMembershipFactory(organization=self.ledger, persona=self.persona, rank=1)
        self.wren = NPCAssetFactory(
            promoter_persona=self.persona, asset_persona=PersonaFactory(name="Wren")
        )
        self.watch_template = CheckTypeFactory(name="Watchfulness")
        self.watch_the_docks = TaskTemplateFactory(
            name="Watch the docks", check_type=self.watch_template
        )
        errand = MissionTemplateFactory(name="Run the message")
        MissionNodeFactory(template=errand, is_entry=True)
        self.run_the_message = TaskTemplateFactory(
            name="Run the message", check_type=self.watch_template, mission_template=errand
        )
        self.win = CheckOutcomeFactory(name="Win", success_level=2)
        self.lose = CheckOutcomeFactory(name="Lose", success_level=-1)
        self.watch(self.ysmay, self.hobb, self.maud)

    def test_tasks_are_issued_dispatched_and_taken(self) -> None:
        self.assertIn("Your networks report nothing.", self.telnet(self.ysmay, "network"))
        for line, reply in (
            ("network skulk", "Usage: network |"),
            ("network issue", "Usage: network issue <template> org=<org>"),
            ("network issue Nothing org=The Ledger", "No such template or organization."),
            ("network accept soon", "Usage: network accept <task id>"),
            ("network accept 99999", "No such task."),
            ("network assign x", "Usage: network assign <task id> = <agent name>"),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertIn(
            "Only the organization's leadership can issue tasks.",
            self.telnet(self.hobb, "network issue Watch the docks org=The Ledger"),
        )
        self.assertFalse(OrgTask.objects.exists())

        told = self.telnet(self.ysmay, "network issue Watch the docks org=The Ledger")
        task = OrgTask.objects.get(template=self.watch_the_docks)
        self.assertIn(f"Task #{task.pk} issued: Watch the docks.", told)
        self.assertIn(
            f"#{task.pk} [open] Watch the docks (The Ledger)",
            strip_ansi(self.telnet(self.ysmay, "network")),
        )
        self.assertIn(
            "Usage: network assign <task id> = <agent name>",
            self.telnet(self.ysmay, f"network assign {task.pk} = Nobody"),
        )
        with force_check_outcome(self.win):
            told = self.telnet(self.ysmay, f"network assign {task.pk} = Wren")
        self.assertIn(f"Wren slips away on task #{task.pk}. They report back by", told)
        self.assertEqual(OrgTask.objects.get(pk=task.pk).status, TaskStatus.ASSIGNED)
        self.assertIn(
            "This task already has an assignment or is closed.",
            self.telnet(self.ysmay, f"network assign {task.pk} = Wren"),
        )
        self.assertIn(
            "This task already has an assignment or is closed.",
            self.telnet(self.ysmay, f"network accept {task.pk}"),
        )
        # A task with no mission behind it is an agent's work, not a member's.
        self.telnet(self.ysmay, "network issue Watch the docks org=The Ledger")
        second = OrgTask.objects.filter(template=self.watch_the_docks).exclude(pk=task.pk).get()
        self.assertIn(
            "That task is not ready to resolve.",
            self.telnet(self.ysmay, f"network accept {second.pk}"),
        )

        self.telnet(self.ysmay, "network issue Run the message org=The Ledger")
        errand = OrgTask.objects.get(template=self.run_the_message)
        self.assertIn(
            "Only members of the issuing organization can handle its tasks.",
            self.telnet(self.hobb, f"network accept {errand.pk}"),
        )
        told = self.telnet(self.ysmay, f"network accept {errand.pk}")
        run = MissionInstance.objects.get(template__name="Run the message")
        self.assertIn(
            f"You take task #{errand.pk} yourself. See `mission` for your new run (#{run.pk}).",
            told,
        )
        self.assertEqual(OrgTask.objects.get(pk=errand.pk).status, TaskStatus.ASSIGNED)

    def test_a_listener_is_posted_worked_against_and_ushered_out(self) -> None:
        self.assertIn(
            "Usage: network post <agent name> (one of your agents)",
            self.telnet(self.ysmay, "network post Nobody"),
        )
        told = self.telnet(self.ysmay, "network post Wren")
        post = ListenerPost.objects.get()
        self.assertIn(f"Wren settles in here, ears open (post #{post.pk}).", told)
        self.assertIn(
            "That listener post cannot be created.", self.telnet(self.ysmay, "network post Wren")
        )
        self.assertIn(
            f"post #{post.pk}: Wren listening (buzz 0/100)",
            strip_ansi(self.telnet(self.ysmay, "network")),
        )
        self.assertIn(
            "There is nothing to collect here.", self.telnet(self.ysmay, "network collect")
        )
        ListenerHarvest.objects.create(
            post=post, secret=SecretFactory(subject_sheet=self.hobb.sheet_data)
        )
        self.assertIn("1 to collect", strip_ansi(self.telnet(self.ysmay, "network")))
        self.assertIn(
            "There is nothing to collect here.", self.telnet(self.hobb, "network collect")
        )
        self.assertIn(
            "Your agent leans close: An Agent's Whisper.",
            self.telnet(self.ysmay, "network collect"),
        )
        self.assertIsNotNone(ListenerHarvest.objects.get().collected_at)
        self.assertIn(
            "There is nothing to collect here.", self.telnet(self.ysmay, "network collect")
        )

        with force_check_outcome(self.lose):
            self.assertIn("You spot nothing out of place.", self.telnet(self.hobb, "network sweep"))
        with force_check_outcome(self.win):
            self.assertIn(
                "Someone here is listening: Wren.", self.telnet(self.hobb, "network sweep")
            )
        self.assertIn(
            "That move is not possible here.", self.telnet(self.ysmay, "network suppress")
        )
        # Working against a player's network is consent-gated, and closed by default.
        self.assertIn(
            "They are not open to that kind of play.", self.telnet(self.hobb, "network suppress")
        )
        self.telnet(self.ysmay, "consent category espionage=everyone")
        with force_check_outcome(self.lose):
            self.assertIn("They don't scare.", self.telnet(self.hobb, "network suppress"))
        self.assertIsNone(ListenerPost.objects.get().suppressed_until)
        with force_check_outcome(self.win):
            self.assertIn("They go pale, and quiet.", self.telnet(self.hobb, "network suppress"))
        self.assertIsNotNone(ListenerPost.objects.get().suppressed_until)

        with force_check_outcome(self.lose):
            self.assertIn("They resist your charms.", self.telnet(self.hobb, "network flip"))
        with force_check_outcome(self.win):
            self.assertIn(
                "Their loyalties quietly change hands. They are yours now.",
                self.telnet(self.hobb, "network flip"),
            )
        self.assertEqual(
            ListenerPost.objects.get().flipped_controller, self.hobb.sheet_data.primary_persona
        )
        self.assertTrue(
            NPCAsset.objects.filter(
                promoter_persona=self.hobb.sheet_data.primary_persona,
                asset_persona=self.wren.asset_persona,
            ).exists()
        )
        for line, reply in (
            ("network plant", "Usage: network plant <post id> <character> = <the lie>"),
            (f"network plant {post.pk} Nobody = She sold the key", "No such character."),
        ):
            self.assertIn(reply, self.telnet(self.hobb, line))
        self.assertIn(
            "That move is not possible here.",
            self.telnet(self.ysmay, f"network plant {post.pk} Hobb = He sold the key"),
        )
        self.assertIn(
            "The lie is seeded. Their next collection will carry it.",
            self.telnet(self.hobb, f"network plant {post.pk} Ysmay = She sold the key"),
        )
        self.assertIsNotNone(ListenerPost.objects.get().pending_plant)

        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.profile,
            holder_persona=self.maud.sheet_data.primary_persona,
        )
        self.assertIn("That move is not possible here.", self.telnet(self.hobb, "network clear"))
        self.assertIn(
            "You clear the room (1 ushered out).", self.telnet(self.maud, "network clear")
        )
        self.assertIn("No hangers-on to usher out.", self.telnet(self.maud, "network clear"))
        self.assertIn(
            "No one here seems to be listening.", self.telnet(self.hobb, "network suppress")
        )
        self.assertIn("Your networks report nothing.", self.telnet(self.ysmay, "network"))


@override_settings(SEED_SAMPLE_CONTENT=True)
class SeeingWhoIsUnderTheMask(JourneyCase):
    """Ysmay wears a stag mask; Hobb and Maud try to place who is under it."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ensure_identification_check()
        self.lantern = self.make_room("The Lantern")
        self.profile = RoomProfileFactory(objectdb=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.maud = self.make_player("Maud", room=self.lantern)
        self.success = CheckOutcomeFactory(name="Placed", success_level=2)
        self.miss = CheckOutcomeFactory(name="Missed", success_level=0)
        self.botch = CheckOutcomeFactory(name="Botched", success_level=-2)
        self.watch(self.ysmay, self.hobb, self.maud)

    def test_a_mask_is_seen_through_or_not(self) -> None:
        for line, reply in (
            ("identify", "Identify whom?"),
            ("identify Nobody", "Could not find 'Nobody'."),
            ("identify Ysmay", "Their face is their own; there is no mask to see through."),
        ):
            self.assertIn(reply, self.telnet(self.hobb, line))
        self.telnet(self.ysmay, "persona mask Stag Mask")
        self.assertIn(
            "Their face is their own; there is no mask to see through.",
            self.telnet(self.ysmay, "identify Ysmay"),
        )

        with force_check_outcome(self.miss) as capture:
            self.assertIn(
                "You can't place who's really underneath",
                self.telnet(self.hobb, "identify Ysmay"),
            )
        self.assertEqual(capture.target_difficulty, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])
        self.assertEqual(PersonaDiscovery.objects.count(), 0)
        # Naming the right person eases the look; naming the wrong one does not.
        with force_check_outcome(self.miss) as capture:
            self.telnet(self.hobb, "identify Ysmay=Maud")
        self.assertEqual(capture.target_difficulty, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])
        with force_check_outcome(self.miss) as capture:
            self.telnet(self.hobb, "identify Ysmay=Ysmay")
        self.assertEqual(
            capture.target_difficulty, max(0, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL] - 15)
        )

        with force_check_outcome(self.success):
            self.assertIn("that's unmistakably Ysmay.", self.telnet(self.hobb, "identify Ysmay"))
        self.assertEqual(PersonaDiscovery.objects.count(), 1)
        self.assertIn(
            "You already know exactly who this is.", self.telnet(self.hobb, "identify Ysmay")
        )
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

        FunctionaryFactory(
            role=NPCRoleFactory(name="Barkeep"), room=self.profile, name_override="Old Marta"
        )
        with force_check_outcome(self.botch):
            self.assertIn(
                "You'd swear that's Old Marta... but you're wrong.",
                self.telnet(self.maud, "identify Ysmay"),
            )
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

    def test_the_attempt_is_logged_without_naming_anyone(self) -> None:
        self.telnet(self.ysmay, "persona mask Stag Mask")
        self.telnet(self.hobb, "scene start The Masked Hour")
        with force_check_outcome(self.miss):
            self.telnet(self.hobb, "identify Ysmay")
        logged = Interaction.objects.get(content__contains="studies someone closely")
        self.assertEqual(logged.persona, self.hobb.sheet_data.primary_persona)
        self.assertNotIn("Ysmay", logged.content)
        self.assertNotIn("Stag", logged.content)


class FakeClock:
    """Stands in for ``evennia.utils.delay``: hops run when the test ticks."""

    def __init__(self) -> None:
        self.pending: list[tuple] = []
        self.cancelled = 0

    def delay(self, _seconds, func, *args, **_kwargs):
        self.pending.append((func, args))
        return self

    def cancel(self) -> None:
        self.cancelled += 1
        self.pending.clear()

    def tick(self) -> None:
        func, args = self.pending.pop(0)
        func(*args)


class WalkingAcrossTown(JourneyCase):
    """Ysmay walks from the square to wherever Hobb is, one hop a tick."""

    def setUp(self) -> None:
        super().setUp()
        self.square = self.make_room("The Square")
        self.lane = self.make_room("Tanner's Lane")
        self.market = self.make_room("The Market")
        self.cellar = self.make_room("A Cellar")
        for room in (self.square, self.lane, self.market):
            RoomProfileFactory(objectdb=room, is_public=True)
        self.cellar_profile = RoomProfileFactory(objectdb=self.cellar, is_public=False)
        exit_between("east", self.square, self.lane)
        exit_between("west", self.lane, self.square)
        exit_between("east", self.lane, self.market)
        exit_between("west", self.market, self.lane)
        exit_between("down", self.market, self.cellar)
        exit_between("up", self.cellar, self.market)
        self.ysmay = self.make_player("Ysmay", room=self.square)
        self.hobb = self.make_player("Hobb", room=self.market)
        self.clock = FakeClock()
        patcher = patch("actions.definitions.movement.delay", self.clock.delay)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.watch(self.ysmay, self.hobb)

    def test_she_walks_to_hobb(self) -> None:
        for line, reply in (
            ("travel", "Travel to whom? (Usage: travel <character name> | travel stop)"),
            ("travel Nobody", "Could not find 'Nobody'."),
            ("travel stop", "You aren't traveling anywhere."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line))
        self.assertIn("You set off.", self.telnet(self.ysmay, "travel Hobb"))
        self.assertEqual(self.ysmay.location, self.square)
        self.clock.tick()
        self.assertEqual(self.ysmay.location, self.lane)
        self.assertNotIn("You arrive.", self.said(self.ysmay))
        self.clock.tick()
        self.assertEqual(self.ysmay.location, self.market)
        self.assertTold(self.ysmay, "You arrive.")
        self.assertEqual(self.clock.pending, [])
        self.assertIn("You're already there.", self.telnet(self.ysmay, "travel Hobb"))

        self.hobb.location = self.cellar
        self.assertIn("There's no clear public path there.", self.telnet(self.ysmay, "travel Hobb"))
        self.assertEqual(self.ysmay.location, self.market)

    def test_she_stops_and_the_way_can_close(self) -> None:
        self.telnet(self.ysmay, "travel Hobb")
        self.assertIn("You stop where you are.", self.telnet(self.ysmay, "travel stop"))
        self.assertEqual(self.clock.cancelled, 1)
        self.assertEqual(self.ysmay.location, self.square)
        self.assertIn("You aren't traveling anywhere.", self.telnet(self.ysmay, "travel stop"))

        self.telnet(self.ysmay, "travel Hobb")
        self.clock.tick()
        self.assertEqual(self.ysmay.location, self.lane)
        market_profile = self.market.room_profile
        market_profile.is_public = False
        market_profile.save(update_fields=["is_public"])
        self.clock.tick()
        self.assertEqual(self.ysmay.location, self.lane)
        self.assertTold(self.ysmay, "Your route stops here: That path is no longer open.")
        self.assertEqual(self.clock.pending, [])
        self.assertIn("You aren't traveling anywhere.", self.telnet(self.ysmay, "travel stop"))
