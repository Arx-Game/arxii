"""Tests for #743 — renown event notifications."""

from __future__ import annotations

from unittest.mock import patch

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
        # Moderate at fame 0 → TALKED_ABOUT (one tier change). Expect 2:
        # the deed + the tier transition (per spec, separate lines).
        self.assertEqual(NarrativeMessage.objects.count(), 2)
        msgs = list(NarrativeMessage.objects.order_by("pk"))
        for msg in msgs:
            self.assertEqual(msg.category, NarrativeCategory.RENOWN.value)
        delivery = NarrativeMessageDelivery.objects.filter(message=msgs[0]).get()
        self.assertEqual(delivery.recipient_character_sheet_id, persona.character_sheet_id)


class NotificationBodyShapeTests(TestCase):
    def test_body_uses_qualitative_magnitude_descriptor(self) -> None:
        """Per spec: natural-language framing, no raw deltas in the chat line."""
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            title="Saved the village",
        )
        # First message is the deed (tier transition is the second).
        deed_msg = NarrativeMessage.objects.order_by("pk").first()
        self.assertIn("Saved the village", deed_msg.body)
        self.assertIn("significant renown", deed_msg.body)
        # Raw point values must NOT leak into the chat line (#676
        # "hidden mechanics stay tribal").
        self.assertNotIn("+", deed_msg.body)

    def test_risk_only_event_says_survives(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            risk=RenownRisk.HIGH,
            title="Dangerous secret",
        )
        deed_msg = NarrativeMessage.objects.order_by("pk").first()
        self.assertIn("Dangerous secret", deed_msg.body)
        self.assertIn("survives grave risk", deed_msg.body)
        self.assertNotIn("earns", deed_msg.body)

    def test_magnitude_plus_risk_combines(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.MODERATE,
            risk=RenownRisk.MODERATE,
            title="Bold gambit",
        )
        deed_msg = NarrativeMessage.objects.order_by("pk").first()
        self.assertIn("moderate renown", deed_msg.body)
        self.assertIn("real risk", deed_msg.body)

    def test_bare_event_falls_back_to_quiet_recognition(self) -> None:
        persona = _make_player_persona()
        fire_renown_award(persona=persona, title="Quiet recognition")
        deed_msg = NarrativeMessage.objects.order_by("pk").first()
        self.assertIn("Quiet recognition", deed_msg.body)
        self.assertIn("quietly recognised", deed_msg.body)

    def test_deed_body_has_no_details_placeholder(self) -> None:
        """The inbox '(details)' stub was dropped — the Renown tab is the
        home for per-axis detail, so the chat line carries no expander hook.
        """
        persona = _make_player_persona()
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE, title="A deed")
        deed_msg = NarrativeMessage.objects.order_by("pk").first()
        self.assertNotIn("(details)", deed_msg.body)


class TierTransitionTests(TestCase):
    def test_tier_transition_fires_a_separate_message(self) -> None:
        """Per spec: 'Fame tier transitions get their own chat line.'"""
        persona = _make_player_persona()
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.VERY_HIGH,
            title="Heroic feat",
        )
        # Two messages: the deed, plus the tier announcement.
        self.assertEqual(NarrativeMessage.objects.count(), 2)
        bodies = list(NarrativeMessage.objects.order_by("pk").values_list("body", flat=True))
        deed_msg, tier_msg = bodies
        self.assertIn("Heroic feat", deed_msg)
        self.assertIn("You've become", tier_msg)
        # New tier named explicitly (Very High → HOUSEHOLD_NAME).
        self.assertIn("Household Name", tier_msg)


class NotificationFailureModeTests(TestCase):
    def test_deed_persists_when_notification_raises(self) -> None:
        """Notification failure must not roll back the renown award."""
        persona = _make_player_persona()
        with patch(
            "world.societies.notifications.send_narrative_message",
            side_effect=RuntimeError("simulated push failure"),
        ):
            result = fire_renown_award(
                persona=persona,
                magnitude=RenownMagnitude.MODERATE,
                title="Survives notification crash",
            )

        persona.refresh_from_db()
        self.assertGreater(persona.fame_points, 0)
        self.assertGreater(persona.prestige_from_deeds, 0)
        self.assertEqual(result.fame_awarded, 150)  # MODERATE
        # And no notification rows were created (each send_narrative_message
        # call raised; the renown side committed first regardless).
        self.assertFalse(NarrativeMessage.objects.exists())
