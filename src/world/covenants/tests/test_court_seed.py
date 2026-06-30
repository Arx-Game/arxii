"""Tests for the themed Court seed factory (#1589 Task 8).

``make_court_with_mission`` builds a complete, ready-to-engage Court in one call:
a master NPC sheet, a convened COURT covenant with that master as leader, a
servant holding a themed COURT role whose thread pulls a combat FLAT_BONUS, the
master's NPCRole fronting the Court's backing Organization, and an ACTIVE Court
mission the servant is a participant on. The whole point is that the engagement
predicate ``has_active_court_mission`` returns True for the seeded servant.
"""

from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.court_missions import has_active_court_mission
from world.covenants.factories import (
    CourtPactFactory,
    make_court_with_mission,
    wire_court_role_powers_catalog,
)
from world.covenants.models import CharacterCovenantRole, CourtPact, CovenantRoleBonus
from world.magic.constants import EffectKind, TargetKind
from world.magic.models import ThreadPullEffect
from world.missions.constants import MissionStatus


class WireCourtRolePowersCatalogTests(TestCase):
    """The COURT analog of the Battle role-powers catalog."""

    def test_authors_court_role_with_bonus_and_flat_bonus_pull(self):
        role, flat_effects = wire_court_role_powers_catalog()

        # A COURT-scoped role.
        self.assertEqual(role.covenant_type, CovenantType.COURT)

        # A CovenantRoleBonus scaling on the holder's own level.
        self.assertTrue(
            CovenantRoleBonus.objects.filter(covenant_role=role).exists(),
            "themed COURT role must carry a CovenantRoleBonus",
        )

        # At least one tier-1 FLAT_BONUS ThreadPullEffect per resonance.
        self.assertGreaterEqual(len(flat_effects), 1)
        for effect in flat_effects:
            self.assertEqual(effect.target_kind, TargetKind.COVENANT_ROLE)
            self.assertEqual(effect.tier, 1)
            self.assertEqual(effect.effect_kind, EffectKind.FLAT_BONUS)
            self.assertIsNotNone(effect.flat_bonus_amount)

    def test_idempotent(self):
        role_a, _ = wire_court_role_powers_catalog()
        role_b, _ = wire_court_role_powers_catalog()
        self.assertEqual(role_a.pk, role_b.pk)
        # No duplicate FLAT_BONUS tier-1 COVENANT_ROLE rows.
        flat_rows = ThreadPullEffect.objects.filter(
            target_kind=TargetKind.COVENANT_ROLE,
            tier=1,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        self.assertEqual(flat_rows.count(), flat_rows.values("resonance").distinct().count())


class CourtPactFactoryTests(TestCase):
    """The CourtPact factory builds a valid active pact."""

    def test_builds_active_pact(self):
        pact = CourtPactFactory()
        self.assertIsNotNone(pact.pk)
        self.assertIsNone(pact.released_at)
        self.assertEqual(pact.covenant.covenant_type, CovenantType.COURT)
        self.assertIsNotNone(pact.covenant.leader_id)
        self.assertEqual(CourtPact.objects.active().count(), 1)


class MakeCourtWithMissionTests(TestCase):
    """The one-call themed Court seed used by the E2E (Task 9)."""

    @classmethod
    def setUpTestData(cls):
        cls.seed = make_court_with_mission()

    def test_returns_court_covenant_with_leader(self):
        covenant = self.seed.covenant
        self.assertEqual(covenant.covenant_type, CovenantType.COURT)
        self.assertEqual(covenant.leader_id, self.seed.master_sheet.pk)

    def test_servant_holds_themed_court_role(self):
        membership = CharacterCovenantRole.objects.get(
            character_sheet=self.seed.servant_sheet,
            covenant=self.seed.covenant,
        )
        self.assertEqual(membership.covenant_role.covenant_type, CovenantType.COURT)
        # The themed role carries a CovenantRoleBonus + a tier-1 FLAT_BONUS pull.
        self.assertTrue(
            CovenantRoleBonus.objects.filter(covenant_role=membership.covenant_role).exists()
        )

    def test_themed_role_has_flat_bonus_thread_pull(self):
        self.assertTrue(
            ThreadPullEffect.objects.filter(
                target_kind=TargetKind.COVENANT_ROLE,
                tier=1,
                effect_kind=EffectKind.FLAT_BONUS,
            ).exists()
        )

    def test_master_npc_role_fronts_the_court_org(self):
        from world.npc_services.models import NPCRole

        roles = NPCRole.objects.filter(faction_affiliation=self.seed.covenant.organization)
        self.assertTrue(roles.exists())

    def test_active_mission_with_servant_participant(self):
        mission = self.seed.mission_instance
        self.assertEqual(mission.status, MissionStatus.ACTIVE)
        self.assertIsNotNone(mission.source_offer_id)
        self.assertTrue(
            mission.participants.filter(character=self.seed.servant_sheet.character).exists()
        )

    def test_engagement_predicate_true_for_servant(self):
        self.assertTrue(
            has_active_court_mission(
                character_sheet=self.seed.servant_sheet,
                covenant=self.seed.covenant,
            )
        )
