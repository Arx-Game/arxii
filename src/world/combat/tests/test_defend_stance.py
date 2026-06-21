"""TDD tests for the DEFEND passive stance (#1273, Task 6).

The DEFEND passive is a preventative, roll-free mitigation technique that works by
installing a "Shielded" reactive condition on allies. When DAMAGE_PRE_APPLY fires for
a shielded ally, a MODIFY_PAYLOAD flow multiplies the incoming amount by 0.5, halving
the damage — deterministically and without any dice roll.

Pipeline:
    PC declares DEFEND passive → _resolve_passive_actions →
        _apply_passive_technique (ALLY branch) → bulk_apply_conditions →
        _install_reactive_side_effects installs Shielded's trigger on each ally →
    NPC hits ally → apply_damage_to_participant emits DAMAGE_PRE_APPLY →
        ally's trigger fires MODIFY_PAYLOAD(multiply 0.5) →
        effective_damage = original // 2 (int from float * int).
"""

from django.test import TestCase

from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.defend_content import (
    DEFEND_PASSIVE_NAME,
    SHIELDED_CONDITION_NAME,
    ensure_defend_content,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.services import (
    _apply_passive_technique,
    apply_damage_to_participant,
)
from world.conditions.models import ConditionInstance
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_encounter_with_ally():
    """Create a DECLARING encounter with two ACTIVE participants sharing the room.

    Returns (encounter, defender, ally, room):
    - defender: the PC who will declare DEFEND
    - ally:     the other PC who will receive the Shielded condition
    - room:     the encounter's room (used for character.location)
    """
    encounter = CombatEncounterFactory(
        status=EncounterStatus.DECLARING,
        round_number=1,
    )
    room = encounter.room

    defender = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
    ally = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)

    # Characters must be in the room so emit_event can find their trigger_handler.
    defender.character_sheet.character.location = room
    ally.character_sheet.character.location = room

    CharacterVitals.objects.get_or_create(
        character_sheet=defender.character_sheet,
        defaults={"health": 100, "max_health": 100},
    )
    CharacterVitals.objects.get_or_create(
        character_sheet=ally.character_sheet,
        defaults={"health": 100, "max_health": 100},
    )

    return encounter, defender, ally, room


# ---------------------------------------------------------------------------
# Content-seeding smoke test
# ---------------------------------------------------------------------------


class EnsureDefendContentTest(TestCase):
    """ensure_defend_content() creates all expected rows idempotently."""

    def setUp(self):
        ensure_defend_content()

    def test_shielded_condition_exists(self):
        from world.conditions.models import ConditionTemplate

        self.assertTrue(ConditionTemplate.objects.filter(name=SHIELDED_CONDITION_NAME).exists())

    def test_shielded_condition_has_reactive_trigger(self):
        from flows.constants import EventName
        from world.conditions.models import ConditionTemplate

        template = ConditionTemplate.objects.get(name=SHIELDED_CONDITION_NAME)
        trigger_defs = list(template.reactive_triggers.all())
        self.assertEqual(len(trigger_defs), 1)
        td = trigger_defs[0]
        self.assertEqual(td.event_name, EventName.DAMAGE_PRE_APPLY)

    def test_defend_technique_exists(self):
        self.assertTrue(Technique.objects.filter(name=DEFEND_PASSIVE_NAME).exists())

    def test_defend_technique_has_ally_condition_application(self):
        tech = Technique.objects.get(name=DEFEND_PASSIVE_NAME)
        row = tech.condition_applications.get()
        self.assertEqual(row.target_kind, ConditionTargetKind.ALLY)
        self.assertEqual(row.condition.name, SHIELDED_CONDITION_NAME)

    def test_idempotent_second_call(self):
        """Calling ensure_defend_content twice must not raise or create duplicates."""
        ensure_defend_content()
        self.assertEqual(Technique.objects.filter(name=DEFEND_PASSIVE_NAME).count(), 1)


# ---------------------------------------------------------------------------
# Passive application: ally receives Shielded condition
# ---------------------------------------------------------------------------


class DefendPassiveShieldsAllyTest(TestCase):
    """After _apply_passive_technique, the ally carries the Shielded condition."""

    def setUp(self):
        ensure_defend_content()
        self.encounter, self.defender, self.ally, self.room = _setup_encounter_with_ally()
        self.defend_tech = Technique.objects.get(name=DEFEND_PASSIVE_NAME)

    def test_ally_receives_shielded_condition(self):
        _apply_passive_technique(self.defend_tech, self.defender, self.encounter)

        ally_char = self.ally.character_sheet.character
        instances = ConditionInstance.objects.filter(
            target=ally_char,
            condition__name=SHIELDED_CONDITION_NAME,
            resolved_at__isnull=True,
        )
        self.assertTrue(
            instances.exists(),
            "DEFEND passive must install the Shielded condition on the active ally.",
        )

    def test_defender_does_not_receive_shielded(self):
        """ALLY target_kind must NOT apply the condition to the defender themselves."""
        _apply_passive_technique(self.defend_tech, self.defender, self.encounter)

        defender_char = self.defender.character_sheet.character
        instances = ConditionInstance.objects.filter(
            target=defender_char,
            condition__name=SHIELDED_CONDITION_NAME,
            resolved_at__isnull=True,
        )
        self.assertFalse(
            instances.exists(),
            "DEFEND passive must NOT apply Shielded to the declaring PC (ALLY, not SELF).",
        )


# ---------------------------------------------------------------------------
# Reactive trigger: Shielded halves incoming damage
# ---------------------------------------------------------------------------


class ShieldedConditionHalvesDamageTest(TestCase):
    """End-to-end: the Shielded reactive condition halves incoming damage.

    Pipeline: _apply_passive_technique installs Shielded on ally →
    apply_damage_to_participant emits DAMAGE_PRE_APPLY →
    ally's Shielded trigger fires MODIFY_PAYLOAD(multiply 0.5) →
    ally takes N//2.

    We call _apply_passive_technique directly (not resolve_round) so the
    test is independent of encounter-status bookkeeping and character-location
    setup is explicit.
    """

    NPC_DAMAGE = 40

    def setUp(self):
        ensure_defend_content()

        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.room = self.encounter.room

        self.defender = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.ally = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )

        # Place characters in the room so emit_event finds their triggers.
        # character.location = room persists db_location to DB AND updates
        # room.contents_cache so emit_event's _gather_triggers finds the ally.
        self.ally_char = self.ally.character_sheet.character
        self.ally_char.location = self.room

        # Defender doesn't need location for the passive-dispatch test.
        self.defender_char = self.defender.character_sheet.character

        # Vitals — ally starts at full health.
        self.ally_vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.ally.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        self.ally_vitals.health = 100
        self.ally_vitals.max_health = 100
        self.ally_vitals.save()

        self.defend_tech = Technique.objects.get(name=DEFEND_PASSIVE_NAME)

    def test_defend_stance_halves_ally_damage(self):
        """Ally takes NPC_DAMAGE // 2 after DEFEND passive installs Shielded."""
        # Step 1: Apply the DEFEND passive — installs Shielded + reactive trigger on ally.
        _apply_passive_technique(self.defend_tech, self.defender, self.encounter)

        # Confirm the trigger was installed (Trigger row exists for the ally's char).
        from flows.models.triggers import Trigger

        self.assertTrue(
            Trigger.objects.filter(obj=self.ally_char).exists(),
            "Shielded's reactive trigger must be installed as a Trigger row on the ally.",
        )

        # Confirm the ally is still in the room (location must not be None for
        # emit_event to fire the DAMAGE_PRE_APPLY trigger in apply_damage_to_participant).
        self.assertEqual(
            self.ally_char.location,
            self.room,
            "Ally's character must be in the room so emit_event(DAMAGE_PRE_APPLY) fires.",
        )

        # TriggerHandler.on_trigger_added defers cache invalidation to
        # transaction.on_commit (rollback-safe design). In Django TestCase,
        # the test transaction is never committed, so the callback never fires
        # and _populated stays True with the stale pre-install _by_event cache.
        # Force an immediate re-populate so the next emit_event finds the trigger.
        self.ally_char.trigger_handler._reset()

        # Step 2: NPC deals damage to the ally via apply_damage_to_participant.
        # emit_event(DAMAGE_PRE_APPLY, ..., location=ally_char.location) fires
        # the Shielded trigger → multiply 0.5 → ally takes N//2 damage.
        result = apply_damage_to_participant(
            self.ally,
            self.NPC_DAMAGE,
            damage_type=None,
        )

        self.ally_vitals.refresh_from_db()
        expected_damage = self.NPC_DAMAGE // 2
        actual_damage = 100 - self.ally_vitals.health

        self.assertEqual(
            actual_damage,
            expected_damage,
            f"Expected Shielded to halve damage to {expected_damage}, "
            f"but ally took {actual_damage}.",
        )
        self.assertEqual(result.damage_dealt, expected_damage)

    def test_no_shielded_ally_takes_full_damage(self):
        """Control: without Shielded condition, ally takes the full NPC_DAMAGE."""
        # Don't call _apply_passive_technique — no Shielded condition, no trigger.
        result = apply_damage_to_participant(
            self.ally,
            self.NPC_DAMAGE,
            damage_type=None,
        )

        self.ally_vitals.refresh_from_db()
        actual_damage = 100 - self.ally_vitals.health

        self.assertEqual(
            actual_damage,
            self.NPC_DAMAGE,
            f"Without DEFEND, ally should take full {self.NPC_DAMAGE} damage, "
            f"but took {actual_damage}.",
        )
        self.assertEqual(result.damage_dealt, self.NPC_DAMAGE)
