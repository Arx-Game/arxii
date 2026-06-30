"""Tests for SignatureMotifBonus catalog model + payload child rows (#1582).

TDD: written before the model exists; initial run should fail with ImportError.
"""

import contextlib

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.magic.constants import TargetKind
from world.magic.factories import (
    FacetFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import (
    SignatureMotifBonus,
    SignatureMotifBonusAppliedCondition,
    SignatureMotifBonusCapabilityGrant,
    SignatureMotifBonusDamageProfile,
    Thread,
)
from world.traits.factories import TraitFactory


class SignatureMotifBonusCreationTests(TestCase):
    """Tests for creating SignatureMotifBonus catalog rows."""

    @classmethod
    def setUpTestData(cls):
        cls.facet = FacetFactory(name="Wolf")
        cls.resonance = ResonanceFactory()

    def test_creation_with_required_facet(self):
        """A bonus requiring only a facet gate can be created."""
        bonus = SignatureMotifBonus.objects.create(
            name="Wolf's Fang",
            narrative_snippet="Your strikes carry the hungering edge of the wolf.",
            required_facet=self.facet,
            flat_intensity_delta=1,
        )
        self.assertEqual(bonus.name, "Wolf's Fang")
        self.assertEqual(bonus.required_facet, self.facet)
        self.assertIsNone(bonus.required_resonance)
        self.assertEqual(bonus.flat_intensity_delta, 1)

    def test_creation_with_required_resonance(self):
        """A bonus requiring only a resonance gate can be created."""
        bonus = SignatureMotifBonus.objects.create(
            name="Resonant Surge",
            required_resonance=self.resonance,
        )
        self.assertEqual(bonus.required_resonance, self.resonance)
        self.assertIsNone(bonus.required_facet)
        self.assertEqual(bonus.flat_intensity_delta, 0)

    def test_creation_with_both_gates(self):
        """A bonus may require both facet and resonance."""
        bonus = SignatureMotifBonus.objects.create(
            name="Spider Silk",
            required_facet=self.facet,
            required_resonance=self.resonance,
        )
        self.assertEqual(bonus.required_facet, self.facet)
        self.assertEqual(bonus.required_resonance, self.resonance)

    def test_narrative_snippet_defaults_blank(self):
        """narrative_snippet is optional (defaults to blank string)."""
        bonus = SignatureMotifBonus.objects.create(
            name="Plain Bonus",
            required_facet=self.facet,
        )
        self.assertEqual(bonus.narrative_snippet, "")

    def test_str_representation(self):
        """__str__ includes the bonus name."""
        bonus = SignatureMotifBonus(name="My Bonus")
        self.assertIn("My Bonus", str(bonus))


class SignatureMotifBonusCleanTests(TestCase):
    """Tests for SignatureMotifBonus.clean() gate-field validation."""

    def test_clean_raises_when_neither_gate_field_set(self):
        """clean() must raise ValidationError when both gate fields are None."""
        bonus = SignatureMotifBonus(
            name="Invalid",
            required_facet=None,
            required_resonance=None,
        )
        with self.assertRaises(ValidationError):
            bonus.clean()

    def test_clean_passes_with_facet_only(self):
        """clean() does not raise when required_facet is set."""
        facet = FacetFactory()
        bonus = SignatureMotifBonus(name="OK", required_facet=facet)
        # Should not raise
        bonus.clean()

    def test_clean_passes_with_resonance_only(self):
        """clean() does not raise when required_resonance is set."""
        resonance = ResonanceFactory()
        bonus = SignatureMotifBonus(name="OK", required_resonance=resonance)
        bonus.clean()

    def test_clean_passes_with_both(self):
        """clean() does not raise when both gate fields are set."""
        facet = FacetFactory()
        resonance = ResonanceFactory()
        bonus = SignatureMotifBonus(
            name="OK",
            required_facet=facet,
            required_resonance=resonance,
        )
        bonus.clean()


class SignatureMotifBonusCachedPayloadTests(TestCase):
    """Tests for cached_* payload accessor properties."""

    @classmethod
    def setUpTestData(cls):
        cls.facet = FacetFactory()
        cls.bonus = SignatureMotifBonus.objects.create(
            name="Payload Bonus",
            required_facet=cls.facet,
        )
        cls.condition_template = ConditionTemplateFactory()
        cls.capability_type = CapabilityTypeFactory()
        cls.damage_type = DamageTypeFactory()

    def test_cached_condition_applications_returns_attached_row(self):
        """cached_condition_applications returns the attached applied condition."""
        applied = SignatureMotifBonusAppliedCondition.objects.create(
            signature_bonus=self.bonus,
            condition=self.condition_template,
        )
        # Invalidate cache if present
        with contextlib.suppress(AttributeError):
            del self.bonus.cached_condition_applications
        result = self.bonus.cached_condition_applications
        self.assertIn(applied, result)

    def test_cached_capability_grants_returns_attached_row(self):
        """cached_capability_grants returns the attached capability grant."""
        grant = SignatureMotifBonusCapabilityGrant.objects.create(
            signature_bonus=self.bonus,
            capability=self.capability_type,
        )
        with contextlib.suppress(AttributeError):
            del self.bonus.cached_capability_grants
        result = self.bonus.cached_capability_grants
        self.assertIn(grant, result)

    def test_cached_damage_profiles_returns_attached_row(self):
        """cached_damage_profiles returns the attached damage profile."""
        profile = SignatureMotifBonusDamageProfile.objects.create(
            signature_bonus=self.bonus,
            damage_type=self.damage_type,
        )
        with contextlib.suppress(AttributeError):
            del self.bonus.cached_damage_profiles
        result = self.bonus.cached_damage_profiles
        self.assertIn(profile, result)

    def test_cached_condition_applications_empty_when_none(self):
        """cached_condition_applications returns empty list when no rows attached."""
        bonus = SignatureMotifBonus.objects.create(
            name="Empty Bonus",
            required_facet=self.facet,
        )
        self.assertEqual(bonus.cached_condition_applications, [])

    def test_cached_capability_grants_empty_when_none(self):
        """cached_capability_grants returns empty list when no rows attached."""
        bonus = SignatureMotifBonus.objects.create(
            name="Empty Bonus 2",
            required_facet=self.facet,
        )
        self.assertEqual(bonus.cached_capability_grants, [])

    def test_cached_damage_profiles_empty_when_none(self):
        """cached_damage_profiles returns empty list when no rows attached."""
        bonus = SignatureMotifBonus.objects.create(
            name="Empty Bonus 3",
            required_facet=self.facet,
        )
        self.assertEqual(bonus.cached_damage_profiles, [])


class SignatureMotifBonusQualifiesForTests(TestCase):
    """Tests for SignatureMotifBonus.qualifies_for(character_sheet)."""

    @classmethod
    def setUpTestData(cls):
        # A character with a motif
        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory()
        # Attach resonance to motif
        cls.motif_resonance = MotifResonanceFactory(
            motif=cls.motif,
            resonance=cls.resonance,
        )
        # Attach facet to that motif resonance
        cls.assoc = MotifResonanceAssociationFactory(
            motif_resonance=cls.motif_resonance,
            facet=cls.facet,
        )

        # A character with no motif
        cls.sheet_no_motif = CharacterSheetFactory()

        # A character with a motif but a DIFFERENT facet/resonance
        cls.sheet_other = CharacterSheetFactory()
        cls.other_motif = MotifFactory(character=cls.sheet_other)
        cls.other_resonance = ResonanceFactory()
        cls.other_facet = FacetFactory()
        cls.other_motif_resonance = MotifResonanceFactory(
            motif=cls.other_motif,
            resonance=cls.other_resonance,
        )
        MotifResonanceAssociationFactory(
            motif_resonance=cls.other_motif_resonance,
            facet=cls.other_facet,
        )

    def test_qualifies_for_true_when_facet_matches(self):
        """Returns True when required_facet is present in the character's motif."""
        bonus = SignatureMotifBonus.objects.create(
            name="Facet Gate",
            required_facet=self.facet,
        )
        self.assertTrue(bonus.qualifies_for(self.sheet))

    def test_qualifies_for_false_when_facet_missing(self):
        """Returns False when the character's motif lacks the required facet."""
        bonus = SignatureMotifBonus.objects.create(
            name="Facet Gate 2",
            required_facet=self.facet,
        )
        # sheet_other has other_facet, not cls.facet
        self.assertFalse(bonus.qualifies_for(self.sheet_other))

    def test_qualifies_for_false_when_no_motif(self):
        """Returns False when the character has no Motif row."""
        bonus = SignatureMotifBonus.objects.create(
            name="No Motif Gate",
            required_facet=self.facet,
        )
        self.assertFalse(bonus.qualifies_for(self.sheet_no_motif))

    def test_qualifies_for_true_when_resonance_matches(self):
        """Returns True when required_resonance is present in the character's motif."""
        bonus = SignatureMotifBonus.objects.create(
            name="Resonance Gate",
            required_resonance=self.resonance,
        )
        self.assertTrue(bonus.qualifies_for(self.sheet))

    def test_qualifies_for_false_when_resonance_missing(self):
        """Returns False when the character's motif lacks the required resonance."""
        bonus = SignatureMotifBonus.objects.create(
            name="Resonance Gate 2",
            required_resonance=self.resonance,
        )
        # sheet_other has other_resonance, not cls.resonance
        self.assertFalse(bonus.qualifies_for(self.sheet_other))

    def test_qualifies_for_both_gates_and_semantics(self):
        """Returns True only when BOTH required_facet AND required_resonance match."""
        bonus = SignatureMotifBonus.objects.create(
            name="And Gate",
            required_facet=self.facet,
            required_resonance=self.resonance,
        )
        # sheet has both
        self.assertTrue(bonus.qualifies_for(self.sheet))

    def test_qualifies_for_fails_when_only_one_of_two_gates_passes(self):
        """Returns False when only one of two required gates passes."""
        # sheet_other has other_facet + other_resonance;
        # bonus requires cls.facet (not present on sheet_other)
        bonus = SignatureMotifBonus.objects.create(
            name="And Gate Fail",
            required_facet=self.facet,
            required_resonance=self.other_resonance,
        )
        # sheet_other has other_resonance (passes resonance gate)
        # but does NOT have cls.facet (fails facet gate)
        self.assertFalse(bonus.qualifies_for(self.sheet_other))


class ThreadSignatureBonusFKTests(TestCase):
    """Thread.signature_bonus FK: non-null only when target_kind==TECHNIQUE.

    TDD step for Task 3 (#1582): these tests are written before the FK exists
    and should initially FAIL with AttributeError / TypeError.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Sig FK Test Facet")
        cls.bonus = SignatureMotifBonus.objects.create(
            name="FK Test Bonus",
            required_facet=cls.facet,
        )
        # A Technique to anchor a TECHNIQUE-kind thread.
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        # A Trait to anchor a TRAIT-kind thread.
        cls.trait = TraitFactory()

    def test_signature_bonus_on_technique_thread_passes_full_clean(self) -> None:
        """Setting signature_bonus on a TECHNIQUE thread passes full_clean()."""
        thread = Thread(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            signature_bonus=self.bonus,
        )
        # Should not raise.
        thread.full_clean()

    def test_signature_bonus_null_on_technique_thread_passes(self) -> None:
        """signature_bonus=None on a TECHNIQUE thread is valid."""
        thread = Thread(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            signature_bonus=None,
        )
        thread.full_clean()

    def test_signature_bonus_on_trait_thread_raises_validation_error(self) -> None:
        """Setting signature_bonus on a TRAIT thread raises ValidationError."""
        thread = Thread(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=self.trait,
            signature_bonus=self.bonus,
        )
        with self.assertRaises(ValidationError) as ctx:
            thread.full_clean()
        self.assertIn("signature_bonus", ctx.exception.message_dict)

    def test_signature_bonus_null_on_trait_thread_passes(self) -> None:
        """signature_bonus=None on a TRAIT thread is valid."""
        thread = Thread(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=self.trait,
            signature_bonus=None,
        )
        thread.full_clean()

    def test_signature_bonus_on_facet_thread_raises_validation_error(self) -> None:
        """Setting signature_bonus on a FACET thread raises ValidationError."""
        facet = FacetFactory(name="Anchor Facet")
        thread = Thread(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            signature_bonus=self.bonus,
        )
        with self.assertRaises(ValidationError) as ctx:
            thread.full_clean()
        self.assertIn("signature_bonus", ctx.exception.message_dict)
