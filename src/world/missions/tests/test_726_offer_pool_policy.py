"""Tests for the #726 mission-offer POOL count + draw-priority policy.

Covers the three pieces shipped for #726:

- ``offer_policy.mission_pool_count`` — standing-banded count (strangers see
  one trial job, trusted contacts a full slate).
- ``MissionOfferDetails.draw_priority`` + ``_draw_pool_offers`` priority tiers
  — chain-unlock / high-stakes offers surface ahead of the general pool.
- The live composition — ``available_offers(session, pool_count=...)`` scales
  the POOL slate by the PC's standing.

The ``has_completed_mission`` predicate leaf (the chain *gate*) is tested in
``world.missions.tests.test_resolvers`` alongside the other leaves.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
    NPCStandingFactory,
)
from world.npc_services.models import NPCServiceOffer
from world.npc_services.offer_policy import mission_pool_count
from world.npc_services.services import (
    _draw_pool_offers,
    _draw_priority_for_offer,
    available_offers,
    start_interaction,
)
from world.scenes.factories import PersonaFactory


def _make_pc():
    """Character + sheet → its auto-created PRIMARY persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


def _make_mission_offer(role, *, label, draw_mode=DrawMode.POOL, draw_priority=0):
    """Full POOL-mode MISSION offer: offer + details + entry-node template."""
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    offer = NPCServiceOfferFactory(
        role=role,
        kind=OfferKind.MISSION,
        label=label,
        draw_mode=draw_mode,
    )
    MissionOfferDetailsFactory(
        offer=offer,
        mission_template=template,
        draw_priority=draw_priority,
    )
    return offer


def _pool_offers(role):
    """The role's POOL offers, ordered for a stable draw input."""
    return list(NPCServiceOffer.objects.filter(role=role, draw_mode=DrawMode.POOL).order_by("pk"))


class MissionPoolCountTests(TestCase):
    """``mission_pool_count`` maps NPC standing → the POOL slate size."""

    @classmethod
    def setUpTestData(cls):
        cls.character, cls.pc_persona = _make_pc()
        cls.npc = PersonaFactory()
        # A role with no org affiliation isolates the NPC-standing input
        # (org count falls back to the floor, so max() is a no-op here).
        cls.role = NPCRoleFactory()

    def test_class1_functionary_gets_floor(self):
        # npc_persona is None → no standing surface → one trial job.
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=None), 1
        )

    def test_no_standing_row_gets_floor(self):
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 1
        )

    def test_neutral_affection_gets_floor(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=0)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 1
        )

    def test_negative_affection_gets_floor(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=-40)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 1
        )

    def test_lower_band_boundary(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=10)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 2
        )

    def test_mid_band(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=25)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 3
        )

    def test_just_below_a_band_uses_lower_band(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=49)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 3
        )

    def test_ceiling_clamp(self):
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=10_000)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 5
        )


class DrawPriorityTests(TestCase):
    """``draw_priority`` tiers: higher tiers are exhausted before lower ones."""

    def test_priority_for_offer_reads_details(self):
        role = NPCRoleFactory()
        offer = _make_mission_offer(role, label="chain", draw_priority=7)
        self.assertEqual(_draw_priority_for_offer(offer), 7)

    def test_high_priority_offer_guaranteed_with_one_slot(self):
        role = NPCRoleFactory()
        chain = _make_mission_offer(role, label="chain", draw_priority=5)
        for i in range(5):
            _make_mission_offer(role, label=f"gen-{i}")
        # Only one slot: the single priority-5 offer must win every time.
        for _ in range(20):
            drawn = _draw_pool_offers(_pool_offers(role), 1)
            self.assertEqual(drawn, [chain])

    def test_priority_fills_before_general_pool(self):
        role = NPCRoleFactory()
        hi = {_make_mission_offer(role, label=f"chain-{i}", draw_priority=3) for i in range(2)}
        for i in range(4):
            _make_mission_offer(role, label=f"gen-{i}")
        # Two slots, two priority offers: the general pool never appears.
        for _ in range(20):
            drawn = set(_draw_pool_offers(_pool_offers(role), 2))
            self.assertEqual(drawn, hi)

    def test_lower_tier_fills_remaining_slots(self):
        role = NPCRoleFactory()
        chain = _make_mission_offer(role, label="chain", draw_priority=4)
        for i in range(4):
            _make_mission_offer(role, label=f"gen-{i}")
        # Three slots, one priority offer → it's always included; the other two
        # come from the general pool.
        for _ in range(20):
            drawn = _draw_pool_offers(_pool_offers(role), 3)
            self.assertEqual(len(drawn), 3)
            self.assertIn(chain, drawn)


class StandingDrivenCountIntegrationTests(TestCase):
    """The live composition: ``available_offers`` slate scales with standing."""

    def setUp(self):
        self.role = NPCRoleFactory()
        self.npc = PersonaFactory()
        for i in range(6):
            _make_mission_offer(self.role, label=f"pool-{i}")

    def _pool_count_listed(self, persona, character):
        count = mission_pool_count(role=self.role, persona=persona, npc_persona=self.npc)
        session = start_interaction(
            role=self.role, persona=persona, character=character, npc_persona=self.npc
        )
        listed = available_offers(session, pool_count=count)
        return len([o for o in listed if o.draw_mode == DrawMode.POOL])

    def test_stranger_sees_one_pool_offer(self):
        character, persona = _make_pc()
        self.assertEqual(self._pool_count_listed(persona, character), 1)

    def test_trusted_contact_sees_full_slate(self):
        character, persona = _make_pc()
        NPCStandingFactory(persona=persona, npc_persona=self.npc, affection=100)
        self.assertEqual(self._pool_count_listed(persona, character), 5)
