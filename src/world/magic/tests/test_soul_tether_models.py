"""Soul Tether model tests (Spec B §15)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import CharacterResonanceFactory, ThreadFactory


class ThreadHollowFieldTests(TestCase):
    def test_hollow_current_default_zero(self) -> None:
        thread = ThreadFactory()
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 0)

    def test_hollow_current_persists(self) -> None:
        thread = ThreadFactory()
        thread.hollow_current = 12
        thread.save(update_fields=["hollow_current"])
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 12)


class CharacterResonanceLifetimeHelpedTests(TestCase):
    def test_lifetime_helped_default_zero(self) -> None:
        cr = CharacterResonanceFactory()
        cr.refresh_from_db()
        self.assertEqual(cr.lifetime_helped, 0)

    def test_lifetime_helped_persists_and_is_monotonic_in_practice(self) -> None:
        cr = CharacterResonanceFactory()
        cr.lifetime_helped = 50
        cr.save(update_fields=["lifetime_helped"])
        cr.refresh_from_db()
        self.assertEqual(cr.lifetime_helped, 50)


class SineatingModelTests(TestCase):
    def test_sineating_can_be_created_with_required_fields(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Sineating
        from world.relationships.factories import CharacterRelationshipFactory

        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sinner, target=sineater)
        resonance = ResonanceFactory()

        row = Sineating.objects.create(
            sinner_sheet=sinner,
            sineater_sheet=sineater,
            relationship=relationship,
            resonance=resonance,
            units_offered=10,
            units_accepted=7,
            anima_cost=14,
            fatigue_cost=7,
        )
        self.assertEqual(row.units_offered, 10)
        self.assertEqual(row.units_accepted, 7)
