"""Tests for the per-kind offer effect handler registry."""

from django.test import TestCase

from world.npc_services.constants import OfferKind
from world.npc_services.effects import (
    OFFER_EFFECT_HANDLERS,
    EffectResult,
    UnregisteredOfferKindError,
    dispatch_offer_effect,
)
from world.npc_services.factories import (
    NPCServiceOfferFactory,
    PermitOfferDetailsFactory,
)
from world.scenes.factories import PersonaFactory


class EffectHandlerRegistryTests(TestCase):
    """The registry routes offer kind → handler and surfaces missing handlers."""

    def test_permit_handler_registered(self) -> None:
        # Plan 2 ships PERMIT only — the dispatch wiring is the deliverable.
        self.assertIn(OfferKind.PERMIT.value, OFFER_EFFECT_HANDLERS)

    def test_dispatch_permit_returns_structured_result(self) -> None:
        # Stub handler — Plan 3 replaces the body. Plan 2 verifies dispatch end-to-end.
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT, label="permit-offer-1")
        PermitOfferDetailsFactory(offer=offer)
        persona = PersonaFactory()
        result = dispatch_offer_effect(offer, persona)
        self.assertIsInstance(result, EffectResult)
        self.assertEqual(result.kind, OfferKind.PERMIT)
        self.assertEqual(result.object_label, "permit-offer-1")
        self.assertEqual(result.payload["holder_persona_pk"], persona.pk)
        self.assertEqual(result.payload["offer_pk"], offer.pk)

    def test_dispatch_unregistered_kind_raises(self) -> None:
        # Bypass the OfferKind enum validation to construct a truly unwired
        # kind. Saves to bypass validation — we're verifying the dispatcher
        # fails loudly rather than silently no-op'ing.
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT, label="bogus")
        offer.kind = "unregistered_kind"  # not a real OfferKind value
        persona = PersonaFactory()
        with self.assertRaises(UnregisteredOfferKindError):
            dispatch_offer_effect(offer, persona)
