"""Integration tests for reactive event emission in combat services (Tasks 28/29).

Tests verify:
- DAMAGE_PRE_APPLY is emitted with correct payload
- Cancellation of DAMAGE_PRE_APPLY skips damage
- MODIFY_PAYLOAD on DAMAGE_PRE_APPLY changes the effective damage amount
- DAMAGE_APPLIED is emitted after vitals are updated
- CHARACTER_INCAPACITATED is gated on knockout_eligible
- CHARACTER_KILLED is gated on death_eligible
- ATTACK_PRE_RESOLVE cancellation skips the attack
"""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import TriggerScope
from flows.consts import FlowActionChoices
from flows.events.names import EventNames
from flows.events.payloads import (
    CharacterIncapacitatedPayload,
    CharacterKilledPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction
from world.combat.services import apply_damage_to_participant, resolve_npc_attack
from world.conditions.factories import ReactiveConditionFactory
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


def _make_set_amount_flow(new_amount: int):
    """Return a FlowDefinition that sets DamagePreApply.amount to *new_amount*."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": "amount", "op": "set", "value": new_amount},
    )
    return flow


def _participant_with_vitals(health: int = 100, max_health: int = 100):
    """Return (participant, vitals) with a character in a room."""
    participant = CombatParticipantFactory()
    character = participant.character_sheet.character
    room = _create_room()
    character.location = room
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.status = CharacterStatus.ALIVE
    vitals.save()
    return participant, vitals


# ---------------------------------------------------------------------------
# Task 28: DAMAGE_PRE_APPLY emission
# ---------------------------------------------------------------------------


class DamagePreApplyEmissionTest(TestCase):
    """apply_damage_to_participant emits DAMAGE_PRE_APPLY with correct payload."""

    def test_damage_pre_apply_is_emitted(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list[tuple[str, object]] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            captured.append((event_name, payload))
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 10, damage_type="fire")
        finally:
            svc_mod.emit_event = original

        pre_events = [p for name, p in captured if name == EventNames.DAMAGE_PRE_APPLY]
        self.assertEqual(len(pre_events), 1)
        p = pre_events[0]
        self.assertIsInstance(p, DamagePreApplyPayload)
        self.assertEqual(p.amount, 10)
        self.assertEqual(p.damage_type, "fire")

    def test_damage_pre_apply_payload_has_target(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        captured: list[DamagePreApplyPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.DAMAGE_PRE_APPLY:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 10)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0].target, character)

    def test_damage_pre_apply_source_classify(self) -> None:
        """Source kwarg is classified into a DamageSource."""
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        attacker = CharacterFactory()
        captured: list[DamagePreApplyPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.DAMAGE_PRE_APPLY:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 10, source=attacker)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        src = captured[0].source
        self.assertIsInstance(src, DamageSource)
        self.assertEqual(src.type, "character")
        self.assertIs(src.ref, attacker)


# ---------------------------------------------------------------------------
# Cancellation test
# ---------------------------------------------------------------------------


class DamagePreApplyCancellationTest(TestCase):
    """Cancelling DAMAGE_PRE_APPLY skips the damage."""

    def test_cancellation_skips_damage(self) -> None:
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        cancel_flow = _make_cancel_flow()

        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=cancel_flow,
            target=character,
            scope=TriggerScope.PERSONAL,
        )

        result = apply_damage_to_participant(participant, 10, damage_type="physical")

        vitals.refresh_from_db()
        # Health must be unchanged
        self.assertEqual(vitals.health, 100)
        # Returned result shows zero damage dealt
        self.assertEqual(result.damage_dealt, 0)
        self.assertFalse(result.knockout_eligible)
        self.assertFalse(result.death_eligible)

    def test_cancellation_health_after_unchanged(self) -> None:
        participant, vitals = _participant_with_vitals(health=80, max_health=100)
        character = participant.character_sheet.character
        cancel_flow = _make_cancel_flow()

        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=cancel_flow,
            target=character,
            scope=TriggerScope.PERSONAL,
        )

        result = apply_damage_to_participant(participant, 50)

        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 80)
        self.assertEqual(result.health_after, 80)


# ---------------------------------------------------------------------------
# MODIFY_PAYLOAD test
# ---------------------------------------------------------------------------


class DamageModifyPayloadTest(TestCase):
    """MODIFY_PAYLOAD on DAMAGE_PRE_APPLY changes effective damage."""

    def test_modify_amount_reduces_damage(self) -> None:
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character

        # Modify: set amount to 5 even though we pass 10
        modify_flow = _make_set_amount_flow(5)
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=modify_flow,
            target=character,
            scope=TriggerScope.PERSONAL,
        )

        result = apply_damage_to_participant(participant, 10)

        vitals.refresh_from_db()
        # Health should drop by 5 (modified), not 10 (original)
        self.assertEqual(vitals.health, 95)
        self.assertEqual(result.damage_dealt, 5)


# ---------------------------------------------------------------------------
# DAMAGE_APPLIED emission
# ---------------------------------------------------------------------------


class DamageAppliedEmissionTest(TestCase):
    """DAMAGE_APPLIED is emitted after vitals are saved."""

    def test_damage_applied_emitted_with_hp_after(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list[DamageAppliedPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.DAMAGE_APPLIED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 30)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, DamageAppliedPayload)
        self.assertEqual(p.hp_after, 70)
        self.assertEqual(p.amount_dealt, 30)

    def test_damage_applied_not_emitted_when_cancelled(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        cancel_flow = _make_cancel_flow()

        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=cancel_flow,
            target=character,
            scope=TriggerScope.PERSONAL,
        )

        captured_applied: list = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.DAMAGE_APPLIED:
                captured_applied.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 10)
        finally:
            svc_mod.emit_event = original

        # DAMAGE_APPLIED must NOT fire when pre was cancelled
        self.assertEqual(len(captured_applied), 0)


# ---------------------------------------------------------------------------
# Incapacitation gate
# ---------------------------------------------------------------------------


class IncapacitationEventTest(TestCase):
    """CHARACTER_INCAPACITATED is emitted when knockout_eligible."""

    def test_incapacitation_emitted_on_knockout_eligible(self) -> None:
        # 100 HP, max 100. Damage 85 → 15 HP = 15% < 20% threshold
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list[CharacterIncapacitatedPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.CHARACTER_INCAPACITATED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            result = apply_damage_to_participant(participant, 85)
        finally:
            svc_mod.emit_event = original

        self.assertTrue(result.knockout_eligible)
        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, CharacterIncapacitatedPayload)

    def test_incapacitation_not_emitted_when_not_eligible(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.CHARACTER_INCAPACITATED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            result = apply_damage_to_participant(participant, 30)  # 70 HP remaining
        finally:
            svc_mod.emit_event = original

        self.assertFalse(result.knockout_eligible)
        self.assertEqual(len(captured), 0)


# ---------------------------------------------------------------------------
# Death gate
# ---------------------------------------------------------------------------


class DeathEventTest(TestCase):
    """CHARACTER_KILLED is emitted when death_eligible."""

    def test_death_emitted_on_death_eligible(self) -> None:
        # 100 HP. Damage 100 → 0 HP = death eligible
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list[CharacterKilledPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.CHARACTER_KILLED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            result = apply_damage_to_participant(participant, 100)
        finally:
            svc_mod.emit_event = original

        self.assertTrue(result.death_eligible)
        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, CharacterKilledPayload)

    def test_death_emitted_on_force_death(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list[CharacterKilledPayload] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.CHARACTER_KILLED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            apply_damage_to_participant(participant, 5, force_death=True)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)

    def test_death_not_emitted_below_threshold(self) -> None:
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        captured: list = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.CHARACTER_KILLED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit
        try:
            result = apply_damage_to_participant(participant, 50)  # 50 HP remaining
        finally:
            svc_mod.emit_event = original

        self.assertFalse(result.death_eligible)
        self.assertEqual(len(captured), 0)


# ---------------------------------------------------------------------------
# ATTACK_PRE_RESOLVE cancellation via resolve_npc_attack
# ---------------------------------------------------------------------------


class AttackPreResolveCancellationTest(TestCase):
    """ATTACK_PRE_RESOLVE cancellation skips the attack."""

    def _build_npc_attack_setup(self):
        """Build minimal objects for resolve_npc_attack."""
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=20)
        encounter = CombatEncounterFactory()
        opponent = CombatOpponentFactory(encounter=encounter, health=100, max_health=100)
        action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        return action, encounter, opponent

    def test_attack_pre_resolve_emission(self) -> None:
        """resolve_npc_attack emits ATTACK_PRE_RESOLVE."""
        action, _encounter, _opponent = self._build_npc_attack_setup()
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)

        from world.checks.factories import CheckTypeFactory  # type: ignore[attr-defined]

        check_type = CheckTypeFactory()
        captured: list[tuple] = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            captured.append((event_name, payload))
            return original(event_name, payload, **kwargs)

        svc_mod.emit_event = capturing_emit

        # Stub perform_check to avoid needing full check infrastructure
        mock_check = MagicMock()
        mock_check.success_level = 0  # miss → 0 damage

        def fake_check(char, ct):
            return mock_check

        try:
            resolve_npc_attack(action, participant, check_type, perform_check_fn=fake_check)
        finally:
            svc_mod.emit_event = original

        pre_events = [name for name, _ in captured if name == EventNames.ATTACK_PRE_RESOLVE]
        self.assertGreaterEqual(len(pre_events), 1)

    def test_attack_pre_resolve_cancellation_skips_damage(self) -> None:
        """Cancelling ATTACK_PRE_RESOLVE on the target means no damage is applied."""
        action, _encounter, _opponent = self._build_npc_attack_setup()
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.ATTACK_PRE_RESOLVE,
            flow_definition=cancel_flow,
            target=character,
            scope=TriggerScope.PERSONAL,
        )

        from world.checks.factories import CheckTypeFactory  # type: ignore[attr-defined]

        check_type = CheckTypeFactory()

        mock_check = MagicMock()
        mock_check.success_level = -2  # critical hit → should be big damage if not cancelled

        def fake_check(char, ct):
            return mock_check

        resolve_npc_attack(action, participant, check_type, perform_check_fn=fake_check)

        vitals.refresh_from_db()
        # If ATTACK_PRE_RESOLVE was cancelled, damage should be skipped
        self.assertEqual(vitals.health, 100)
