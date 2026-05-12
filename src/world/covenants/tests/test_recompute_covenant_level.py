"""Tests for recompute_covenant_level service."""

from django.test import TestCase

from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantLevelThresholdFactory,
    CovenantRoleFactory,
)
from world.covenants.services import recompute_covenant_level
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    CovenantLegendCreditFactory,
    LegendEntryFactory,
    LegendSourceTypeFactory,
)
from world.societies.models import refresh_legend_views
from world.societies.services import create_legend_event


class RecomputeCovenantLevelTests(TestCase):
    """Behavioural tests for recompute_covenant_level.

    Isolation tests (test_level_rises_*, test_idempotent_*, test_fires_*,
    test_no_message_*) build legend totals via factories + raw
    CovenantLegendCredit rows so the service is tested in isolation from
    the mutation-path wiring.

    End-to-end test (test_recompute_via_mutation_path) verifies that
    create_legend_event drives the recompute automatically.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        CovenantLevelThresholdFactory(level=1, required_legend=0)
        CovenantLevelThresholdFactory(level=2, required_legend=100)
        CovenantLevelThresholdFactory(level=3, required_legend=300)
        cls.source_type = LegendSourceTypeFactory()

    def _make_engaged_member(self, covenant: object) -> object:
        """Create a persona whose character sheet is actively engaged with covenant.

        Returns the CharacterCovenantRole membership row.
        """
        persona = PersonaFactory()
        sheet = persona.character_sheet
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
            engaged=False,
        )
        membership.engaged = True
        membership.save()
        sheet.character.covenant_roles.invalidate()
        return membership

    def _seed_legend_for_covenant(self, covenant: object, total: int) -> None:
        """Seed a LegendEntry + CovenantLegendCredit and refresh materialized views.

        Uses factories directly so we bypass the mutation-service wiring and
        can test recompute_covenant_level in isolation.
        """
        persona = PersonaFactory()
        entry = LegendEntryFactory(persona=persona, base_value=total)
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        refresh_legend_views()

    def test_level_rises_when_threshold_crossed(self) -> None:
        """Legend total >= 100 → recompute_covenant_level returns 2 and saves it."""
        covenant = CovenantFactory(level=1)
        self._seed_legend_for_covenant(covenant, 150)

        result = recompute_covenant_level(covenant=covenant)

        covenant.refresh_from_db()
        self.assertEqual(result, 2)
        self.assertEqual(covenant.level, 2)

    def test_idempotent_when_total_unchanged(self) -> None:
        """Calling recompute a second time with no new legend returns None, no new message."""
        covenant = CovenantFactory(level=1)
        self._seed_legend_for_covenant(covenant, 150)

        # First call: level rises to 2 and fires a message
        recompute_covenant_level(covenant=covenant)
        msg_count_after_first = NarrativeMessage.objects.filter(
            category=NarrativeCategory.COVENANT
        ).count()

        # Second call: same total, same level → idempotent
        result = recompute_covenant_level(covenant=covenant)

        self.assertIsNone(result)
        self.assertEqual(
            NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT).count(),
            msg_count_after_first,
        )

    def test_fires_narrative_message_per_engaged_member(self) -> None:
        """Level rise emits exactly ONE NarrativeMessage with 3 deliveries (3 engaged members)."""
        covenant = CovenantFactory(level=1)
        memberships = [self._make_engaged_member(covenant) for _ in range(3)]
        # Seed legend via factories — bypass mutation path to isolate the service
        persona = memberships[0].character_sheet.personas.first()
        entry = LegendEntryFactory(persona=persona, base_value=150)
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        refresh_legend_views()

        msg_before = NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT).count()
        recompute_covenant_level(covenant=covenant)

        msgs = NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT)
        self.assertEqual(msgs.count(), msg_before + 1)

        msg = msgs.order_by("-sent_at").first()
        self.assertEqual(msg.category, NarrativeCategory.COVENANT)
        self.assertIn(covenant.name, msg.body)
        self.assertIn("2", msg.body)

        delivery_count = NarrativeMessageDelivery.objects.filter(message=msg).count()
        self.assertEqual(delivery_count, 3)

    def test_no_message_when_level_unchanged(self) -> None:
        """Covenant at level 1 with legend=0 → recompute returns None, no message fired."""
        covenant = CovenantFactory(level=1)

        result = recompute_covenant_level(covenant=covenant)

        self.assertIsNone(result)
        self.assertEqual(
            NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT).count(), 0
        )

    def test_level_3_when_total_exceeds_300(self) -> None:
        """Legend total >= 300 → covenant jumps straight to level 3."""
        covenant = CovenantFactory(level=1)
        self._seed_legend_for_covenant(covenant, 350)

        result = recompute_covenant_level(covenant=covenant)

        covenant.refresh_from_db()
        self.assertEqual(result, 3)
        self.assertEqual(covenant.level, 3)

    def test_recompute_via_mutation_path(self) -> None:
        """End-to-end: create_legend_event auto-wires recompute after view refresh."""
        covenant = CovenantFactory(level=1)
        membership = self._make_engaged_member(covenant)
        persona = membership.character_sheet.personas.first()

        create_legend_event(
            title="A Great Event",
            source_type=self.source_type,
            base_value=150,
            personas=[persona],
        )

        covenant.refresh_from_db()
        self.assertEqual(covenant.level, 2)
        self.assertEqual(
            NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT).count(), 1
        )
