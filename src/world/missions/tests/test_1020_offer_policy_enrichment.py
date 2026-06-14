"""Tests for the #1020 mission-offer policy enrichment.

Two dimensions layered onto the #726 POOL policy:

- **Org-reputation count input** — ``mission_pool_count`` lifts the slate by the
  persona's ``OrganizationReputation`` tier when the role fronts an org
  (``NPCRole.faction_affiliation``); the final count is
  ``max(npc_standing_count, org_count)``.
- **Era arc-replace** — active-Era ("season") offers whose ``percent_replace``
  roll wins are drawn ahead of the general pool, behind explicit
  ``draw_priority`` chains. Randomness is exercised at the deterministic
  0 / 100 boundaries.
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
from world.npc_services.services import _arc_offer_wins, _draw_pool_offers
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationReputationFactory
from world.stories.constants import EraStatus
from world.stories.factories import EraFactory


def _make_pc():
    """Character + sheet → its auto-created PRIMARY persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


def _make_offer(role, *, label, era=None, percent_replace=0, draw_priority=0):
    """POOL-mode MISSION offer with a controllable template era / percent_replace."""
    template = MissionTemplateFactory(created_in_era=era, percent_replace=percent_replace)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    offer = NPCServiceOfferFactory(
        role=role,
        kind=OfferKind.MISSION,
        label=label,
        draw_mode=DrawMode.POOL,
    )
    MissionOfferDetailsFactory(offer=offer, mission_template=template, draw_priority=draw_priority)
    return offer


def _pool_offers(role):
    return list(NPCServiceOffer.objects.filter(role=role, draw_mode=DrawMode.POOL).order_by("pk"))


class OrgReputationCountTests(TestCase):
    """``mission_pool_count`` folds org reputation in via ``max(npc, org)``."""

    @classmethod
    def setUpTestData(cls):
        cls.character, cls.pc_persona = _make_pc()
        cls.npc = PersonaFactory()
        cls.org = OrganizationFactory()
        cls.role = NPCRoleFactory(faction_affiliation=cls.org)
        cls.role_no_org = NPCRoleFactory()  # faction_affiliation is None

    def test_no_affiliation_skips_org_path(self):
        self.assertEqual(
            mission_pool_count(role=self.role_no_org, persona=self.pc_persona, npc_persona=None), 1
        )

    def test_affiliated_role_no_rep_row_is_floor(self):
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=None), 1
        )

    def test_unknown_tier_gives_no_lift(self):
        # value 0 → UNKNOWN tier (rank 4, below the FAVORED floor) → count 1.
        OrganizationReputationFactory(persona=self.pc_persona, organization=self.org, value=0)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=None), 1
        )

    def test_favored_tier_lifts_count(self):
        # value 150 → FAVORED (rank 5) → org band 2.
        OrganizationReputationFactory(persona=self.pc_persona, organization=self.org, value=150)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=None), 2
        )

    def test_revered_tier_full_slate(self):
        # value 900 → REVERED (rank 8) → org band 5.
        OrganizationReputationFactory(persona=self.pc_persona, organization=self.org, value=900)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=None), 5
        )

    def test_max_of_npc_and_org_takes_npc(self):
        # NPC affection 25 → 3; org FAVORED → 2; max == 3.
        NPCStandingFactory(persona=self.pc_persona, npc_persona=self.npc, affection=25)
        OrganizationReputationFactory(persona=self.pc_persona, organization=self.org, value=150)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 3
        )

    def test_max_of_npc_and_org_takes_org(self):
        # No NPC standing → 1; org REVERED → 5; max == 5.
        OrganizationReputationFactory(persona=self.pc_persona, organization=self.org, value=900)
        self.assertEqual(
            mission_pool_count(role=self.role, persona=self.pc_persona, npc_persona=self.npc), 5
        )


class ArcOfferWinTests(TestCase):
    """``_arc_offer_wins`` — the deterministic 0 / 100 roll boundaries."""

    @classmethod
    def setUpTestData(cls):
        cls.role = NPCRoleFactory()
        cls.era = EraFactory(status=EraStatus.ACTIVE)
        cls.other_era = EraFactory(name="other", status=EraStatus.CONCLUDED)

    def test_percent_100_always_wins(self):
        offer = _make_offer(self.role, label="arc", era=self.era, percent_replace=100)
        self.assertTrue(_arc_offer_wins(offer, self.era.pk))

    def test_percent_0_never_wins(self):
        offer = _make_offer(self.role, label="arc0", era=self.era, percent_replace=0)
        self.assertFalse(_arc_offer_wins(offer, self.era.pk))

    def test_offer_from_other_era_never_wins(self):
        offer = _make_offer(self.role, label="old", era=self.other_era, percent_replace=100)
        self.assertFalse(_arc_offer_wins(offer, self.era.pk))

    def test_offer_with_no_era_never_wins(self):
        offer = _make_offer(self.role, label="eraless", era=None, percent_replace=100)
        self.assertFalse(_arc_offer_wins(offer, self.era.pk))


class ArcReplaceDrawTests(TestCase):
    """Arc winners draw ahead of the general pool, behind explicit chains."""

    def setUp(self):
        self.role = NPCRoleFactory()

    def test_no_active_era_is_noop(self):
        # Arc-eligible template but no ACTIVE era → drawn as plain general pool.
        upcoming = EraFactory(status=EraStatus.UPCOMING)
        _make_offer(self.role, label="arc", era=upcoming, percent_replace=100)
        for i in range(4):
            _make_offer(self.role, label=f"gen-{i}")
        drawn = _draw_pool_offers(_pool_offers(self.role), 5)
        self.assertEqual(len(drawn), 5)  # all five, no error, no special ordering

    def test_arc_winner_outranks_general_pool(self):
        era = EraFactory(status=EraStatus.ACTIVE)
        arc = _make_offer(self.role, label="arc", era=era, percent_replace=100)
        for i in range(5):
            _make_offer(self.role, label=f"gen-{i}")
        # One slot: the always-winning arc offer is promoted over the general pool.
        for _ in range(20):
            self.assertEqual(_draw_pool_offers(_pool_offers(self.role), 1), [arc])

    def test_chain_priority_outranks_arc_winner(self):
        era = EraFactory(status=EraStatus.ACTIVE)
        chain = _make_offer(self.role, label="chain", draw_priority=5)  # not arc
        _make_offer(self.role, label="arc", era=era, percent_replace=100)
        for i in range(3):
            _make_offer(self.role, label=f"gen-{i}")
        # One slot: explicit chain beats the arc winner.
        for _ in range(20):
            self.assertEqual(_draw_pool_offers(_pool_offers(self.role), 1), [chain])

    def test_arc_winner_and_chain_both_included_when_slots_allow(self):
        era = EraFactory(status=EraStatus.ACTIVE)
        chain = _make_offer(self.role, label="chain", draw_priority=5)
        arc = _make_offer(self.role, label="arc", era=era, percent_replace=100)
        for i in range(4):
            _make_offer(self.role, label=f"gen-{i}")
        # Two slots: chain (tier 1) then arc winner (tier 2), general never reached.
        for _ in range(20):
            drawn = _draw_pool_offers(_pool_offers(self.role), 2)
            self.assertEqual(set(drawn), {chain, arc})
