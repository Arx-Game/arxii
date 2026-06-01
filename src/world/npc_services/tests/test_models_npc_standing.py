"""Tests for the unified NPCStanding + OfferCooldown models.

NPCStanding is per-(PC persona, NPC persona) — affection / interaction
summary only. OfferCooldown is per-(offer, persona) — throttles offer
re-selection after a final-action grant. The two are deliberately
orthogonal so cooldown works for every offer kind, not just NPC-rooted
ones.
"""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.npc_services.factories import (
    NPCServiceOfferFactory,
    NPCStandingFactory,
    OfferCooldownFactory,
)
from world.npc_services.models import NPCStanding, OfferCooldown
from world.scenes.factories import PersonaFactory


class NPCStandingModelTests(TestCase):
    """(persona, npc_persona) unique; affection only."""

    def test_create_standing(self) -> None:
        persona = PersonaFactory()
        npc_persona = PersonaFactory()
        standing = NPCStandingFactory(persona=persona, npc_persona=npc_persona)
        self.assertEqual(standing.persona, persona)
        self.assertEqual(standing.npc_persona, npc_persona)

    def test_affection_defaults_to_zero(self) -> None:
        standing = NPCStandingFactory()
        self.assertEqual(standing.affection, 0)

    def test_affection_round_trips(self) -> None:
        standing = NPCStandingFactory(affection=42)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, 42)

    def test_affection_accepts_negative(self) -> None:
        standing = NPCStandingFactory(affection=-5)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, -5)

    def test_persona_npc_persona_uniqueness(self) -> None:
        persona = PersonaFactory()
        npc_persona = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_persona)
        with self.assertRaises(IntegrityError):
            NPCStanding.objects.create(persona=persona, npc_persona=npc_persona)

    def test_same_persona_different_npc_allowed(self) -> None:
        persona = PersonaFactory()
        npc_a = PersonaFactory()
        npc_b = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_a)
        NPCStandingFactory(persona=persona, npc_persona=npc_b)
        self.assertEqual(NPCStanding.objects.filter(persona=persona).count(), 2)

    def test_last_changed_at_auto_updates(self) -> None:
        standing = NPCStandingFactory(affection=0)
        first_ts = standing.last_changed_at
        standing.affection = 5
        standing.save()
        standing.refresh_from_db()
        self.assertGreater(standing.last_changed_at, first_ts)


class OfferCooldownModelTests(TestCase):
    """(offer, persona) unique; available_at gates re-selection."""

    def test_create_cooldown(self) -> None:
        offer = NPCServiceOfferFactory()
        persona = PersonaFactory()
        future = timezone.now() + timedelta(hours=4)
        cooldown = OfferCooldownFactory(offer=offer, persona=persona, available_at=future)
        self.assertEqual(cooldown.offer, offer)
        self.assertEqual(cooldown.persona, persona)
        self.assertGreater(cooldown.available_at, timezone.now())

    def test_offer_persona_uniqueness(self) -> None:
        offer = NPCServiceOfferFactory()
        persona = PersonaFactory()
        OfferCooldownFactory(offer=offer, persona=persona)
        with self.assertRaises(IntegrityError):
            OfferCooldown.objects.create(
                offer=offer,
                persona=persona,
                available_at=timezone.now() + timedelta(hours=1),
            )

    def test_same_persona_different_offers_allowed(self) -> None:
        persona = PersonaFactory()
        offer_a = NPCServiceOfferFactory(label="offer-a")
        offer_b = NPCServiceOfferFactory(label="offer-b")
        OfferCooldownFactory(offer=offer_a, persona=persona)
        OfferCooldownFactory(offer=offer_b, persona=persona)
        self.assertEqual(OfferCooldown.objects.filter(persona=persona).count(), 2)
