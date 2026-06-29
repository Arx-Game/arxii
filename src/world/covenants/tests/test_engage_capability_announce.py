"""Tests for capability-gain/loss announcements on covenant role engage/disengage.

Engaging a covenant role that grants a capability via a tier-0 CAPABILITY_GRANT
ThreadPullEffect must send ONE NarrativeCategory.ABILITY message to the character,
naming the gained capability. Disengaging must send the lost message.

See issue #1606.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.services import (
    clear_engaged_for_type,
    clear_engaged_membership,
    set_engaged_membership,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery


class EngageCapabilityAnnounceTests(TestCase):
    """set_engaged_membership sends an ABILITY message when a capability is gained."""

    def _make_covenant_role_thread(self, *, sheet, role, resonance, level=10):
        return ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=role,
            level=level,
        )

    def _make_tier0_capability_effect(self, *, resonance, capability):
        return ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=capability,
        )

    def test_engage_sends_ability_message_naming_gained_capability(self):
        """Engaging a role with a CAPABILITY_GRANT sends one ABILITY message."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=False,
            left_at=None,
        )

        set_engaged_membership(membership=membership)

        msgs = NarrativeMessage.objects.filter(category=NarrativeCategory.ABILITY)
        self.assertEqual(msgs.count(), 1)
        msg = msgs.first()
        self.assertIn(cap.name, msg.body)
        # Delivered to this character sheet
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                message=msg, recipient_character_sheet=sheet
            ).exists()
        )

    def test_disengage_sends_ability_message_naming_lost_capability(self):
        """Disengaging a role with a CAPABILITY_GRANT sends one ABILITY message (lost)."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            left_at=None,
        )

        clear_engaged_membership(membership=membership)

        msgs = NarrativeMessage.objects.filter(category=NarrativeCategory.ABILITY)
        self.assertEqual(msgs.count(), 1)
        msg = msgs.first()
        self.assertIn(cap.name, msg.body)
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                message=msg, recipient_character_sheet=sheet
            ).exists()
        )

    def test_engage_no_message_when_no_capability_grant(self):
        """Engaging a role with no CAPABILITY_GRANT effect sends no ABILITY message."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()

        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=False,
            left_at=None,
        )

        set_engaged_membership(membership=membership)

        self.assertFalse(
            NarrativeMessage.objects.filter(category=NarrativeCategory.ABILITY).exists()
        )

    def test_clear_engaged_for_type_sends_lost_message(self):
        """clear_engaged_for_type sends an ABILITY message for each disengaged capability."""
        from world.covenants.constants import CovenantType

        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()

        self._make_covenant_role_thread(sheet=sheet, role=role, resonance=resonance)
        self._make_tier0_capability_effect(resonance=resonance, capability=cap)

        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
            engaged=True,
            left_at=None,
        )

        clear_engaged_for_type(character_sheet=sheet, covenant_type=CovenantType.DURANCE)

        msgs = NarrativeMessage.objects.filter(category=NarrativeCategory.ABILITY)
        self.assertEqual(msgs.count(), 1)
        msg = msgs.first()
        self.assertIn(cap.name, msg.body)
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                message=msg, recipient_character_sheet=sheet
            ).exists()
        )
