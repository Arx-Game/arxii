"""Tests for alteration tier schema validation."""

from django.test import TestCase

from world.magic.constants import MIN_ALTERATION_DESCRIPTION_LENGTH, AlterationTier
from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.services import validate_alteration_resolution


class ValidateAlterationResolutionTests(TestCase):
    """Test validate_alteration_resolution service function."""

    @classmethod
    def setUpTestData(cls):
        from world.conditions.factories import DamageTypeFactory

        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(
            name="Shadow",
            affinity=cls.affinity,
        )
        cls.damage_type = DamageTypeFactory(name="Holy")

    def _valid_payload(self, **overrides):
        """Return a valid resolution payload dict with optional overrides."""
        base = {
            "tier": AlterationTier.MARKED,
            "origin_affinity_id": self.affinity.pk,
            "origin_resonance_id": self.resonance.pk,
            "name": "Test Alteration",
            "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "weakness_magnitude": 1,
            "weakness_damage_type_id": self.damage_type.pk,
            "resonance_bonus_magnitude": 1,
            "social_reactivity_magnitude": 1,
            "is_visible_at_rest": False,
        }
        base.update(overrides)
        return base

    def test_valid_payload_passes(self):
        """A well-formed payload at tier 2 passes validation."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(),
            is_staff=False,
        )
        assert errors == []

    def test_tier_mismatch_rejected(self):
        """Payload tier must match pending tier."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.TOUCHED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(tier=AlterationTier.MARKED),
            is_staff=False,
        )
        assert any("tier" in e.lower() for e in errors)

    def test_affinity_mismatch_rejected(self):
        """Payload affinity must match pending origin."""
        other_affinity = AffinityFactory(name="Celestial")
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                origin_affinity_id=other_affinity.pk,
            ),
            is_staff=False,
        )
        assert any("affinity" in e.lower() for e in errors)

    def test_weakness_exceeds_cap_rejected(self):
        """Weakness magnitude above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(weakness_magnitude=5),
            is_staff=False,
        )
        assert any("weakness" in e.lower() for e in errors)

    def test_resonance_bonus_exceeds_cap_rejected(self):
        """Resonance bonus above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(resonance_bonus_magnitude=5),
            is_staff=False,
        )
        assert any("resonance" in e.lower() for e in errors)

    def test_social_reactivity_exceeds_cap_rejected(self):
        """Social reactivity above tier cap is rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(social_reactivity_magnitude=5),
            is_staff=False,
        )
        assert any("social" in e.lower() for e in errors)

    def test_visibility_required_at_tier_4(self):
        """is_visible_at_rest must be True at tier 4+."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED_PROFOUNDLY,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                tier=AlterationTier.MARKED_PROFOUNDLY,
                weakness_magnitude=3,
                resonance_bonus_magnitude=3,
                social_reactivity_magnitude=3,
                is_visible_at_rest=False,
            ),
            is_staff=False,
        )
        assert any("visible" in e.lower() for e in errors)

    def test_description_too_short_rejected(self):
        """Descriptions below minimum length are rejected."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(player_description="too short"),
            is_staff=False,
        )
        assert any("description" in e.lower() for e in errors)

    def test_weakness_without_damage_type_rejected(self):
        """weakness_magnitude > 0 requires weakness_damage_type."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                weakness_magnitude=1,
                weakness_damage_type_id=None,
            ),
            is_staff=False,
        )
        assert any("damage_type" in e.lower() for e in errors)

    def test_non_staff_library_entry_rejected(self):
        """Non-staff cannot set is_library_entry=True."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(is_library_entry=True),
            is_staff=False,
        )
        assert any("library" in e.lower() for e in errors)

    def test_staff_can_set_library_entry(self):
        """Staff can set is_library_entry=True."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(is_library_entry=True),
            is_staff=True,
        )
        assert errors == []

    def test_library_duplicate_rejected(self):
        """Cannot use a library entry the character already has active."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory
        from world.magic.factories import MagicalAlterationTemplateFactory

        sheet = CharacterSheetFactory()
        library_entry = MagicalAlterationTemplateFactory(
            is_library_entry=True,
            tier=AlterationTier.MARKED,
        )
        # Simulate the condition already being active
        ConditionInstanceFactory(
            target=sheet.character,
            condition=library_entry.condition_template,
            severity=1,
        )
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload={"library_entry_pk": library_entry.pk},
            is_staff=False,
            character_sheet=sheet,
        )
        assert any("already" in e.lower() for e in errors)

    def test_library_pk_without_character_sheet_rejected(self):
        """library_entry_pk requires character_sheet to validate duplicates."""
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(library_entry_pk=1),
            is_staff=False,
            character_sheet=None,
        )
        assert any("character_sheet" in e.lower() for e in errors)

    def test_resonance_mismatch_rejected(self):
        """Payload resonance must match pending origin."""
        other_resonance = ResonanceFactory(
            name="Flame",
            affinity=self.affinity,
        )
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.MARKED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=self._valid_payload(
                origin_resonance_id=other_resonance.pk,
            ),
            is_staff=False,
        )
        assert any("resonance" in e.lower() for e in errors)
