"""Tests for the interaction state machine.

Covers: start_interaction (starting rapport seeding), available_offers
(eligibility predicate + rapport gate filtering), resolve_offer (effect
dispatch + rapport delta + final-action close), end_interaction
(persistence of new affection on close).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    NPCStandingFactory,
    PermitOfferDetailsFactory,
)
from world.npc_services.models import NPCStanding
from world.npc_services.services import (
    available_offers,
    end_interaction,
    resolve_offer,
    start_interaction,
)
from world.scenes.factories import PersonaFactory


def _pc():
    """A PC with sheet + PRIMARY persona, ready for predicate context."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


class StartInteractionTests(TestCase):
    """Rapport seeding from role default + existing NPCStanding affection."""

    def test_class_1_starts_at_role_default(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory(default_rapport_starting_value=3)
        session = start_interaction(role=role, persona=persona, character=character)
        # No NPC persona = class-1; no affection to add.
        self.assertEqual(session.current_rapport, 3)
        self.assertIsNone(session.npc_persona)

    def test_class_2_seeds_with_existing_affection(self) -> None:
        character, persona = _pc()
        npc_persona = PersonaFactory()
        role = NPCRoleFactory(default_rapport_starting_value=2)
        NPCStandingFactory(persona=persona, npc_persona=npc_persona, affection=5)
        session = start_interaction(
            role=role, persona=persona, character=character, npc_persona=npc_persona
        )
        self.assertEqual(session.current_rapport, 7)  # 2 + 5

    def test_class_2_no_existing_standing_starts_at_role_default(self) -> None:
        character, persona = _pc()
        npc_persona = PersonaFactory()
        role = NPCRoleFactory(default_rapport_starting_value=2)
        session = start_interaction(
            role=role, persona=persona, character=character, npc_persona=npc_persona
        )
        self.assertEqual(session.current_rapport, 2)


class AvailableOffersTests(TestCase):
    """Eligibility predicate + rapport gate + draw mode filtering."""

    def test_eligibility_predicate_filters_offers(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory()
        eligible = NPCServiceOfferFactory(role=role, label="eligible", eligibility_rule={})
        # Gate on a distinction the PC doesn't have — predicate evaluates False.
        gated = NPCServiceOfferFactory(
            role=role,
            label="gated",
            eligibility_rule={"leaf": "has_distinction", "params": {"slug": "knight"}},
        )
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertIn(eligible, listed)
        self.assertNotIn(gated, listed)

    def test_rapport_requirement_filters_offers(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory(default_rapport_starting_value=0)
        low = NPCServiceOfferFactory(role=role, label="low", rapport_requirement=0)
        high = NPCServiceOfferFactory(role=role, label="high", rapport_requirement=5)
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertIn(low, listed)
        self.assertNotIn(high, listed)

    def test_pool_offers_included_when_pool_count_is_none(self) -> None:
        # #686: POOL offers are now first-class. Without pool_count, every
        # eligible offer is returned regardless of draw_mode (the legacy
        # "skip POOL silently" behaviour was wrong — callers that want
        # sampling pass pool_count, callers that want everything don't).
        character, persona = _pc()
        role = NPCRoleFactory()
        menu_offer = NPCServiceOfferFactory(role=role, label="menu", draw_mode=DrawMode.MENU)
        pool_offer = NPCServiceOfferFactory(role=role, label="pool", draw_mode=DrawMode.POOL)
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertIn(menu_offer, listed)
        self.assertIn(pool_offer, listed)

    def test_pool_offers_sampled_when_pool_count_is_set(self) -> None:
        # #686: pool_count caps POOL-mode offers via weighted draw without
        # replacement. MENU offers always come back in full.
        character, persona = _pc()
        role = NPCRoleFactory()
        menu_offer = NPCServiceOfferFactory(role=role, label="menu", draw_mode=DrawMode.MENU)
        # Author 4 POOL offers; cap to 2.
        pool_offers = [
            NPCServiceOfferFactory(role=role, label=f"pool-{i}", draw_mode=DrawMode.POOL)
            for i in range(4)
        ]
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session, pool_count=2)
        self.assertIn(menu_offer, listed)
        listed_pool = [o for o in listed if o.draw_mode == DrawMode.POOL]
        self.assertEqual(len(listed_pool), 2)
        for sampled in listed_pool:
            self.assertIn(sampled, pool_offers)

    def test_closed_session_returns_no_offers(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory()
        NPCServiceOfferFactory(role=role)
        session = start_interaction(role=role, persona=persona, character=character)
        end_interaction(session)
        self.assertEqual(available_offers(session), [])


def _seed_permit_prereqs():
    """Seed the BuildingPermit template + return a default BuildingKind.

    The PERMIT effect handler (issue_permit, registered by buildings)
    requires both to be present. Tests that exercise resolve_offer on a
    PERMIT-kind offer call this and pass the returned kind to the
    PermitOfferDetailsFactory.
    """
    from world.buildings.factories import BuildingKindFactory
    from world.buildings.seeds import ensure_building_permit_template

    ensure_building_permit_template()
    return BuildingKindFactory(name="test-kind")


class ResolveOfferTests(TestCase):
    """Final-action close + non-final rapport adjustment + cross-session safety."""

    def test_final_action_dispatches_effect_and_closes(self) -> None:
        kind = _seed_permit_prereqs()
        character, persona = _pc()
        role = NPCRoleFactory()
        offer = NPCServiceOfferFactory(role=role, label="permit", is_final=True)
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        session = start_interaction(role=role, persona=persona, character=character)
        result = resolve_offer(session, offer)
        self.assertEqual(result.kind, OfferKind.PERMIT)
        self.assertTrue(session.closed)
        self.assertEqual(len(session.results), 1)

    def test_non_final_action_adjusts_rapport_keeps_session_open(self) -> None:
        kind = _seed_permit_prereqs()
        character, persona = _pc()
        role = NPCRoleFactory(default_rapport_starting_value=0)
        offer = NPCServiceOfferFactory(
            role=role,
            label="flatter",
            is_final=False,
            rapport_delta_success=3,
        )
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        session = start_interaction(role=role, persona=persona, character=character)
        resolve_offer(session, offer)
        self.assertFalse(session.closed)
        self.assertEqual(session.current_rapport, 3)

    def test_ineligible_offer_raises(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory()
        # Eligible at construction, then mutate predicate so it's no longer eligible.
        offer = NPCServiceOfferFactory(
            role=role,
            label="gated",
            eligibility_rule={"leaf": "has_distinction", "params": {"slug": "unobtainable"}},
        )
        PermitOfferDetailsFactory(offer=offer)
        session = start_interaction(role=role, persona=persona, character=character)
        with self.assertRaises(ValueError):
            resolve_offer(session, offer)

    def test_offer_from_other_role_raises(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory()
        other_role = NPCRoleFactory()
        wrong_offer = NPCServiceOfferFactory(role=other_role, label="elsewhere")
        PermitOfferDetailsFactory(offer=wrong_offer)
        session = start_interaction(role=role, persona=persona, character=character)
        with self.assertRaises(ValueError):
            resolve_offer(session, wrong_offer)


class EndInteractionPersistsAffectionTests(TestCase):
    """Class 2-4 close persists new affection; class-1 is a no-op."""

    def test_class_2_persists_new_affection(self) -> None:
        kind = _seed_permit_prereqs()
        character, persona = _pc()
        npc_persona = PersonaFactory()
        role = NPCRoleFactory(default_rapport_starting_value=0)
        offer = NPCServiceOfferFactory(
            role=role,
            label="flatter",
            is_final=False,
            rapport_delta_success=4,
        )
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        session = start_interaction(
            role=role, persona=persona, character=character, npc_persona=npc_persona
        )
        resolve_offer(session, offer)
        end_interaction(session)
        standing = NPCStanding.objects.get(persona=persona, npc_persona=npc_persona)
        self.assertEqual(standing.affection, 4)

    def test_class_1_no_persistence(self) -> None:
        kind = _seed_permit_prereqs()
        character, persona = _pc()
        role = NPCRoleFactory()
        offer = NPCServiceOfferFactory(
            role=role, label="flatter", is_final=False, rapport_delta_success=4
        )
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        session = start_interaction(role=role, persona=persona, character=character)
        resolve_offer(session, offer)
        end_interaction(session)
        # No persona → no row.
        self.assertEqual(NPCStanding.objects.count(), 0)

    def test_close_is_idempotent(self) -> None:
        character, persona = _pc()
        role = NPCRoleFactory()
        session = start_interaction(role=role, persona=persona, character=character)
        end_interaction(session)
        end_interaction(session)  # second call is a no-op
        self.assertTrue(session.closed)
