"""Tests for #743 — renown event notifications."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.constants import RenownMagnitude, RenownRisk
from world.societies.renown import fire_renown_award


def _make_npc_persona():
    """Persona whose sheet has no active player tenure (NPC)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_player_persona():
    """Persona whose sheet has an active roster tenure (player-owned)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return sheet.primary_persona


class NotificationGateTests(TestCase):
    def test_no_notification_for_npc_persona(self) -> None:
        persona = _make_npc_persona()
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE)
        self.assertFalse(NarrativeMessage.objects.exists())

    def test_notification_fires_for_player_owned_persona(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE)
        self.assertEqual(NarrativeMessage.objects.count(), 1)
        msg = NarrativeMessage.objects.get()
        self.assertEqual(msg.category, NarrativeCategory.RENOWN.value)
        # Delivery row keyed to the persona's sheet.
        delivery = NarrativeMessageDelivery.objects.get(message=msg)
        self.assertEqual(delivery.recipient_character_sheet_id, persona.character_sheet_id)


class NotificationBodyShapeTests(TestCase):
    def test_body_includes_title_and_deltas(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            title="Saved the village",
        )
        msg = NarrativeMessage.objects.get()
        self.assertIn("Saved the village", msg.body)
        self.assertIn("fame", msg.body)
        self.assertIn("prestige", msg.body)

    def test_body_announces_tier_transition_when_it_fires(self) -> None:
        persona = _make_player_persona()
        # Very High pushes from NORMAL straight to HOUSEHOLD_NAME → tier
        # transition fires.
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.VERY_HIGH,
            title="Heroic feat",
        )
        msg = NarrativeMessage.objects.get()
        self.assertIn("Heroic feat", msg.body)
        self.assertIn("new tier", msg.body)

    def test_body_handles_no_magnitude_no_risk_gracefully(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(persona=persona, title="Quiet recognition")
        msg = NarrativeMessage.objects.get()
        self.assertIn("Quiet recognition", msg.body)
        self.assertIn("minor renown", msg.body)


class NotificationLegendOnlyTests(TestCase):
    def test_risk_only_award_summarises_legend(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            risk=RenownRisk.MODERATE,
            title="Dangerous secret",
        )
        msg = NarrativeMessage.objects.get()
        self.assertIn("legend", msg.body)
        # No fame/prestige bits when magnitude wasn't supplied.
        self.assertNotIn("fame", msg.body)
        self.assertNotIn("prestige", msg.body)
