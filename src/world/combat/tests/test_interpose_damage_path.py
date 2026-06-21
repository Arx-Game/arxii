"""Tests for _try_interpose wired into apply_damage_to_participant (#1273, Task 5).

TDD: write failing tests first, then implement.

The PG-tagged test (InterposeReducesAllyDamageTest) exercises the full stack:
- Guardian declares INTERPOSE for Ally with a telekinesis capability
  granted via ConditionCapabilityEffect.
- An NPC opponent attacks Ally with a known base_damage.
- After apply_damage_to_participant resolves (with perform_check mocked to
  return a clean-block success), Ally's CharacterVitals.health drops by LESS
  than the raw damage N.

Tagged @tag("postgres") because apply_condition (capability grant) uses
DISTINCT ON in get_available_actions, which fails on the SQLite fast tier.

Also includes two SQLite-safe unit tests:
- _try_interpose no-ops when the encounter is not in RESOLVING status.
- apply_damage_to_participant returns 0-damage result when interpose zeroes
  the payload (covered via mocking _try_interpose itself).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from world.combat.constants import (
    CombatManeuver,
    EncounterStatus,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundAction,
)
from world.combat.interpose_content import ensure_interpose_content
from world.combat.services import _try_interpose, apply_damage_to_participant
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# SQLite-safe helpers
# ---------------------------------------------------------------------------


def _make_vitals(participant, health: int = 100, max_health: int = 100) -> CharacterVitals:
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.save()
    return vitals


# ---------------------------------------------------------------------------
# SQLite-safe: _try_interpose guard — no-op outside of RESOLVING status
# ---------------------------------------------------------------------------


class TryInterposeNoOpOutsideResolvingTest(TestCase):
    """_try_interpose must be a no-op when the encounter is not RESOLVING.

    Covers the non-combat guard: if the encounter has any status other than
    RESOLVING, the function returns early without querying CombatRoundAction.
    This ensures non-combat callers of apply_damage_to_participant are
    unaffected.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        ensure_interpose_content()

        self.encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.participant)

    def test_try_interpose_no_op_when_declaring(self) -> None:
        """No CombatRoundAction query fires when encounter is DECLARING."""
        from flows.events.payloads import DamagePreApplyPayload, DamageSource

        pre_payload = DamagePreApplyPayload(
            target=self.participant.character_sheet.character,
            amount=50,
            damage_type=None,
            source=DamageSource(type="character", ref=None),
        )
        original_amount = pre_payload.amount

        with patch("world.combat.models.CombatRoundAction.objects.filter") as mock_filter:
            _try_interpose(self.participant, pre_payload)

        mock_filter.assert_not_called()
        self.assertEqual(
            pre_payload.amount,
            original_amount,
            "_try_interpose must not mutate payload when not RESOLVING",
        )

    def test_try_interpose_no_op_when_completed(self) -> None:
        """No mutation when encounter is COMPLETED."""
        from flows.events.payloads import DamagePreApplyPayload, DamageSource

        self.encounter.status = EncounterStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        self.participant.encounter.status = EncounterStatus.COMPLETED

        pre_payload = DamagePreApplyPayload(
            target=self.participant.character_sheet.character,
            amount=50,
            damage_type=None,
            source=DamageSource(type="character", ref=None),
        )
        original_amount = pre_payload.amount

        with patch("world.combat.models.CombatRoundAction.objects.filter") as mock_filter:
            _try_interpose(self.participant, pre_payload)

        mock_filter.assert_not_called()
        self.assertEqual(pre_payload.amount, original_amount)


# ---------------------------------------------------------------------------
# SQLite-safe: early-return-on-zero branch
# ---------------------------------------------------------------------------


class ApplyDamageZeroAfterInterposeTest(TestCase):
    """apply_damage_to_participant returns 0-damage result when _try_interpose zeroes the payload.

    This is the SQLite-safe unit test for the early-return branch added in Step 3.
    We mock _try_interpose to set amount=0 directly, then verify the function
    returns a ParticipantDamageResult(damage_dealt=0) without touching health.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.encounter = CombatEncounterFactory(status=EncounterStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.vitals = _make_vitals(self.participant, health=80, max_health=100)

        character = self.participant.character_sheet.character

        room = self.encounter.room
        character.db_location = room
        character.save(update_fields=["db_location"])

    def test_zero_payload_returns_zero_damage_result(self) -> None:
        """When _try_interpose zeroes the payload, damage_dealt=0 and health unchanged."""

        def _zero_payload(participant, pre_payload):
            pre_payload.amount = 0

        health_before = self.vitals.health

        with patch("world.combat.services._try_interpose", side_effect=_zero_payload):
            result = apply_damage_to_participant(self.participant, 40)

        self.assertEqual(result.damage_dealt, 0)
        self.assertFalse(result.knockout_eligible)
        self.assertFalse(result.death_eligible)
        self.assertFalse(result.permanent_wound_eligible)

        # Health must NOT have changed — the early return fires before vitals.save()
        self.vitals.refresh_from_db()
        self.assertEqual(
            self.vitals.health,
            health_before,
            "health must be unchanged when interpose blocks the damage",
        )


# ---------------------------------------------------------------------------
# PG-only: full integration — ally health drops less than raw damage
# ---------------------------------------------------------------------------


@tag("postgres")  # apply_condition (capability grant) uses DISTINCT ON (PG-only)
class InterposeReducesAllyDamageTest(TestCase):
    """End-to-end: Guardian's INTERPOSE reduces damage dealt to Ally.

    Setup:
    - One encounter (RESOLVING) with two participants: Guardian and Ally.
    - Guardian has a telekinesis ConditionCapabilityEffect (grants the
      interpose capability used by dispatch_interpose).
    - A CombatRoundAction(maneuver=INTERPOSE, focused_ally_target=Ally) for Guardian.
    - Ally's ChallengeInstance for "Interpose" is pre-bound (as _ensure_interpose_challenges
      would do in resolve_round).
    - perform_check is mocked to return a clean-block SUCCESS (success_level=2),
      forcing a DESTROY resolution that zeroes pre_payload.amount.

    Assertion:
    - Ally's CharacterVitals.health drops by LESS than the raw damage N (40 in
      this test). Specifically, the mock forces a clean block → health unchanged.
    """

    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        idmapper_models.flush_cache()

        ensure_interpose_content()

        # Seed the check-resolution pipeline (ResultCharts + outcomes for rank diffs).
        # Without this, _get_difficulty_indicator_for_check finds no chart for
        # the interpose's Reflexes roll → IMPOSSIBLE → the approach is dropped.
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        self.room = create_object("typeclasses.rooms.Room", key="InterposeRoom", nohome=True)

        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=1,
            room=self.room,
        )

        # Guardian: will declare INTERPOSE for Ally
        guardian_sheet = CharacterSheetFactory()
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.guardian = guardian_sheet.character
        self.guardian.db_location = self.room
        self.guardian.save(update_fields=["db_location"])

        # Ally: the protected target
        ally_sheet = CharacterSheetFactory()
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])

        # Grant Guardian telekinesis via a condition.
        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name="TelekineticGuardian")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(self.guardian, grant_template)

        # Ally's vitals: 100 HP.
        self.ally_vitals = _make_vitals(self.ally_participant, health=100, max_health=100)
        _make_vitals(self.guardian_participant)

        # Declare INTERPOSE for Ally this round.
        CombatRoundAction.objects.create(
            participant=self.guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ally_participant,
            is_ready=True,
        )

        # Pre-bind the Interpose ChallengeInstance to Ally (mirrors _ensure_interpose_challenges).
        template = ChallengeTemplate.objects.get(name="Interpose")
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=self.ally,
            is_active=True,
            defaults={"location": self.room, "is_revealed": True},
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_interpose_reduces_ally_health_by_less_than_raw_damage(self, mock_check) -> None:
        """Guardian's telekinetic interpose reduces the blow: Ally takes less than 40 damage."""
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        # Force a clean-block SUCCESS (success_level=2).
        success = CheckOutcomeFactory(name="CleanBlock", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        raw_damage = 40
        result = apply_damage_to_participant(self.ally_participant, raw_damage)

        # The interpose should have fired (mock called at least once).
        self.assertTrue(mock_check.called, "dispatch_interpose must route through perform_check")

        # Ally's health must have dropped by LESS than raw_damage (clean block → 0 damage).
        self.ally_vitals.refresh_from_db()
        health_drop = 100 - self.ally_vitals.health
        self.assertLess(
            health_drop,
            raw_damage,
            f"Interpose must reduce damage below {raw_damage}; health dropped by {health_drop}",
        )

        # Full clean block → damage_dealt == 0 and health unchanged.
        self.assertEqual(result.damage_dealt, 0, "clean block must result in 0 damage_dealt")
        self.assertEqual(
            self.ally_vitals.health,
            100,
            "clean block must leave ally at full health",
        )
