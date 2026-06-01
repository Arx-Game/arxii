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
        # Plan 3 replaced the stub with the real issue_permit handler from
        # world.buildings.services. The dispatch contract is the same
        # (returns EffectResult); the body now creates a real BuildingPermit
        # ItemInstance + BuildingPermitDetails row. We seed the prereqs
        # (template + BuildingKind) and verify the dispatch still works.
        from world.buildings.factories import BuildingKindFactory
        from world.buildings.seeds import ensure_building_permit_template

        ensure_building_permit_template()
        kind = BuildingKindFactory(name="effect-test-kind")
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT, label="permit-offer-1")
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory

        character = CharacterFactory()
        persona = CharacterSheetFactory(character=character).primary_persona
        result = dispatch_offer_effect(offer, persona)
        self.assertIsInstance(result, EffectResult)
        self.assertEqual(result.kind, OfferKind.PERMIT)
        self.assertEqual(result.payload["holder_persona_pk"], persona.pk)
        self.assertIn("permit_pk", result.payload)

    def test_dispatch_unregistered_kind_raises(self) -> None:
        # Bypass the OfferKind enum validation to construct a truly unwired
        # kind. Saves to bypass validation — we're verifying the dispatcher
        # fails loudly rather than silently no-op'ing.
        offer = NPCServiceOfferFactory(kind=OfferKind.PERMIT, label="bogus")
        offer.kind = "unregistered_kind"  # not a real OfferKind value
        persona = PersonaFactory()
        with self.assertRaises(UnregisteredOfferKindError):
            dispatch_offer_effect(offer, persona)
