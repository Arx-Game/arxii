"""Tests for ``try_declare_sustained_ritual`` — deferring a ritual across
combat rounds instead of dispatching it immediately (#2705, Task 5).

Covers the "not sustained, dispatch immediately as today" inertness cases —
no active participant / encounter not DECLARING, ``sustained_rounds == 0`` (or
no ``RitualCheckConfig`` at all), non-empty kwargs (the ADR-0007 guard), and
a participant already holding an earlier-round commitment (D2-consistency,
mirrors ``_validate_no_pending_sustained`` without raising) — plus the fire
path: budget rolled via ``roll_sustained_absorption_budget``, a RITUAL-kind
``SustainedAction`` created with ``declared_action=None``, and the same
same-round-replacement idempotence Task 2 established for techniques.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.combat.constants import CONCENTRATION_CHECK_TYPE_NAME, ParticipantStatus, SustainedKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatEncounter, CombatParticipant, SustainedAction
from world.combat.services import declare_action, try_declare_sustained_ritual
from world.fatigue.constants import EffortLevel
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_declaring_encounter(round_number: int = 1) -> CombatEncounter:
    return CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=round_number)


def _make_active_participant(encounter: CombatEncounter) -> CombatParticipant:
    participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=100, max_health=100
    )
    return participant


def _make_sustained_ritual(*, sustained_rounds: int = 2):
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.SERVICE,
        service_function_path="world.magic.services.placeholder_ritual",
    )
    RitualCheckConfigFactory(ritual=ritual, sustained_rounds=sustained_rounds)
    return ritual


class _SustainedRitualDeclarationBase(TestCase):
    """Shared Concentration ``CheckType`` — see ``test_sustained_declaration.py``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.concentration_category = CheckCategoryFactory(name="sustained-ritual-composure-checks")
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )


class SustainedRitualFiresTests(_SustainedRitualDeclarationBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = _make_declaring_encounter(round_number=1)
        self.participant = _make_active_participant(self.encounter)
        self.ritual = _make_sustained_ritual(sustained_rounds=2)

    def test_creates_sustained_action_ritual_kind(self) -> None:
        sustained = try_declare_sustained_ritual(
            sheet=self.participant.character_sheet, ritual=self.ritual, kwargs={}
        )
        self.assertIsNotNone(sustained)
        self.assertEqual(SustainedAction.objects.count(), 1)
        row = SustainedAction.objects.get()
        self.assertEqual(row.sustained_kind, SustainedKind.RITUAL)
        self.assertEqual(row.ritual_id, self.ritual.pk)
        self.assertIsNone(row.technique_id)
        self.assertIsNone(row.declared_action_id)
        self.assertEqual(row.declared_round, 1)
        self.assertEqual(row.resolves_round, 3)
        self.assertGreaterEqual(row.absorption_budget, 0)
        self.assertLessEqual(row.absorption_budget, 4)

    def test_returns_the_created_row(self) -> None:
        sustained = try_declare_sustained_ritual(
            sheet=self.participant.character_sheet, ritual=self.ritual, kwargs={}
        )
        self.assertEqual(sustained.pk, SustainedAction.objects.get().pk)

    def test_same_round_replacement_idempotence(self) -> None:
        first = try_declare_sustained_ritual(
            sheet=self.participant.character_sheet, ritual=self.ritual, kwargs={}
        )
        second = try_declare_sustained_ritual(
            sheet=self.participant.character_sheet, ritual=self.ritual, kwargs={}
        )
        self.assertEqual(SustainedAction.objects.count(), 1)
        self.assertNotEqual(first.pk, second.pk)


class SustainedRitualInertnessTests(_SustainedRitualDeclarationBase):
    def test_no_active_participant_dispatches_immediately(self) -> None:
        """No CombatParticipant at all for this sheet — the outside-combat case."""
        lone_sheet = CharacterSheetFactory()
        ritual = _make_sustained_ritual(sustained_rounds=2)

        result = try_declare_sustained_ritual(sheet=lone_sheet, ritual=ritual, kwargs={})

        self.assertIsNone(result)
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_encounter_not_declaring_dispatches_immediately(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        participant = _make_active_participant(encounter)
        ritual = _make_sustained_ritual(sustained_rounds=2)

        result = try_declare_sustained_ritual(
            sheet=participant.character_sheet, ritual=ritual, kwargs={}
        )

        self.assertIsNone(result)
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_sustained_rounds_zero_dispatches_immediately(self) -> None:
        encounter = _make_declaring_encounter()
        participant = _make_active_participant(encounter)
        ritual = _make_sustained_ritual(sustained_rounds=0)

        result = try_declare_sustained_ritual(
            sheet=participant.character_sheet, ritual=ritual, kwargs={}
        )

        self.assertIsNone(result)
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_no_check_config_dispatches_immediately(self) -> None:
        encounter = _make_declaring_encounter()
        participant = _make_active_participant(encounter)
        ritual = RitualFactory()  # no RitualCheckConfig sidecar at all

        result = try_declare_sustained_ritual(
            sheet=participant.character_sheet, ritual=ritual, kwargs={}
        )

        self.assertIsNone(result)
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_non_empty_kwargs_dispatches_immediately(self) -> None:
        """ADR-0007 guard: a ritual invoked with per-cast kwargs cannot be deferred."""
        encounter = _make_declaring_encounter()
        participant = _make_active_participant(encounter)
        ritual = _make_sustained_ritual(sustained_rounds=2)

        result = try_declare_sustained_ritual(
            sheet=participant.character_sheet,
            ritual=ritual,
            kwargs={"thread": object()},
        )

        self.assertIsNone(result)
        self.assertEqual(SustainedAction.objects.count(), 0)

    def test_already_holding_earlier_commitment_dispatches_immediately(self) -> None:
        """D2-consistency: a participant already sustaining a technique doesn't
        get a second parallel commitment stacked via the ritual path — the
        ritual dispatches immediately instead (no raise; this isn't the
        round-declaration seam)."""
        encounter = _make_declaring_encounter(round_number=1)
        participant = _make_active_participant(encounter)
        gift = GiftFactory()
        effect_type = EffectTypeFactory(base_power=None)
        technique = TechniqueFactory(gift=gift, effect_type=effect_type, windup_rounds=2)
        declare_action(participant, focused_action=technique, effort_level=EffortLevel.MEDIUM)
        self.assertEqual(SustainedAction.objects.count(), 1)

        # Advance to round 2 — strictly between declared_round (1) and resolves_round (3).
        encounter.round_number = 2
        encounter.save(update_fields=["round_number"])

        ritual = _make_sustained_ritual(sustained_rounds=2)
        result = try_declare_sustained_ritual(
            sheet=participant.character_sheet, ritual=ritual, kwargs={}
        )

        self.assertIsNone(result)
        # Still exactly the one technique-side commitment; no ritual row added.
        self.assertEqual(SustainedAction.objects.count(), 1)
        self.assertEqual(SustainedAction.objects.get().sustained_kind, SustainedKind.TECHNIQUE)
