"""Integration tests for dramatic traps (#1051, #520 Phase 6).

A trap is a room-anchored hazard. On entry an armed, not-yet-resolved trap
runs a detection check whose graded outcome is resolved through the trap's
``consequence_pool`` via the shared effect-handler path
(``select_consequence`` -> ``apply_resolution`` -> ``_deal_damage`` ->
``process_damage_consequences``). A success-tier roll carries no damage
consequence (the entrant spots and avoids it); a failure-tier roll fires the
authored damage. Disarm routes the same pool through ``disarm_check_type``.
"""

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import DamageTypeFactory
from world.room_features.factories import TrapFactory
from world.room_features.trap_services import check_room_traps_on_entry
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory


class _TrapSceneMixin:
    """Builds a character, a room, and one armed spike-trap dealing 30 on failure."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.failure_outcome = CheckOutcomeFactory(name="Trap-Failure", success_level=0)
        cls.success_outcome = CheckOutcomeFactory(name="Trap-Success", success_level=1)

    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.character = CharacterFactory(db_key="victim")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)

        # Consequence pool: a FAILURE-tier consequence dealing 30 self-damage.
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=self.failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            target=EffectTarget.SELF,
            damage_amount=30,
            damage_type=DamageTypeFactory(name="trap-spikes"),
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        self.trap = TrapFactory(
            room_profile=self.room_profile,
            consequence_pool=pool,
            detect_check_type=CheckTypeFactory(name="Detect Traps"),
            disarm_check_type=CheckTypeFactory(name="Disarm Traps"),
            detect_difficulty=20,
            disarm_difficulty=20,
        )

    def _health(self) -> int:
        self.vitals.refresh_from_db()
        return self.vitals.health


class TrapModelTest(_TrapSceneMixin, TestCase):
    def test_factory_builds_armed_hidden_undetected_trap(self) -> None:
        assert self.trap.is_armed is True
        assert self.trap.is_hidden is True
        assert self.trap.detected_by.count() == 0
        assert self.trap.room_profile == self.room_profile

    def test_room_profile_reverse_accessor(self) -> None:
        assert list(self.room_profile.traps.all()) == [self.trap]


class TrapEntryResolutionTest(_TrapSceneMixin, TestCase):
    def test_armed_undetected_trap_fires_on_failed_detection(self) -> None:
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 70
        assert self.sheet in self.trap.detected_by.all()

    def test_detection_success_avoids_damage(self) -> None:
        with force_check_outcome(self.success_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 100
        assert self.sheet in self.trap.detected_by.all()

    def test_already_resolved_trap_does_not_refire(self) -> None:
        self.trap.detected_by.add(self.sheet)
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 100

    def test_disarmed_trap_does_not_fire(self) -> None:
        self.trap.is_armed = False
        self.trap.save(update_fields=["is_armed"])
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 100

    def test_room_without_profile_is_noop(self) -> None:
        # A bare object with no room_profile must not raise.
        check_room_traps_on_entry(self.character, self.character)
        assert self._health() == 100


class TrapDisarmActionTest(_TrapSceneMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.character.location = self.room
        self.character.save()

    def test_successful_disarm_disarms_trap(self) -> None:
        action = get_action("disarm_trap")
        with force_check_outcome(self.success_outcome):
            result = action.run(self.character, trap_id=self.trap.pk)

        assert result.success is True
        self.trap.refresh_from_db()
        assert self.trap.is_armed is False
        assert self._health() == 100

    def test_failed_disarm_triggers_trap(self) -> None:
        action = get_action("disarm_trap")
        with force_check_outcome(self.failure_outcome):
            result = action.run(self.character, trap_id=self.trap.pk)

        assert result.success is False
        self.trap.refresh_from_db()
        assert self.trap.is_armed is True
        assert self._health() == 70


class TrapMoveIntegrationTest(_TrapSceneMixin, TestCase):
    def test_moving_into_trapped_room_fires_trap(self) -> None:
        with force_check_outcome(self.failure_outcome):
            self.character.move_to(self.room, quiet=True)

        assert self._health() == 70
