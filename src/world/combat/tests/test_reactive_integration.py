"""Integration tests for reactive event emission in combat services.

All scenarios exercise the unified-dispatch model: ``emit_event(name, payload,
location)`` gathers triggers from the room and its contents, sorts by priority
desc, and dispatches on a single FlowStack. Self-targeting is expressed as a
filter (``SELF_FILTER``) rather than an old PERSONAL scope.

Tests verify:
- DAMAGE_PRE_APPLY is emitted with correct payload
- Cancellation of DAMAGE_PRE_APPLY skips damage
- MODIFY_PAYLOAD on DAMAGE_PRE_APPLY changes the effective damage amount
- DAMAGE_APPLIED is emitted after vitals are updated
- CHARACTER_INCAPACITATED is gated on knockout_eligible
- CHARACTER_KILLED is gated on death_eligible
- ATTACK_PRE_RESOLVE cancellation skips the attack
- Typeclass hook (at_attacked) emits ATTACK_LANDED — distinct from service path
- Damage-source discrimination (scar vs character) via filter conditions
"""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
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
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}


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


def _participant_with_vitals(health: int = 100, max_health: int = 100, room=None):
    """Return (participant, vitals) with a character placed in a room."""
    participant = CombatParticipantFactory()
    character = participant.character_sheet.character
    if room is None:
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
# DAMAGE_PRE_APPLY emission
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

        pre_events = [p for name, p in captured if name == EventName.DAMAGE_PRE_APPLY]
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
            if event_name == EventName.DAMAGE_PRE_APPLY:
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
            if event_name == EventName.DAMAGE_PRE_APPLY:
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
# Cancellation
# ---------------------------------------------------------------------------


class DamagePreApplyCancellationTest(TestCase):
    """Cancelling DAMAGE_PRE_APPLY skips the damage."""

    def test_cancellation_skips_damage(self) -> None:
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        cancel_flow = _make_cancel_flow()

        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=character,
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
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=character,
        )

        result = apply_damage_to_participant(participant, 50)

        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 80)
        self.assertEqual(result.health_after, 80)


# ---------------------------------------------------------------------------
# MODIFY_PAYLOAD
# ---------------------------------------------------------------------------


class DamageModifyPayloadTest(TestCase):
    """MODIFY_PAYLOAD on DAMAGE_PRE_APPLY changes effective damage."""

    def test_modify_amount_reduces_damage(self) -> None:
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character

        # Modify: set amount to 5 even though we pass 10
        modify_flow = _make_set_amount_flow(5)
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=modify_flow,
            target=character,
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
            if event_name == EventName.DAMAGE_APPLIED:
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
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=character,
        )

        captured_applied: list = []

        import world.combat.services as svc_mod

        original = svc_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.DAMAGE_APPLIED:
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
            if event_name == EventName.CHARACTER_INCAPACITATED:
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
            if event_name == EventName.CHARACTER_INCAPACITATED:
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
            if event_name == EventName.CHARACTER_KILLED:
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
            if event_name == EventName.CHARACTER_KILLED:
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
            if event_name == EventName.CHARACTER_KILLED:
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
# ATTACK_PRE_RESOLVE via resolve_npc_attack
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

        pre_events = [name for name, _ in captured if name == EventName.ATTACK_PRE_RESOLVE]
        self.assertGreaterEqual(len(pre_events), 1)

    def test_attack_pre_resolve_cancellation_skips_damage(self) -> None:
        """Cancelling ATTACK_PRE_RESOLVE on the target means no damage is applied."""
        action, _encounter, _opponent = self._build_npc_attack_setup()
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character

        # ATTACK_PRE_RESOLVE carries targets=[character]; a self-filtered scar
        # on the character fires when the character is in the target list.
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_PRE_RESOLVE,
            filter_condition={"path": "targets", "op": "contains", "value": "self"},
            flow_definition=cancel_flow,
            target=character,
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


# ---------------------------------------------------------------------------
# Typeclass hook dual-path — at_attacked emits ATTACK_LANDED distinctly
# ---------------------------------------------------------------------------


class TypeclassHookDualPathTest(TestCase):
    """Typeclass hook dual-path: Character.at_attacked emits ATTACK_LANDED via
    the typeclass hook. Combat services emit DAMAGE_PRE_APPLY separately via
    apply_damage_to_participant. Both paths produce equivalent events that the
    reactive layer can respond to independently.

    A reactive trigger on ATTACK_LANDED only responds to the typeclass hook
    path, not to DAMAGE_PRE_APPLY from the service path.
    """

    def test_at_attacked_hook_emits_attack_landed(self) -> None:
        """Character.at_attacked emits ATTACK_LANDED — scar fires there."""
        char = CharacterFactory()
        room = _create_room("DualPathRoomA")
        char.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_LANDED,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=char,
        )

        attacker = CharacterFactory()
        weapon = MagicMock()
        damage_result = MagicMock()
        action = MagicMock()

        # Capture emissions to verify ATTACK_LANDED is emitted
        captured: list[str] = []
        import flows.emit as emit_mod
        import typeclasses.characters as chars_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            captured.append(event_name)
            return original(event_name, payload, **kwargs)

        chars_mod.emit_event = capturing_emit
        try:
            char.at_attacked(attacker, weapon, damage_result, action)
        finally:
            chars_mod.emit_event = original

        self.assertIn(EventName.ATTACK_LANDED, captured)

    def test_service_path_emits_damage_pre_apply_not_attack_landed(self) -> None:
        """apply_damage_to_participant emits DAMAGE_PRE_APPLY, not ATTACK_LANDED.

        The two paths are distinct: typeclass hook emits ATTACK_LANDED,
        service function emits DAMAGE_PRE_APPLY. A scar on ATTACK_LANDED does
        not fire during the service path.
        """
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character

        # Install a cancel scar on ATTACK_LANDED only
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_LANDED,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=character,
        )

        # Apply damage via service — only DAMAGE_PRE_APPLY is emitted, not ATTACK_LANDED
        result = apply_damage_to_participant(participant, 20, damage_type="physical")

        vitals.refresh_from_db()
        # ATTACK_LANDED scar did NOT fire — damage was applied normally
        self.assertEqual(result.damage_dealt, 20)
        self.assertEqual(vitals.health, 80)

    def test_near_miss_no_scar_both_paths_resolve_normally(self) -> None:
        """Without any scars, both emission paths complete without cancellation."""
        char = CharacterFactory()
        room = _create_room("DualPathRoomC")
        char.location = room

        # at_attacked hook: no scar → no cancellation
        attacker = CharacterFactory()
        weapon = MagicMock()
        damage_result = MagicMock()
        action = MagicMock()
        # Should not raise
        char.at_attacked(attacker, weapon, damage_result, action)

        # Service path: no scar → damage applied
        participant, _vitals = _participant_with_vitals(health=100, max_health=100)
        result = apply_damage_to_participant(participant, 10)
        self.assertEqual(result.damage_dealt, 10)


# ---------------------------------------------------------------------------
# Damage-source discrimination via filter conditions
# ---------------------------------------------------------------------------


class DamageSourceDiscriminationScarVsWeaponTest(TestCase):
    """Filter-driven damage-source discrimination.

    Two wards on the same character differentiated by source.type in the filter:
      - Scar-ward: cancels DAMAGE_PRE_APPLY when source.type == "scar"
      - Weapon-ward: cancels DAMAGE_PRE_APPLY when source.type == "character"

    Scar-sourced damage fires the scar-ward, not the weapon-ward, and vice
    versa. Each test uses apply_damage_to_participant so the real service
    emission path runs — the filter DSL evaluates against the live payload.
    """

    def _install_scar_ward(self, character):
        """Install a ward that cancels ONLY when source.type == 'scar'."""
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.type", "op": "==", "value": "scar"},
                ]
            },
            flow_definition=cancel_flow,
            target=character,
        )

    def _install_weapon_ward(self, character):
        """Install a ward that cancels ONLY when source.type == 'character'."""
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.type", "op": "==", "value": "character"},
                ]
            },
            flow_definition=cancel_flow,
            target=character,
        )

    def test_hit_scar_source_trips_scar_ward_only(self):
        """Scar-sourced damage triggers the scar-ward — damage cancelled."""
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        self._install_scar_ward(character)

        # Synthesize a scar source via a stub object that classify_source maps
        # to type="scar". Since classify_source only recognises specific refs,
        # we bypass it by calling apply_damage_to_participant with a DamageSource-
        # shaped marker passed through as source.
        #
        # classify_source treats an arbitrary object as type="character". To get
        # source.type == "scar" on the payload we bypass the service and use
        # emit_event directly with a hand-built DamagePreApplyPayload. This still
        # exercises the same reactive pipeline (room gather, filter, flow).
        from flows.emit import emit_event

        payload = DamagePreApplyPayload(
            target=character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="scar", ref=None),
        )
        stack = emit_event(EventName.DAMAGE_PRE_APPLY, payload, location=character.location)
        self.assertTrue(stack.was_cancelled())
        # No service damage was applied
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100)

    def test_near_miss_weapon_source_does_not_trip_scar_ward(self):
        """Character-sourced damage does NOT trip the scar-ward."""
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        self._install_scar_ward(character)

        # Use the service path with a character source — classify_source wraps
        # into DamageSource(type="character", ref=attacker). Scar-ward filter
        # should reject (!="scar").
        attacker = CharacterFactory()
        result = apply_damage_to_participant(
            participant, 10, damage_type="physical", source=attacker
        )
        vitals.refresh_from_db()
        self.assertEqual(result.damage_dealt, 10)
        self.assertEqual(vitals.health, 90)

    def test_hit_weapon_source_trips_weapon_ward_only(self):
        """Character-sourced damage triggers the weapon-ward — damage cancelled."""
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        self._install_weapon_ward(character)

        attacker = CharacterFactory()
        result = apply_damage_to_participant(
            participant, 10, damage_type="physical", source=attacker
        )
        vitals.refresh_from_db()
        self.assertEqual(result.damage_dealt, 0)
        self.assertEqual(vitals.health, 100)

    def test_near_miss_scar_source_does_not_trip_weapon_ward(self):
        """Scar-sourced damage does NOT trip the weapon-ward."""
        participant, vitals = _participant_with_vitals(health=100, max_health=100)
        character = participant.character_sheet.character
        self._install_weapon_ward(character)

        from flows.emit import emit_event

        payload = DamagePreApplyPayload(
            target=character,
            amount=10,
            damage_type="physical",
            source=DamageSource(type="scar", ref=None),
        )
        stack = emit_event(EventName.DAMAGE_PRE_APPLY, payload, location=character.location)
        self.assertFalse(stack.was_cancelled())
        # Service path not invoked here, so vitals unchanged
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100)
