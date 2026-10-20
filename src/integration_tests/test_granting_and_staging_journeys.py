"""Journeys for the commands ledger (#3657, tranche 15): the GM grants and staging group,
the mission party and the house's domains. A GM dresses a room with a position
blueprint and awards a distinction; a mission holder invites a companion; a wronged
character answers a secret; a house leader runs a domain. Each types what the person
types through the real command handler and asserts what they were told and what the
rows now hold."""

from __future__ import annotations

from django.test import override_settings

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.factories import AreaFactory
from world.areas.positioning.factories import PositionBlueprintFactory
from world.areas.positioning.models import ObjectPosition, Position
from world.areas.positioning.services import add_blueprint_position
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInvite, MissionParticipant
from world.missions.services.run import staff_assign_mission
from world.progression.models.rewards import ExperiencePointsData
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.relationships.factories import GrievanceOptionFactory
from world.relationships.models import CharacterRelationship
from world.roster.models import RosterEntry
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import grant_secret_knowledge
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import DomainHolding, HoldingKind, HouseStature, StatureBand
from world.societies.houses.services import create_domain
from world.societies.models import OrganizationOffice
from world.vitals.seeds import ensure_foundational_capabilities


def staff(case: JourneyCase, character) -> None:
    """Make ``character``'s account staff, the way a staffer's is."""
    account = case.account_of(character)
    account.is_staff = True
    account.save(update_fields=["is_staff"])


def gm(case: JourneyCase, character, level: str) -> None:
    """Give ``character``'s account GM trust at ``level``."""
    GMProfileFactory(account=case.account_of(character), level=level)


def entry_of(character) -> RosterEntry:
    """The roster entry ``make_player`` gave ``character``."""
    return RosterEntry.objects.get(character_sheet_id=character.pk)


def fund_xp(case: JourneyCase, character, amount: int) -> ExperiencePointsData:
    """Give ``character``'s account ``amount`` XP to spend."""
    return ExperiencePointsData.objects.create(
        account=case.account_of(character), total_earned=amount, total_spent=0
    )


def xp_spent(case: JourneyCase, character) -> int:
    tracker = ExperiencePointsData.objects.get(account=case.account_of(character))
    tracker.refresh_from_db()
    return tracker.total_spent


@override_settings(SEED_SAMPLE_CONTENT=True)  # the Movement capability is sample-seeded
class SettingTheStage(JourneyCase):
    """Hobb, newly approved as a GM, stages the solar with a position blueprint;
    Ysmay, a player, may only read the room; Marrow is staff."""

    def setUp(self) -> None:
        super().setUp()
        self.solar = self.make_room("The Solar")
        self.ysmay = self.make_player("Ysmay", room=self.solar)
        self.hobb = self.make_player("Hobb", room=self.solar)
        self.marrow = self.make_player("Marrow", room=self.make_room("The Gallery"))
        gm(self, self.hobb, GMLevel.STARTING)
        staff(self, self.marrow)
        ensure_foundational_capabilities()  # taking a position asks whether one can move
        self.lone_dais = PositionBlueprintFactory(name="Lone Dais")
        add_blueprint_position(self.lone_dais, "Center", description="The centre")
        self.tight_alley = PositionBlueprintFactory(name="Tight Alley")
        add_blueprint_position(self.tight_alley, "Alley", description="A narrow passage")

    def test_a_starting_gm_stages_the_room_and_restages_it(self) -> None:
        self.assertIn("No positions are set in this room yet.", self.telnet(self.hobb, "setstage"))
        told = self.telnet(self.hobb, "setstage list")
        self.assertIn("Position blueprints:", told)
        self.assertIn(f"  {self.lone_dais.pk}: Lone Dais", told)
        self.assertIn(f"  {self.tight_alley.pk}: Tight Alley", told)
        self.assertIn(
            "Set the stage with which blueprint? (setstage list to see them.)",
            self.telnet(self.hobb, "setstage replace"),
        )
        self.assertIn(
            "No such blueprint. (setstage list to see them.)",
            self.telnet(self.hobb, "setstage Grand Hall"),
        )
        self.assertIn("GM trust required.", self.telnet(self.ysmay, "setstage Lone Dais"))
        self.assertFalse(Position.objects.filter(room=self.solar).exists())

        self.assertIn(
            "You set the stage with Lone Dais: Center.",
            self.telnet(self.hobb, "setstage Lone Dais"),
        )
        self.assertEqual(
            list(Position.objects.filter(room=self.solar).values_list("name", flat=True)),
            ["Center"],
        )
        told = self.telnet(self.hobb, "setstage")
        self.assertIn("Positions here:", told)
        self.assertIn("  Center", told)

        # A second staging needs the word; a staged room is not silently doubled.
        self.assertIn(
            "This room is already staged.", self.telnet(self.hobb, "setstage Tight Alley")
        )
        self.assertIn(
            "You set the stage with Tight Alley: Alley.",
            self.telnet(self.hobb, "setstage Tight Alley replace"),
        )
        self.assertEqual(
            list(Position.objects.filter(room=self.solar).values_list("name", flat=True)),
            ["Alley"],
        )

        # Someone standing on the stage keeps it from being struck.
        self.telnet(self.ysmay, "position Alley")
        self.assertTrue(ObjectPosition.objects.filter(position__room=self.solar).exists())
        self.assertIn(
            "Cannot restage an occupied room.",
            self.telnet(self.hobb, f"setstage {self.lone_dais.pk} replace"),
        )
        self.assertTrue(Position.objects.filter(room=self.solar, name="Alley").exists())

    def test_staff_stage_by_id_and_the_hub_names_the_room_default(self) -> None:
        self.assertIn(
            "You set the stage with Lone Dais: Center.",
            self.telnet(self.marrow, f"setstage {self.lone_dais.pk}"),
        )
        self.assertTrue(Position.objects.filter(room=self.marrow.location, name="Center").exists())

        RoomProfileFactory(objectdb=self.solar, default_blueprint=self.tight_alley)
        told = self.telnet(self.ysmay, "setstage")
        self.assertIn("No positions are set in this room yet.", told)
        self.assertIn(f"Default blueprint here: Tight Alley (pk {self.tight_alley.pk})", told)


class AwardingADistinction(JourneyCase):
    """Ravenna, a Junior GM, awards Ysmay a distinction for a story beat and takes a
    curse off her; Hobb, a Starting GM, and Ysmay herself may not; Marrow is staff."""

    def setUp(self) -> None:
        super().setUp()
        self.solar = self.make_room("The Solar")
        self.ysmay = self.make_player("Ysmay", room=self.solar)
        self.hobb = self.make_player("Hobb", room=self.solar)
        self.ravenna = self.make_player("Ravenna", room=self.solar)
        self.marrow = self.make_player("Marrow", room=self.solar)
        gm(self, self.ravenna, GMLevel.JUNIOR)
        gm(self, self.hobb, GMLevel.STARTING)
        staff(self, self.marrow)
        fund_xp(self, self.ysmay, 100)
        fund_xp(self, self.hobb, 0)
        self.silver_tongue = DistinctionFactory(
            name="Silver Tongue", slug="silver-tongue", cost_per_rank=10, max_rank=3
        )
        self.cursed = DistinctionFactory(
            name="Cursed", slug="cursed", cost_per_rank=-50, max_rank=1
        )

    def held(self, character, distinction) -> CharacterDistinction | None:
        return CharacterDistinction.objects.filter(
            character=character.sheet_data, distinction=distinction
        ).first()

    def test_a_junior_gm_awards_a_distinction_and_ranks_it_up(self) -> None:
        self.assertIn(
            "GM trust required.", self.telnet(self.ysmay, "grant_distinction Hobb=silver-tongue")
        )
        self.assertIn(
            "Requires Junior GM or higher.",
            self.telnet(self.hobb, "grant_distinction Ysmay=silver-tongue"),
        )
        self.assertIn(
            "Usage: grant_distinction <character>=<distinction slug>[,rank]",
            self.telnet(self.ravenna, "grant_distinction Ysmay"),
        )
        self.assertIn(
            "rank must be a whole number.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue,lots"),
        )
        self.assertIn(
            "Silver Tongue has a maximum rank of 3.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue,9"),
        )
        self.assertIn(
            "No active distinction found with slug 'golden-tongue'.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=golden-tongue"),
        )
        self.assertIn(
            "Could not find 'Nobody'.",
            self.telnet(self.ravenna, "grant_distinction Nobody=silver-tongue"),
        )
        self.assertIn(
            "That is not a character.",
            self.telnet(self.ravenna, "grant_distinction The Solar=silver-tongue"),
        )
        self.assertFalse(
            CharacterDistinction.objects.filter(character=self.ysmay.sheet_data).exists()
        )

        self.assertIn(
            "Awarded 'Silver Tongue' (rank 1) to Ysmay.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue"),
        )
        held = self.held(self.ysmay, self.silver_tongue)
        self.assertEqual((held.rank, held.origin), (1, DistinctionOrigin.GM_AWARD))
        self.assertEqual(xp_spent(self, self.ysmay), 10)

        # A second award ranks the held distinction up; the typed rank is checked against
        # the ceiling and then each award advances one step (recorded on #3657).
        self.assertIn(
            "Awarded 'Silver Tongue' (rank 2) to Ysmay.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue"),
        )
        self.assertIn(
            "Awarded 'Silver Tongue' (rank 3) to Ysmay.",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue,3"),
        )
        self.assertEqual(self.held(self.ysmay, self.silver_tongue).rank, 3)
        self.assertEqual(xp_spent(self, self.ysmay), 30)

        # At the ceiling a further award is refused before any XP moves.
        self.assertIn(
            "Ysmay already holds Silver Tongue at its highest rank (3).",
            self.telnet(self.ravenna, "grant_distinction Ysmay=silver-tongue"),
        )
        self.assertEqual(xp_spent(self, self.ysmay), 30)

        # XP is the character's to pay: a character with none is refused.
        self.assertIn(
            "Need 10 XP, have 0.", self.telnet(self.marrow, "grant_distinction Hobb=silver-tongue")
        )
        self.assertIsNone(self.held(self.hobb, self.silver_tongue))

    def test_a_curse_is_free_to_lay_and_costs_xp_to_lift(self) -> None:
        self.assertIn(
            "Usage: grant_distinction/remove <character>=<distinction slug>",
            self.telnet(self.ravenna, "grant_distinction/remove Ysmay"),
        )
        self.assertIn(
            "Ysmay does not have Cursed.",
            self.telnet(self.ravenna, "grant_distinction/remove Ysmay=cursed"),
        )
        self.assertIn(
            "Awarded 'Cursed' (rank 1) to Ysmay.",
            self.telnet(self.marrow, "grant_distinction Ysmay=cursed"),
        )
        self.assertEqual(xp_spent(self, self.ysmay), 0)
        self.assertIn(
            "Removed Cursed from Ysmay.",
            self.telnet(self.ravenna, "grant_distinction/remove Ysmay=cursed"),
        )
        self.assertIsNone(self.held(self.ysmay, self.cursed))
        self.assertEqual(xp_spent(self, self.ysmay), 50)
        self.assertIn(
            "Requires Junior GM or higher.",
            self.telnet(self.hobb, "grant_distinction/remove Ysmay=cursed"),
        )


class InvitingToAMission(JourneyCase):
    """Ysmay holds a mission contract and brings Hobb along; Maud declines; nobody
    else may invite or answer for them."""

    def setUp(self) -> None:
        super().setUp()
        self.square = self.make_room("The Square")
        self.ysmay = self.make_player("Ysmay", room=self.square)
        self.hobb = self.make_player("Hobb", room=self.square)
        self.maud = self.make_player("Maud", room=self.square)
        template = MissionTemplateFactory(name="Carry a letter")
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        self.run = staff_assign_mission(template, self.ysmay)

    def on_the_mission(self, character) -> bool:
        return MissionParticipant.objects.filter(
            instance=self.run, character_id=character.pk
        ).exists()

    def test_the_holder_invites_and_the_invitee_answers(self) -> None:
        self.assertIn("Usage:", self.telnet(self.ysmay, "mission invite"))
        self.assertIn(
            "Mission id must be a number.", self.telnet(self.ysmay, "mission invite letter Hobb")
        )
        self.assertIn(
            "Invite whom? Usage: mission invite <id> <name>",
            self.telnet(self.ysmay, f"mission invite {self.run.pk}"),
        )
        self.assertIn(
            "Could not find 'Nobody'.",
            self.telnet(self.ysmay, f"mission invite {self.run.pk} Nobody"),
        )
        self.assertIn(
            "You are not part of that mission.",
            self.telnet(self.hobb, f"mission invite {self.run.pk} Ysmay"),
        )
        self.assertFalse(MissionInvite.objects.filter(instance=self.run).exists())

        told = self.telnet(self.ysmay, f"mission invite {self.run.pk} Hobb")
        invite = MissionInvite.objects.get(
            instance=self.run, target_persona__character_sheet_id=self.hobb.pk
        )
        self.assertIn(
            f"You invite Hobb to join mission #{self.run.pk} (invite #{invite.pk}).", told
        )
        self.assertEqual(invite.response, MissionInvite.Response.PENDING)

        told = self.telnet(self.hobb, "mission")
        self.assertIn(f"[invite #{invite.pk}] Carry a letter", told)
        self.assertIn(
            "Which invitation? Usage: mission accept <invite-id>",
            self.telnet(self.hobb, "mission accept"),
        )
        self.assertIn(
            "You are not part of that mission.",
            self.telnet(self.maud, f"mission accept {invite.pk}"),
        )
        self.assertFalse(self.on_the_mission(self.hobb))

        self.assertIn(
            f"You accept the invitation to mission #{self.run.pk}.",
            self.telnet(self.hobb, f"mission accept {invite.pk}"),
        )
        self.assertTrue(self.on_the_mission(self.hobb))
        self.assertIn(
            "You have already responded to that invitation.",
            self.telnet(self.hobb, f"mission accept {invite.pk}"),
        )
        self.assertIn(
            "They are already part of that mission.",
            self.telnet(self.ysmay, f"mission invite {self.run.pk} Hobb"),
        )
        self.assertNotIn("[invite #", self.telnet(self.hobb, "mission"))

        # A companion is on the mission but is not its holder.
        self.assertIn(
            "Only the contract holder may invite others.",
            self.telnet(self.hobb, f"mission invite {self.run.pk} Maud"),
        )

    def test_an_invitation_declined_leaves_the_party_as_it_was(self) -> None:
        self.telnet(self.ysmay, f"mission invite {self.run.pk} Maud")
        invite = MissionInvite.objects.get(instance=self.run)
        self.assertIn(
            f"You decline the invitation to mission #{self.run.pk}.",
            self.telnet(self.maud, f"mission decline {invite.pk}"),
        )
        invite.refresh_from_db()
        self.assertEqual(invite.response, MissionInvite.Response.DECLINED)
        self.assertFalse(self.on_the_mission(self.maud))
        self.assertIn(
            "You have already responded to that invitation.",
            self.telnet(self.maud, f"mission accept {invite.pk}"),
        )
        self.assertIn(
            "You are not part of that mission.", self.telnet(self.maud, "mission decline 999999")
        )


class AnsweringAWrong(JourneyCase):
    """Ysmay learns that Hobb poisoned her sister and decides how it lands on her
    regard for him."""

    def setUp(self) -> None:
        super().setUp()
        self.square = self.make_room("The Square")
        self.ysmay = self.make_player("Ysmay", room=self.square)
        self.hobb = self.make_player("Hobb", room=self.square)
        self.poisoning = SecretFactory(
            subject_sheet=self.hobb.sheet_data, content="Hobb poisoned Ysmay's sister."
        )
        self.theft = SecretFactory(
            subject_sheet=self.hobb.sheet_data, content="Hobb stole her ring."
        )
        for secret in (self.poisoning, self.theft):
            SecretVictimFactory(
                secret=secret, organization=None, persona=self.ysmay.sheet_data.primary_persona
            )
        grant_secret_knowledge(roster_entry=entry_of(self.ysmay), secret=self.poisoning)
        self.unrelated = SecretFactory(content="Someone else's business.")
        self.furious = GrievanceOptionFactory(label="Furious Revelation", conflict_points=50)
        self.quiet = GrievanceOptionFactory(label="Quiet Hurt", conflict_points=10)

    def conflict(self) -> int:
        side = CharacterRelationship.objects.get(
            source=self.ysmay.sheet_data, target=self.hobb.sheet_data
        )
        side.refresh_from_db()
        return side.conflict

    def test_a_wronged_character_answers_each_secret_once(self) -> None:
        self.assertIn(
            "There are no secrets you may answer with a grievance right now.",
            self.telnet(self.hobb, "+grievance"),
        )
        told = self.telnet(self.ysmay, "+grievance")
        self.assertIn(f"[{self.poisoning.pk}] Hobb poisoned Ysmay's sister.", told)
        self.assertNotIn("Hobb stole her ring.", told)  # a wrong she has not learned of
        self.assertIn(f"[{self.furious.pk}] Furious Revelation", told)
        self.assertIn(f"[{self.quiet.pk}] Quiet Hurt", told)

        self.assertIn(
            "Name the secret by its number (see +grievance).",
            self.telnet(self.ysmay, "+grievance the poisoning = Furious Revelation"),
        )
        self.assertIn(
            "That is not a secret you may answer with a grievance.",
            self.telnet(self.ysmay, f"+grievance {self.unrelated.pk} = Furious Revelation"),
        )
        self.assertIn(
            "That is not a secret you may answer with a grievance.",
            self.telnet(self.ysmay, f"+grievance {self.theft.pk} = Furious Revelation"),
        )
        self.assertIn(
            "That is not an available response (see +grievance).",
            self.telnet(self.ysmay, f"+grievance {self.poisoning.pk} = Shrug"),
        )
        self.assertFalse(
            CharacterRelationship.objects.filter(
                source=self.ysmay.sheet_data, target=self.hobb.sheet_data
            ).exists()
        )

        told = self.telnet(self.ysmay, f"+grievance {self.poisoning.pk} = Furious Revelation")
        self.assertIn("You answer the wrong against you:", told)
        self.assertIn("Furious Revelation", told)
        self.assertEqual(self.conflict(), 50)

        # Answered once: it leaves the menu and cannot be answered again.
        self.assertIn(
            "That is not a secret you may answer with a grievance.",
            self.telnet(self.ysmay, f"+grievance {self.poisoning.pk} = Quiet Hurt"),
        )
        self.assertIn(
            "There are no secrets you may answer with a grievance right now.",
            self.telnet(self.ysmay, "grievance"),
        )
        self.assertEqual(self.conflict(), 50)

        # Learning the second wrong offers it; the response may be named by number.
        grant_secret_knowledge(roster_entry=entry_of(self.ysmay), secret=self.theft)
        self.assertIn(
            f"[{self.theft.pk}] Hobb stole her ring.", self.telnet(self.ysmay, "+grievance")
        )
        told = self.telnet(self.ysmay, f"+grievance {self.theft.pk} = {self.quiet.pk}")
        self.assertIn("Quiet Hurt", told)
        self.assertEqual(self.conflict(), 60)


class RunningADomain(JourneyCase):
    """Ysmay leads House Westrock and runs its vale; Hobb, an outsider, is made its
    steward and runs it until she vacates the office; Maud looks on."""

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("Westrock Hall")
        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.hobb = self.make_player("Hobb", room=self.hall)
        self.maud = self.make_player("Maud", room=self.hall)
        self.westrock = OrganizationFactory(name="House Westrock")
        self.vale = create_domain(area=AreaFactory(), name="Westrock Vale", owner_org=self.westrock)
        eastmarch = OrganizationFactory(name="House Eastmarch")
        create_domain(area=AreaFactory(), name="Eastmarch", owner_org=eastmarch)
        OrganizationMembershipFactory(
            organization=self.westrock, persona=self.ysmay.sheet_data.primary_persona, rank=1
        )
        self.farmland = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        self.orchard = HoldingKind.objects.create(
            name="Orchard", stream_kind="domain_tax", base_gross=500, site_kind="land"
        )

    def test_the_leader_runs_the_vale_and_appoints_a_steward(self) -> None:
        self.assertIn("You don't run any domains.", self.telnet(self.hobb, "domain"))
        told = self.telnet(self.ysmay, "domain")
        self.assertIn("Domains you run:", told)
        self.assertIn("  Westrock Vale  [prosperity", told)
        self.assertIn(
            # Spaced separators: a bare "|h" or "|i" is an Evennia colour code on telnet.
            "Usage: domain [list | offices | holding | improve |",
            self.telnet(self.ysmay, "domain plough"),
        )

        # A holding.
        self.assertIn(
            "Usage: domain holding <domain> <holding-kind> [name=<text>]",
            self.telnet(self.ysmay, "domain holding"),
        )
        self.assertIn(
            "No holding kind called 'Vineyard'.",
            self.telnet(self.ysmay, "domain holding Westrock Vale Vineyard"),
        )
        self.assertIn(
            "You don't run a domain named 'Eastmarch'.",
            self.telnet(self.ysmay, "domain holding Eastmarch Farmland"),
        )
        self.assertIn(
            "You don't run any domains.",
            self.telnet(self.hobb, "domain holding Westrock Vale Farmland"),
        )
        self.assertIn(
            "Westrock Vale gains a new holding: South Fields.",
            self.telnet(self.ysmay, "domain holding Westrock Vale Farmland name=South Fields"),
        )
        south_fields = DomainHolding.objects.get(domain=self.vale, name="South Fields")
        self.assertEqual(south_fields.kind, self.farmland)
        # The sole domain may go unnamed; a holding that needs ground cannot be sited from
        # telnet (recorded on #3657).
        self.assertIn(
            "This holding needs ground to stand on.",
            self.telnet(self.ysmay, "domain holding Orchard"),
        )
        self.assertEqual(DomainHolding.objects.filter(domain=self.vale).count(), 1)

        # The steward's office.
        self.assertIn("House Westrock has no offices.", self.telnet(self.ysmay, "domain offices"))
        self.assertIn(
            "Usage: domain appoint <domain> <char> [title=<text>] [check=<trait>]",
            self.telnet(self.ysmay, "domain appoint Hobb"),
        )
        self.assertIn(
            "Could not find 'Nobody'.",
            self.telnet(self.ysmay, "domain appoint Westrock Vale Nobody"),
        )
        self.assertIn(
            "No trait called 'Bookkeeping'.",
            self.telnet(self.ysmay, "domain appoint Westrock Vale Hobb check=Bookkeeping"),
        )
        self.assertIn(
            "Hobb is appointed Minister of the Domains.",
            self.telnet(
                self.ysmay, "domain appoint Westrock Vale Hobb title=Minister of the Domains"
            ),
        )
        office = OrganizationOffice.objects.get(organization=self.westrock, slug="domain-steward")
        self.assertEqual(office.holder, self.hobb.sheet_data.primary_persona)
        told = self.telnet(self.ysmay, "domain offices")
        self.assertIn("Offices of House Westrock:", told)
        self.assertIn("  Minister of the Domains: Hobb", told)

        # The steward runs the vale but holds no rank.
        self.assertIn("  Westrock Vale  [prosperity", self.telnet(self.hobb, "domain"))
        self.assertIn(
            "Westrock Vale gains a new holding: North Fields.",
            self.telnet(self.hobb, "domain holding Farmland name=North Fields"),
        )
        self.assertIn(
            "Only a house leader may appoint or vacate an office.",
            self.telnet(self.hobb, "domain appoint Westrock Vale Maud"),
        )
        self.assertIn(
            "Only a house leader may appoint or vacate an office.",
            self.telnet(self.hobb, "domain vacate"),
        )
        self.assertEqual(
            OrganizationOffice.objects.get(pk=office.pk).holder,
            self.hobb.sheet_data.primary_persona,
        )

        self.assertIn(
            "The domain-steward office is vacated.", self.telnet(self.ysmay, "domain vacate")
        )
        self.assertIsNone(OrganizationOffice.objects.get(pk=office.pk).holder)
        self.assertIn("You don't run any domains.", self.telnet(self.hobb, "domain"))
        self.assertIn(
            "  Minister of the Domains: vacant", self.telnet(self.ysmay, "domain offices")
        )

    def test_improvements_transfers_and_the_stature_panel(self) -> None:
        self.assertIn(
            "Usage: domain improve <domain> cost=<n>", self.telnet(self.ysmay, "domain improve")
        )
        self.assertIn(
            "Usage: domain improve <domain> cost=<n>",
            self.telnet(self.ysmay, "domain improve cost=lots"),
        )
        self.assertIn(
            "Choose which holding to improve.",
            self.telnet(self.ysmay, "domain improve cost=500 gross=50"),
        )
        self.assertFalse(Project.objects.filter(kind=ProjectKind.DOMAIN_IMPROVEMENT).exists())
        self.assertIn(
            "An improvement project for Westrock Vale begins.",
            self.telnet(self.ysmay, "domain improve Westrock Vale cost=500 prosperity=2"),
        )
        project = Project.objects.get(kind=ProjectKind.DOMAIN_IMPROVEMENT)
        self.assertEqual(project.threshold_target, 5)
        self.assertEqual(project.owner_persona, self.ysmay.sheet_data.primary_persona)
        self.telnet(self.ysmay, "domain holding Farmland name=South Fields")
        holding = DomainHolding.objects.get(domain=self.vale)
        self.assertIn(
            "An improvement project for Westrock Vale begins.",
            self.telnet(self.ysmay, f"domain improve cost=200 gross=50 holding={holding.pk}"),
        )
        self.assertEqual(Project.objects.filter(kind=ProjectKind.DOMAIN_IMPROVEMENT).count(), 2)

        # Food moves between granaries; the vale has none yet.
        self.assertIn(
            "Usage: domain transfer <source-domain> <target-domain> amount=<n>",
            self.telnet(self.ysmay, "domain transfer Westrock Vale Eastmarch"),
        )
        self.assertIn(
            "Amount must be a positive number.",
            self.telnet(self.ysmay, "domain transfer Westrock Vale Eastmarch amount=some"),
        )
        self.assertIn(
            "No domain named 'Nowhere'.",
            self.telnet(self.ysmay, "domain transfer Westrock Vale Nowhere amount=5"),
        )
        self.assertIn(
            "Westrock Vale has no food stockpile.",
            self.telnet(self.ysmay, "domain transfer Westrock Vale Eastmarch amount=5"),
        )

        # The stature panel, before and after the house is reckoned.
        self.assertIn(
            "House Westrock has no reckoned stature yet.", self.telnet(self.ysmay, "domain stature")
        )
        band = StatureBand.objects.create(
            name="Formidable",
            rank=2,
            min_percentile=75,
            headline_template="PLACEHOLDER Few would move against {org}.",
        )
        HouseStature.objects.create(
            organization=self.westrock,
            perceived_total=9_000,
            true_total=10_000,
            renown_strength=5_000,
            military_strength=2_000,
            economic_strength=500,
            allied_strength=1_500,
            crisis_penalty=250,
            band=band,
            realm_rank=2,
            realm_cohort_size=7,
        )
        told = self.telnet(self.ysmay, "domain stature Westrock Vale")
        self.assertIn("Stature of House Westrock:", told)
        self.assertIn("Few would move against House Westrock.", told)
        self.assertIn("Held Formidable.", told)
        self.assertIn("The world reckons them at 9000 (in truth 10000).", told)
        self.assertIn("Renown 5000 / military 2000 / economy 500 / allies 1500", told)
        self.assertIn("Open troubles drag them by 250.", told)
        self.assertIn("Ranked 2 of 7 polities of the realm.", told)
        self.assertIn("You don't run any domains.", self.telnet(self.maud, "domain stature"))

        # Two domains need naming.
        create_domain(area=AreaFactory(), name="Westrock Mill", owner_org=self.westrock)
        told = self.telnet(self.ysmay, "domain vacate")
        self.assertIn("Which domain? You run:", told)
        self.assertIn("Westrock Vale", told)
        self.assertIn("Westrock Mill", told)
        self.assertIn(
            "You don't run a domain named 'Nowhere'.",
            self.telnet(self.ysmay, "domain offices Nowhere"),
        )
