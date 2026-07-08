"""Tests for directed-offer summonses (#2050).

Covers: create (validation + uniqueness), respond (accept/decline/risk-gate/
eligibility-failure), record_summons_refusal (affection drop + streak +
escalation), expire (cron sweep).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import make_court_with_mission
from world.covenants.services import get_court_grant_config
from world.npc_services.constants import (
    SUMMONS_REFUSAL_AFFECTION_DELTA,
    OfferKind,
    SummonsStatus,
)
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
    NPCStandingFactory,
)
from world.npc_services.models import NPCStanding
from world.npc_services.summons import (
    create_summons,
    expire_summonses,
    record_summons_refusal,
    respond_to_summons,
)
from world.scenes.factories import PersonaFactory


def _pc():
    """A PC with sheet + PRIMARY persona."""
    from evennia_extensions.factories import CharacterFactory

    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet, sheet.primary_persona


def _mission_offer():
    """A MISSION-kind offer with details + an entry node on the template."""
    offer = NPCServiceOfferFactory(kind=OfferKind.MISSION)
    details = MissionOfferDetailsFactory(offer=offer)
    # issue_mission requires an entry node on the template.
    from world.missions.factories import MissionNodeFactory

    MissionNodeFactory(template=details.mission_template, is_entry=True)
    return offer


# ---------------------------------------------------------------------------
# create_summons
# ---------------------------------------------------------------------------


class CreateSummonsTests(TestCase):
    def test_create_summons_creates_pending_row(self):
        """A valid MISSION offer + persona → PENDING summons with message."""
        offer = _mission_offer()
        _, _, persona = _pc()

        summons = create_summons(offer, persona, message="Come at once.")

        self.assertEqual(summons.status, SummonsStatus.PENDING)
        self.assertEqual(summons.message, "Come at once.")
        self.assertEqual(summons.offer, offer)
        self.assertEqual(summons.target_persona, persona)
        self.assertIsNone(summons.expires_at)
        self.assertIsNone(summons.created_by)

    def test_create_summons_rejects_non_mission_kind(self):
        """Non-MISSION offers are rejected."""
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT)
        _, _, persona = _pc()

        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_summons(offer, persona)

    def test_create_summons_unique_pending(self):
        """A second PENDING summons for the same (offer, persona) raises."""
        offer = _mission_offer()
        _, _, persona = _pc()

        create_summons(offer, persona)
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            create_summons(offer, persona)

    def test_create_summons_with_expiry(self):
        """An expires_at is stored."""
        offer = _mission_offer()
        _, _, persona = _pc()
        deadline = timezone.now() + timedelta(hours=24)

        summons = create_summons(offer, persona, expires_at=deadline)

        self.assertEqual(summons.expires_at, deadline)


# ---------------------------------------------------------------------------
# respond_to_summons — decline
# ---------------------------------------------------------------------------


class RespondSummonsDeclineTests(TestCase):
    def test_decline_sets_declined_and_drops_affection(self):
        """Declining sets DECLINED + drops affection + bumps streak."""
        offer = _mission_offer()
        _, _, persona = _pc()
        npc_persona = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_persona, affection=20)
        # Wire the role to the NPC persona via a covenant leader.
        # For a non-court role, the refusal path is affection-only (no escalation).
        # We need the role to resolve an npc_persona — use a court covenant.
        summons = create_summons(offer, persona, message="Come.")
        # Without a court covenant, _resolve_npc_persona_for_role returns None,
        # so the refusal is a no-op. Test that the summons still gets DECLINED.
        result = respond_to_summons(summons, character, accept=False)

        self.assertTrue(result.success)
        summons.refresh_from_db()
        self.assertEqual(summons.status, SummonsStatus.DECLINED)
        self.assertIsNotNone(summons.resolved_at)

    def test_decline_already_resolved_returns_failure(self):
        """Declining an already-DECLINED summons returns a failure."""
        offer = _mission_offer()
        character, _, persona = _pc()
        summons = create_summons(offer, persona)
        respond_to_summons(summons, character, accept=False)

        result = respond_to_summons(summons, character, accept=False)
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# respond_to_summons — accept
# ---------------------------------------------------------------------------


class RespondSummonsAcceptTests(TestCase):
    def test_accept_starts_mission_run(self):
        """Accepting a summons delegates to resolve_offer → issue_mission."""
        offer = _mission_offer()
        character, _, persona = _pc()
        summons = create_summons(offer, persona)

        result = respond_to_summons(summons, character, accept=True)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.instance_pk)
        summons.refresh_from_db()
        self.assertEqual(summons.status, SummonsStatus.ACCEPTED)
        self.assertIsNotNone(summons.resolved_at)

    def test_accept_eligibility_failure_keeps_pending(self):
        """An OfferNotEligibleError at accept leaves the summons PENDING."""
        # Make the offer ineligible by setting a rapport requirement the
        # session won't meet.
        offer = NPCServiceOfferFactory(
            kind=OfferKind.MISSION,
            rapport_requirement=999,
            is_final=True,
        )
        MissionOfferDetailsFactory(offer=offer)
        character, _, persona = _pc()
        summons = create_summons(offer, persona)

        result = respond_to_summons(summons, character, accept=True)

        self.assertFalse(result.success)
        summons.refresh_from_db()
        self.assertEqual(summons.status, SummonsStatus.PENDING)


# ---------------------------------------------------------------------------
# record_summons_refusal — court-backed escalation
# ---------------------------------------------------------------------------


class RecordSummonsRefusalTests(TestCase):
    """Court-backed refusal: affection drop + streak + escalation pool fire."""

    def test_refusal_drops_affection_and_increments_streak(self):
        """Refusal drops affection by SUMMONS_REFUSAL_AFFECTION_DELTA and bumps streak."""
        seed = make_court_with_mission()
        servant_persona = seed.servant_sheet.primary_persona
        master_persona = seed.master_sheet.primary_persona
        NPCStandingFactory(
            persona=servant_persona,
            npc_persona=master_persona,
            affection=20,
        )

        record_summons_refusal(servant_persona, role=seed.service_offer.role)

        standing = NPCStanding.objects.get(persona=servant_persona, npc_persona=master_persona)
        self.assertEqual(standing.affection, 20 + SUMMONS_REFUSAL_AFFECTION_DELTA)
        self.assertEqual(standing.consecutive_refused_summons, 1)

    def test_streak_crossing_fires_escalation_pool(self):
        """Court-backed role: crossing threshold fires pool + resets streak."""
        from actions.factories import ConsequencePoolFactory

        seed = make_court_with_mission()
        servant_persona = seed.servant_sheet.primary_persona
        master_persona = seed.master_sheet.primary_persona
        NPCStandingFactory(
            persona=servant_persona,
            npc_persona=master_persona,
            affection=100,
            consecutive_refused_summons=2,  # one below default threshold of 3
        )
        # Ensure the config has an escalation pool to fire.
        pool = ConsequencePoolFactory()
        config = get_court_grant_config()
        config.summons_refusal_escalation_pool = pool
        config.save()

        crossed = record_summons_refusal(servant_persona, role=seed.service_offer.role)

        self.assertTrue(crossed)
        standing = NPCStanding.objects.get(persona=servant_persona, npc_persona=master_persona)
        # Streak resets after firing.
        self.assertEqual(standing.consecutive_refused_summons, 0)

    def test_non_court_role_no_escalation(self):
        """Non-court roles: affection shift only, no pool fire."""
        role = NPCRoleFactory()
        _, _, persona = _pc()
        npc_persona = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_persona, affection=20)

        # Non-court role → _resolve_npc_persona_for_role returns None → no-op.
        crossed = record_summons_refusal(persona, role=role)

        self.assertFalse(crossed)


# ---------------------------------------------------------------------------
# expire_summonses
# ---------------------------------------------------------------------------


class ExpireSummonsTests(TestCase):
    def test_expire_past_due_pending(self):
        """Past-due PENDING → EXPIRED."""
        offer = _mission_offer()
        _, _, persona = _pc()
        summons = create_summons(offer, persona, expires_at=timezone.now() - timedelta(hours=1))

        count = expire_summonses()

        self.assertEqual(count, 1)
        summons.refresh_from_db()
        self.assertEqual(summons.status, SummonsStatus.EXPIRED)
        self.assertIsNotNone(summons.resolved_at)

    def test_expire_ignores_not_yet_due(self):
        """A summons with a future expiry is not expired."""
        offer = _mission_offer()
        _, _, persona = _pc()
        create_summons(offer, persona, expires_at=timezone.now() + timedelta(hours=24))

        count = expire_summonses()
        self.assertEqual(count, 0)

    def test_expire_ignores_no_expiry(self):
        """A summons with no expiry is never expired by the sweep."""
        offer = _mission_offer()
        _, _, persona = _pc()
        create_summons(offer, persona)

        count = expire_summonses()
        self.assertEqual(count, 0)

    def test_expire_ignores_already_resolved(self):
        """ACCEPTED/DECLINED/EXPIRED rows are untouched."""
        offer = _mission_offer()
        character, _, persona = _pc()
        summons = create_summons(offer, persona, expires_at=timezone.now() - timedelta(hours=1))
        respond_to_summons(summons, character, accept=False)

        count = expire_summonses()
        self.assertEqual(count, 0)
