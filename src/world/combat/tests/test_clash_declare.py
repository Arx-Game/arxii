"""Tests for Task 7.1: declare_clash_contribution service + DeclareClashContributionSerializer."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from world.combat.constants import ClashActionSlot, ClashStatus, EncounterStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.models import Clash, ClashContributionDeclaration
from world.combat.serializers import DeclareClashContributionSerializer
from world.combat.services import declare_clash_contribution
from world.magic.factories import TechniqueFactory
from world.magic.models import CharacterTechnique


class DeclareClashContributionTests(TestCase):
    """Service function tests for declare_clash_contribution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = ClashConfigFactory()
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=2,
        )
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.clash = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )
        cls.technique = TechniqueFactory()

    def test_creates_declaration(self) -> None:
        """Happy path: service creates a ClashContributionDeclaration with the right fields."""
        decl = declare_clash_contribution(
            participant=self.participant,
            clash=self.clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=self.technique,
            strain_commitment=5,
        )

        self.assertIsInstance(decl, ClashContributionDeclaration)
        self.assertEqual(decl.participant, self.participant)
        self.assertEqual(decl.clash, self.clash)
        self.assertEqual(decl.action_slot, ClashActionSlot.FOCUSED)
        self.assertEqual(decl.technique, self.technique)
        self.assertEqual(decl.strain_commitment, 5)
        self.assertEqual(decl.encounter, self.encounter)

    def test_round_number_from_encounter(self) -> None:
        """Declaration's round_number matches the encounter's current round_number."""
        decl = declare_clash_contribution(
            participant=self.participant,
            clash=self.clash,
            action_slot=ClashActionSlot.PASSIVE,
            technique=self.technique,
            strain_commitment=0,
        )
        self.assertEqual(decl.round_number, self.encounter.round_number)

    def test_idempotent_redeclaration_overrides(self) -> None:
        """Calling twice with different technique/strain creates ONE row (latter values win)."""
        technique2 = TechniqueFactory()

        declare_clash_contribution(
            participant=self.participant,
            clash=self.clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=self.technique,
            strain_commitment=3,
        )
        decl2 = declare_clash_contribution(
            participant=self.participant,
            clash=self.clash,
            action_slot=ClashActionSlot.PASSIVE,
            technique=technique2,
            strain_commitment=7,
        )

        total = ClashContributionDeclaration.objects.filter(
            participant=self.participant,
            clash=self.clash,
            encounter=self.encounter,
            round_number=self.encounter.round_number,
        ).count()
        self.assertEqual(total, 1)
        self.assertEqual(decl2.action_slot, ClashActionSlot.PASSIVE)
        self.assertEqual(decl2.technique, technique2)
        self.assertEqual(decl2.strain_commitment, 7)

    def test_defensive_assertion_encounter_mismatch(self) -> None:
        """ValueError raised when clash.encounter != participant.encounter (programmer error)."""
        other_encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        other_clash = ClashFactory(encounter=other_encounter, status=ClashStatus.ACTIVE)

        with self.assertRaises(ValueError):
            declare_clash_contribution(
                participant=self.participant,
                clash=other_clash,
                action_slot=ClashActionSlot.FOCUSED,
                technique=self.technique,
                strain_commitment=0,
            )

    def test_atomic(self) -> None:
        """If update_or_create raises, no partial state is left."""
        with patch(
            "world.combat.services.ClashContributionDeclaration.objects.update_or_create",
            side_effect=RuntimeError("db failure"),
        ):
            with self.assertRaises(RuntimeError):
                declare_clash_contribution(
                    participant=self.participant,
                    clash=self.clash,
                    action_slot=ClashActionSlot.FOCUSED,
                    technique=self.technique,
                    strain_commitment=0,
                )

        # Nothing should have been written.
        self.assertFalse(
            ClashContributionDeclaration.objects.filter(
                participant=self.participant,
                clash=self.clash,
                encounter=self.encounter,
                round_number=self.encounter.round_number,
            ).exists()
        )


class DeclareClashContributionSerializerTests(TestCase):
    """Serializer tests for DeclareClashContributionSerializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = ClashConfigFactory(passive_anima_cap=10)
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.clash = ClashFactory(
            encounter=cls.encounter,
            status=ClashStatus.ACTIVE,
        )
        cls.technique = TechniqueFactory()
        # Give the participant's character ownership of the technique.
        CharacterTechnique.objects.create(
            character=cls.participant.character_sheet,
            technique=cls.technique,
        )

    def _serialize(self, data: dict) -> dict:
        """Run serializer validation and return validated data (raises if invalid)."""
        serializer = DeclareClashContributionSerializer(
            data=data,
            context={"participant": self.participant},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def test_valid_input_passes(self) -> None:
        """Happy-path validation: returns validated dict with resolved model instances."""
        validated = self._serialize(
            {
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": self.technique.pk,
                "strain_commitment": 3,
            }
        )
        self.assertIsInstance(validated["clash"], Clash)
        self.assertEqual(validated["clash"].pk, self.clash.pk)
        self.assertEqual(validated["action_slot"], ClashActionSlot.FOCUSED)
        self.assertEqual(validated["technique"].pk, self.technique.pk)
        self.assertEqual(validated["strain_commitment"], 3)

    def test_inactive_clash_rejected(self) -> None:
        """Clash with status=RESOLVED raises ValidationError."""
        resolved_clash = ClashFactory(
            encounter=self.encounter,
            status=ClashStatus.RESOLVED,
        )
        serializer = DeclareClashContributionSerializer(
            data={
                "clash": resolved_clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": self.technique.pk,
                "strain_commitment": 0,
            },
            context={"participant": self.participant},
        )
        with self.assertRaises(ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("clash", ctx.exception.detail)

    def test_clash_not_in_participant_encounter_rejected(self) -> None:
        """Clash from a different encounter raises ValidationError."""
        other_encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        other_clash = ClashFactory(encounter=other_encounter, status=ClashStatus.ACTIVE)

        serializer = DeclareClashContributionSerializer(
            data={
                "clash": other_clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": self.technique.pk,
                "strain_commitment": 0,
            },
            context={"participant": self.participant},
        )
        with self.assertRaises(ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("clash", ctx.exception.detail)

    def test_passive_strain_above_cap_rejected(self) -> None:
        """PASSIVE contribution with strain_commitment > passive_anima_cap raises."""
        serializer = DeclareClashContributionSerializer(
            data={
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.PASSIVE,
                "technique": self.technique.pk,
                "strain_commitment": self.config.passive_anima_cap + 1,
            },
            context={"participant": self.participant},
        )
        with self.assertRaises(ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("strain_commitment", ctx.exception.detail)

    def test_passive_strain_at_cap_passes(self) -> None:
        """PASSIVE contribution at exactly the passive_anima_cap is valid."""
        validated = self._serialize(
            {
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.PASSIVE,
                "technique": self.technique.pk,
                "strain_commitment": self.config.passive_anima_cap,
            }
        )
        self.assertEqual(validated["strain_commitment"], self.config.passive_anima_cap)

    def test_focused_strain_above_passive_cap_passes(self) -> None:
        """FOCUSED slot has no passive cap; high strain_commitment is valid."""
        high_strain = self.config.passive_anima_cap + 100
        validated = self._serialize(
            {
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": self.technique.pk,
                "strain_commitment": high_strain,
            }
        )
        self.assertEqual(validated["strain_commitment"], high_strain)

    def test_unknown_technique_pk_rejected(self) -> None:
        """Non-existent technique PK raises ValidationError."""
        serializer = DeclareClashContributionSerializer(
            data={
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": 999999,
                "strain_commitment": 0,
            },
            context={"participant": self.participant},
        )
        with self.assertRaises(ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("technique", ctx.exception.detail)

    def test_pc_doesnt_own_technique_rejected(self) -> None:
        """Technique exists but the PC has no CharacterTechnique for it — rejected."""
        unowned_technique = TechniqueFactory()
        # Deliberately do NOT create a CharacterTechnique row for this participant.

        serializer = DeclareClashContributionSerializer(
            data={
                "clash": self.clash.pk,
                "action_slot": ClashActionSlot.FOCUSED,
                "technique": unowned_technique.pk,
                "strain_commitment": 0,
            },
            context={"participant": self.participant},
        )
        with self.assertRaises(ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("technique", ctx.exception.detail)
