"""Tests for authored causal recognition evidence and safe deed labels (#3914)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.societies.causal_recognition import (
    CREATED_OPENING,
    ENVOY_RESCUE,
    attach_recognition_labels,
    collect_recognition_evidence,
    labels_for_entry,
    record_created_opening,
    record_envoy_rescue,
)
from world.societies.constants import RenownRisk
from world.societies.factories import LegendEntryFactory
from world.societies.models import (
    LegendContribution,
    LegendEntryRecognition,
    LegendRecognitionEvidence,
    LegendRecognitionRule,
)
from world.stories.constants import StakeOutcomeMethod, StakeResolutionColumn
from world.stories.factories import BeatFactory, StakeFactory
from world.stories.models import StakeContractActivation, StakeOutcome


class CausalRecognitionTests(EvenniaTestCase):
    """Causal labels are explicit, idempotent, and safe for player reads."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.beat = BeatFactory()
        cls.activation = StakeContractActivation.objects.create(
            beat=cls.beat,
            party_average_level=2,
            declared_target_level=3,
            declared_risk=RenownRisk.EXTREME,
            effective_risk=RenownRisk.EXTREME,
            is_ready=True,
        )
        cls.rescue_rule = LegendRecognitionRule.objects.create(
            key=ENVOY_RESCUE,
            source_kind="rescue",
            label="Saved the envoy",
            description="Turned aside the blow meant for the envoy.",
        )
        cls.opening_rule = LegendRecognitionRule.objects.create(
            key=CREATED_OPENING,
            source_kind="break_bar",
            label="Created an opening",
            description="Broke the enemy's guard so the party could press forward.",
        )
        cls.entry = LegendEntryFactory(persona=cls.sheet.primary_persona)

    def test_high_check_without_authored_cause_is_not_recognition(self) -> None:
        """A severe scene or an unreferenced check never creates a label."""
        self.assertEqual(collect_recognition_evidence(self.activation), [])
        stake = StakeFactory(beat=self.beat, subject_label="ordinary peril")
        StakeOutcome.objects.create(
            stake=stake,
            activation=self.activation,
            column=StakeResolutionColumn.WIN,
            method=StakeOutcomeMethod.MACHINE,
        )
        LegendContribution.objects.create(
            character_sheet=self.sheet,
            activation=self.activation,
            check_type=CheckTypeFactory(),
            stake=stake,
            success_level=99,
            was_crucial=True,
        )
        LegendRecognitionRule.objects.create(
            key="bridge_hold",
            source_kind="stake",
            subject_label_contains="bridge",
            minimum_success_level=1,
            label="Held the bridge",
        )
        self.assertEqual(collect_recognition_evidence(self.activation), [])

    def test_rescue_and_opening_are_idempotent_and_add_no_value(self) -> None:
        """Retries produce one evidence row and one zero-value entry label."""
        original_value = self.entry.base_value
        first = record_envoy_rescue(
            self.activation,
            self.sheet,
            source_id=101,
            source_action_id=55,
            protected_sheet=self.other_sheet,
        )
        second = record_envoy_rescue(
            self.activation,
            self.sheet,
            source_id=101,
            source_action_id=55,
            protected_sheet=self.other_sheet,
        )
        self.assertEqual(first.pk, second.pk)
        record_created_opening(self.activation, self.sheet, source_id=202, contribution_kind="hold")
        record_created_opening(self.activation, self.sheet, source_id=202, contribution_kind="hold")
        labels = attach_recognition_labels([self.entry], self.activation)
        attach_recognition_labels([self.entry], self.activation)
        self.assertEqual(LegendRecognitionEvidence.objects.count(), 2)
        self.assertEqual(LegendEntryRecognition.objects.filter(entry=self.entry).count(), 2)
        self.assertEqual(self.entry.base_value, original_value)
        self.assertEqual(
            {label.key for label in labels[self.entry.pk]}, {ENVOY_RESCUE, CREATED_OPENING}
        )

    def test_safe_labels_omit_source_and_success_details(self) -> None:
        """The read shape contains labels only, never source IDs or roll quality."""
        record_envoy_rescue(
            self.activation,
            self.sheet,
            source_id=303,
            source_action_id=404,
            protected_sheet=self.other_sheet,
        )
        attach_recognition_labels([self.entry], self.activation)
        payload = [label.__dict__ for label in labels_for_entry(self.entry)]
        self.assertEqual(payload[0]["key"], ENVOY_RESCUE)
        self.assertNotIn("source_id", payload[0])
        self.assertNotIn("source_action_id", payload[0])
        self.assertNotIn("success_level", payload[0])
