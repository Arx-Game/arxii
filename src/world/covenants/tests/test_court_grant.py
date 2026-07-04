"""Tests for Court grant ceiling + monotonic raise services (#1718)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.court_grant import (
    completed_court_mission_count,
    court_grant_ceiling,
    raise_court_pact_grant,
)
from world.covenants.exceptions import CourtGrantNotMonotonicError
from world.covenants.factories import CovenantFactory
from world.covenants.services import swear_court_pact
from world.missions.constants import MissionStatus
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import NPCServiceOfferFactory
from world.npc_services.models import NPCRole
from world.npc_services.services import adjust_npc_affection


class CompletedCourtMissionCountTests(TestCase):
    def setUp(self):
        self.covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        self.servant = CharacterSheetFactory()
        self.role = NPCRole.objects.create(
            name="Test Court Role", faction_affiliation=self.covenant.organization
        )

    def test_counts_only_complete_missions_for_this_org(self):
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.MISSION)
        instance = MissionInstanceFactory(source_offer=offer, status=MissionStatus.COMPLETE)
        MissionParticipantFactory(instance=instance, character=self.servant.character)
        self.assertEqual(
            completed_court_mission_count(character_sheet=self.servant, covenant=self.covenant),
            1,
        )

    def test_ignores_active_missions(self):
        offer = NPCServiceOfferFactory(role=self.role, kind=OfferKind.MISSION)
        instance = MissionInstanceFactory(source_offer=offer, status=MissionStatus.ACTIVE)
        MissionParticipantFactory(instance=instance, character=self.servant.character)
        self.assertEqual(
            completed_court_mission_count(character_sheet=self.servant, covenant=self.covenant),
            0,
        )


class CourtGrantCeilingTests(TestCase):
    def setUp(self):
        self.master_sheet = CharacterSheetFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=self.master_sheet)
        self.servant = CharacterSheetFactory()
        # CharacterSheetFactory's primary_persona post_generation hook already
        # provisions a PRIMARY Persona for both sheets (world/character_sheets/CLAUDE.md
        # invariant) — no explicit PersonaFactory(...) call needed here.

    def test_base_headroom_with_no_affection_or_missions(self):
        self.assertEqual(
            court_grant_ceiling(covenant=self.covenant, servant_sheet=self.servant),
            1,  # CourtGrantConfig.base_headroom default
        )

    def test_affection_raises_ceiling(self):
        adjust_npc_affection(
            self.servant.primary_persona, self.master_sheet.primary_persona, delta=25
        )
        # base_headroom(1) + 25 // affection_divisor(10) = 1 + 2 = 3
        self.assertEqual(court_grant_ceiling(covenant=self.covenant, servant_sheet=self.servant), 3)

    def test_debt_reduces_ceiling(self):
        from world.npc_services.models import NPCStanding
        from world.npc_services.services import incur_npc_debt

        standing, _ = NPCStanding.objects.get_or_create(
            persona=self.servant.primary_persona,
            npc_persona=self.master_sheet.primary_persona,
        )
        incur_npc_debt(standing, 1, current_affection=0, current_missions_completed=0)
        self.assertEqual(court_grant_ceiling(covenant=self.covenant, servant_sheet=self.servant), 0)


class RaiseCourtPactGrantTests(TestCase):
    def test_raises_the_cap(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=2)
        raised = raise_court_pact_grant(pact=pact, new_cap=5)
        self.assertEqual(raised.granted_pull_cap, 5)

    def test_rejects_a_lower_cap(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=5)
        with self.assertRaises(CourtGrantNotMonotonicError):
            raise_court_pact_grant(pact=pact, new_cap=3)

    def test_equal_cap_is_a_no_op_not_an_error(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=4)
        raised = raise_court_pact_grant(pact=pact, new_cap=4)
        self.assertEqual(raised.granted_pull_cap, 4)
