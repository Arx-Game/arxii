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

from django.test import TestCase, tag

from world.combat.constants import ParticipantStatus
from world.combat.defend_content import (
    DEFEND_PASSIVE_NAME,
    SHIELDED_CONDITION_NAME,
    ensure_defend_content,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import (
    _apply_passive_technique,
    resolve_round,
)
from world.conditions.models import ConditionInstance
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.scenes.constants import RoundStatus
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
        status=RoundStatus.DECLARING,
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


@tag("postgres")
class ShieldedConditionHalvesDamageTest(TestCase):
    """End-to-end via the REAL ``resolve_round`` path: Shielded halves NPC damage.

    Production pipeline, no test-only shortcuts:
        defender declares DEFEND passive on a passive slot →
        resolve_round → _resolve_passive_actions → _apply_passive_technique (ALLY)
            → bulk_apply_conditions → _install_reactive_side_effects installs the
              Shielded reactive Trigger on the ally (bulk_create, in-transaction) →
        _refresh_participant_trigger_handlers refreshes the ally's TriggerHandler
            SYNCHRONOUSLY so the new Trigger is visible THIS round →
        NPC fixed-damage attack → apply_damage_to_participant emits
            DAMAGE_PRE_APPLY → ally's Shielded trigger fires MODIFY_PAYLOAD(0.5) →
        ally takes NPC_DAMAGE // 2.

    The whole round runs inside resolve_round's single @transaction.atomic block, so
    this proves the same-round ordering that production requires — the bug was that
    without the synchronous refresh the freshly-installed trigger was invisible until
    on_commit (after the round), so DEFEND did nothing the round it was declared.

    @tag("postgres"): bulk_apply_conditions → _build_bulk_context uses DISTINCT ON
    (.distinct("condition_id")), which is PG-only; runs on the parity tier.
    """

    NPC_DAMAGE = 40

    def _build_round(self, *, with_defend: bool):
        """Build an encounter with an ally; declare DEFEND on the defender iff asked.

        Returns (encounter, ally). The NPC always attacks the ally for fixed
        NPC_DAMAGE with no damage_type (so the only reduction is Shielded's 0.5).
        """
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        room = encounter.room

        defender = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        ally = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)

        # The ally's character must be in the room so emit_event(DAMAGE_PRE_APPLY)
        # finds its trigger_handler when the NPC hit lands.
        ally.character_sheet.character.location = room

        CharacterVitals.objects.create(
            character_sheet=defender.character_sheet,
            health=100,
            max_health=100,
        )
        CharacterVitals.objects.create(
            character_sheet=ally.character_sheet,
            health=100,
            max_health=100,
        )

        # Fixed-damage, no-type NPC attack targeting the ally.
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(
            pool=pool,
            base_damage=self.NPC_DAMAGE,
            damage_type=None,
        )
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        npc_action.targets.add(ally)

        action_kwargs = {}
        if with_defend:
            defend_tech = Technique.objects.get(name=DEFEND_PASSIVE_NAME)
            action_kwargs["physical_passive"] = defend_tech
        CombatRoundAction.objects.create(
            participant=defender,
            round_number=1,
            focused_category=None,
            focused_action=None,
            **action_kwargs,
        )
        return encounter, ally

    def setUp(self):
        ensure_defend_content()

    def _ally_damage_taken(self, *, with_defend: bool) -> int:
        encounter, ally = self._build_round(with_defend=with_defend)
        resolve_round(encounter)
        vitals = CharacterVitals.objects.get(character_sheet=ally.character_sheet)
        return 100 - vitals.health

    def test_defend_stance_halves_ally_damage(self):
        """Driving resolve_round, the shielded ally takes NPC_DAMAGE // 2, not full."""
        baseline = self._ally_damage_taken(with_defend=False)
        defended = self._ally_damage_taken(with_defend=True)

        self.assertEqual(
            baseline,
            self.NPC_DAMAGE,
            f"Without DEFEND the ally must take the full {self.NPC_DAMAGE} damage.",
        )
        self.assertEqual(
            defended,
            self.NPC_DAMAGE // 2,
            "DEFEND's Shielded must halve the NPC hit THE SAME ROUND it is declared "
            f"(expected {self.NPC_DAMAGE // 2}, got {defended}).",
        )
        self.assertLess(
            defended,
            baseline,
            "A declared DEFEND passive must measurably lower the NPC attack the "
            "same round it is declared.",
        )
