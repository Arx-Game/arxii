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


class CorruptionResistanceEffectKindTests(TestCase):
    def test_corruption_resistance_is_a_valid_effect_kind(self) -> None:
        from world.magic.constants import EffectKind

        self.assertIn("CORRUPTION_RESISTANCE", EffectKind.values)


class SoulTetherExceptionTests(TestCase):
    def test_user_message_round_trip(self) -> None:
        from world.magic.exceptions import AffinityGateError

        expected_msg = "Sinner cannot be Celestial-affinity primary."
        with self.assertRaises(AffinityGateError) as ctx:
            raise AffinityGateError(expected_msg)
        self.assertEqual(ctx.exception.user_message, expected_msg)

    def test_default_user_message_when_no_args(self) -> None:
        from world.magic.exceptions import (
            AffinityGateError,
            NoSoulTetherUnlockError,
            RescueValidationError,
            SineatingValidationError,
            SoulTetherFormationError,
        )

        for cls in [
            AffinityGateError,
            NoSoulTetherUnlockError,
            SoulTetherFormationError,
            SineatingValidationError,
            RescueValidationError,
        ]:
            err = cls()
            self.assertNotEqual(
                err.user_message,
                "",
                f"{cls.__name__} should have a non-empty default",
            )
            self.assertIn(
                err.user_message,
                cls.SAFE_MESSAGES,
                f"{cls.__name__} default should be in SAFE_MESSAGES",
            )


class TypesImportTests(TestCase):
    def test_types_module_imports(self) -> None:
        from world.magic.types.soul_tether import (
            SoulTetherRole,
        )

        self.assertEqual(SoulTetherRole.ABYSSAL.value, "ABYSSAL")
        self.assertEqual(SoulTetherRole.SINEATER.value, "SINEATER")

    def test_sineating_offer_frozen(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.types.soul_tether import SineatingOffer
        from world.relationships.factories import CharacterRelationshipFactory

        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sinner, target=sineater)
        resonance = ResonanceFactory()

        offer = SineatingOffer(
            sinner_sheet=sinner,
            sineater_sheet=sineater,
            relationship=relationship,
            resonance=resonance,
            max_units_offered=10,
            anima_cost_per_unit=2,
            fatigue_cost_per_unit=1,
            current_hollow=5,
            hollow_max=20,
            sineater_current_strain_stage=0,
        )
        self.assertEqual(offer.max_units_offered, 10)
        # Verify it's frozen (immutable)
        with self.assertRaises(AttributeError):
            offer.max_units_offered = 5  # type: ignore[misc]


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
