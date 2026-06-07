"""Integration test: character simultaneously engaged in Durance + Battle covenants.

Proves that:
  (a) both roles are simultaneously engaged,
  (b) the Battle role's speed_rank governs combat resolution order (precedence),
  (c) when the battle covenant stands down, engagement is blocked and precedence
      falls back to the Durance role.

Mirrors the setUp/fixture pattern from test_resolution.py (CombatEncounterFactory +
CharacterVitals row for can_act), which is the canonical pattern for resolution-order
tests in this repo.

Uses setUp (per-test, not setUpTestData) because make_engaged_member writes through
the SharedMemoryModel identity-map cache; deepcopy during setUpTestData would corrupt
cached handlers across tests. See test_resolution.py for the same reasoning.
"""

from django.test import TestCase

from world.combat.constants import ENTITY_TYPE_NPC, ENTITY_TYPE_PC
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import add_participant, get_resolution_order
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, make_engaged_member
from world.covenants.handlers import can_engage_membership
from world.covenants.services import precedence_role_for_combat, stand_down_battle_covenant
from world.vitals.models import CharacterVitals


class DuranceAndBattleStackingIntegrationTest(TestCase):
    """A character engaged in both a Durance and a risen STANDING Battle covenant.

    This is the "Done when #3" acceptance criterion for Covenants Slice E (#515):
    both covenant types can be engaged simultaneously, the Battle role wins combat
    precedence, and standing down restores Durance-only behaviour.
    """

    def setUp(self) -> None:
        super().setUp()

        # --- Durance covenant + engaged role ---
        # speed_rank=20 is deliberately SLOWER than NPC_SPEED_RANK (15). This makes the
        # resolution-order assertion discriminating: if precedence ever regressed and the
        # Durance role (not the Battle role) drove the participant, the PC would sort AFTER
        # the NPC and the position check below would fail on its own — not only the
        # covenant_role equality check.
        self.durance_cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.durance_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, speed_rank=20)

        # --- Battle covenant: risen (not dormant), STANDING ---
        self.battle_cov = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,  # already risen — no need to fire rise ritual for this test
        )
        self.battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE, speed_rank=1)

        # Build the character with both memberships engaged via make_engaged_member.
        # make_engaged_member creates a fresh CharacterSheet internally when none is
        # given — capture from the first call and reuse for the second.
        self.durance_membership = make_engaged_member(
            covenant=self.durance_cov, covenant_role=self.durance_role
        )
        self.sheet = self.durance_membership.character_sheet

        self.battle_membership = make_engaged_member(
            character_sheet=self.sheet,
            covenant=self.battle_cov,
            covenant_role=self.battle_role,
        )

        # Invalidate the handler cache after both memberships are created so the
        # next call to currently_engaged_roles() sees both rows.
        self.sheet.character.covenant_roles.invalidate()

        # Give the character living vitals so can_act() returns True and the PC
        # appears in get_resolution_order (same pattern as test_resolution.py).
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )

        # Encounter for resolution-order assertions.
        self.encounter = CombatEncounterFactory()

    # ------------------------------------------------------------------
    # (a) Both roles simultaneously engaged
    # ------------------------------------------------------------------

    def test_both_roles_engaged_simultaneously(self) -> None:
        """currently_engaged_roles() contains both the durance and battle roles."""
        engaged = self.sheet.character.covenant_roles.currently_engaged_roles()
        self.assertIn(self.durance_role, engaged)
        self.assertIn(self.battle_role, engaged)
        self.assertEqual(len(engaged), 2)

    # ------------------------------------------------------------------
    # (b) Battle role governs combat resolution order (precedence)
    # ------------------------------------------------------------------

    def test_add_participant_without_explicit_role_uses_battle_role(self) -> None:
        """add_participant with no explicit role picks Battle via precedence_role_for_combat."""
        participant = add_participant(self.encounter, self.sheet)
        self.assertEqual(participant.covenant_role, self.battle_role)

    def test_resolution_order_carries_battle_role_and_sorts_first(self) -> None:
        """The PC entry in get_resolution_order has the battle role; sorts ahead of a slow NPC."""
        participant = add_participant(self.encounter, self.sheet)

        # Add an NPC (NPC_SPEED_RANK = 15) that sits BETWEEN the battle role (1) and the
        # durance role (20). The PC sorts first only because Battle precedence gives it
        # speed_rank=1; a regression to the Durance role (20) would sort it last.
        npc = CombatOpponentFactory(encounter=self.encounter)

        order = get_resolution_order(self.encounter)

        # PC with battle speed_rank=1 should come before the NPC.
        self.assertEqual(len(order), 2)
        entity_type_first, entity_first = order[0]
        self.assertEqual(entity_type_first, ENTITY_TYPE_PC)
        self.assertEqual(entity_first, participant)
        # The participant carries the battle role.
        self.assertEqual(entity_first.covenant_role, self.battle_role)

        entity_type_second, entity_second = order[1]
        self.assertEqual(entity_type_second, ENTITY_TYPE_NPC)
        self.assertEqual(entity_second, npc)

    # ------------------------------------------------------------------
    # (c) Stand-down: battle dormancy blocks engagement; Durance takes over
    # ------------------------------------------------------------------

    def test_stand_down_blocks_battle_engagement_and_restores_durance_precedence(
        self,
    ) -> None:
        """After stand_down_battle_covenant, battle membership is no longer engaged
        and precedence_role_for_combat falls back to the durance role."""
        stand_down_battle_covenant(covenant=self.battle_cov)

        # Refresh instances that were mutated by stand_down (engaged cleared, is_dormant set).
        self.battle_cov.refresh_from_db()
        self.battle_membership.refresh_from_db()

        # Invalidate the character's covenant_roles handler so it re-fetches.
        self.sheet.character.covenant_roles.invalidate()

        # The battle covenant is now dormant → can_engage_membership must return False.
        self.assertTrue(self.battle_cov.is_dormant)
        self.assertFalse(self.battle_membership.engaged)
        self.assertFalse(can_engage_membership(self.battle_membership))

        # Only the durance role remains engaged.
        engaged = self.sheet.character.covenant_roles.currently_engaged_roles()
        self.assertNotIn(self.battle_role, engaged)
        self.assertIn(self.durance_role, engaged)

        # Combat precedence now returns the durance role.
        self.assertEqual(precedence_role_for_combat(self.sheet), self.durance_role)
