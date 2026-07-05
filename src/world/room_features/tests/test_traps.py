"""Integration tests for dramatic traps (#1051, #520 Phase 6).

A trap is a room-anchored hazard. On entry an armed, not-yet-resolved trap
runs a detection check whose graded outcome is resolved through the trap's
``consequence_pool`` via the shared effect-handler path
(``select_consequence`` -> ``apply_resolution`` -> ``_deal_damage`` ->
``process_damage_consequences``). A success-tier roll carries no damage
consequence (the entrant spots and avoids it); a failure-tier roll fires the
authored damage. Disarm routes the same pool through ``disarm_check_type``.
"""

from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.test_helpers import force_check_outcome
from world.checks.types import ResolutionContext
from world.conditions.factories import DamageTypeFactory
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.services import (
    apply_damage_reduction_from_threads,
    seed_thread_survivability_tuning,
)
from world.mechanics.effect_handlers import apply_effect
from world.mechanics.factories import SituationTemplateFactory, SituationTrapLinkFactory
from world.mechanics.situation_services import instantiate_situation
from world.room_features.factories import TrapFactory
from world.room_features.trap_services import check_room_traps_on_entry, check_traps_at_position
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

    def test_position_defaults_to_none(self) -> None:
        assert self.trap.position is None


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


class PositionScopedTrapTest(_TrapSceneMixin, TestCase):
    """Trap.position scoping (#1317): a position-anchored trap only fires there."""

    def setUp(self) -> None:
        super().setUp()
        self.character.location = self.room
        self.character.save()
        self.spike_position = PositionFactory(room=self.room, name="spike_pit")
        self.other_position = PositionFactory(room=self.room, name="safe_spot")
        self.trap.position = self.spike_position
        self.trap.save(update_fields=["position"])

    def test_position_scoped_trap_fires_at_its_own_position(self) -> None:
        place_in_position(self.character, self.spike_position)
        with force_check_outcome(self.failure_outcome):
            check_traps_at_position(self.character, self.spike_position)

        assert self._health() == 70
        assert self.sheet in self.trap.detected_by.all()

    def test_position_scoped_trap_does_not_fire_elsewhere(self) -> None:
        place_in_position(self.character, self.other_position)
        with force_check_outcome(self.failure_outcome):
            check_traps_at_position(self.character, self.other_position)

        assert self._health() == 100
        assert self.sheet not in self.trap.detected_by.all()

    def test_room_wide_trap_still_fires_via_check_traps_at_position(self) -> None:
        """A trap with position=None (room-wide) still fires no matter which
        Position within the room is checked — unchanged pre-#1317 semantics,
        now reachable via the position-aware entry point too."""
        self.trap.position = None
        self.trap.save(update_fields=["position"])
        place_in_position(self.character, self.other_position)
        with force_check_outcome(self.failure_outcome):
            check_traps_at_position(self.character, self.other_position)

        assert self._health() == 70

    def test_room_entry_still_finds_position_scoped_trap_when_landing_there(self) -> None:
        """check_room_traps_on_entry derives the entrant's landing Position and
        now also checks position-scoped traps anchored there."""
        place_in_position(self.character, self.spike_position)
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 70

    def test_room_entry_does_not_fire_position_scoped_trap_elsewhere(self) -> None:
        place_in_position(self.character, self.other_position)
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 100


class DealDamageThreadReductionTest(TestCase):
    """Thread-derived DR reduces _deal_damage (trap/effect-handler path) (#1251)."""

    def setUp(self) -> None:
        seed_thread_survivability_tuning()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        # Invest threads so the character has non-zero DR.
        ThreadFactory(owner=self.sheet, resonance=ResonanceFactory(), level=10)
        ThreadFactory(owner=self.sheet, resonance=ResonanceFactory(), level=10)

    def _health(self) -> int:
        self.vitals.refresh_from_db()
        return self.vitals.health

    def test_deal_damage_reduced_by_threads(self) -> None:
        """A thread-invested character takes less damage than the raw authored amount."""
        damage_type = DamageTypeFactory(name="trap-fire")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=damage_type,
            target=EffectTarget.SELF,
        )
        context = ResolutionContext(character=self.character)

        with patch("world.mechanics.effect_handlers.process_damage_consequences", autospec=True):
            result = apply_effect(effect, context)

        dr = apply_damage_reduction_from_threads(self.character, 10)
        assert result.applied is True
        self.assertEqual(self._health(), 100 - dr)
        self.assertLess(dr, 10)  # threads actually reduced it

    def test_deal_damage_unchanged_without_threads(self) -> None:
        """A character without threads takes the full authored damage (baseline 0, no change)."""
        sheet_no_threads = CharacterSheetFactory()
        character_no_threads = sheet_no_threads.character
        vitals_no_threads = CharacterVitalsFactory(
            character_sheet=sheet_no_threads, health=100, max_health=100
        )
        damage_type = DamageTypeFactory(name="trap-ice")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=15,
            damage_type=damage_type,
            target=EffectTarget.SELF,
        )
        context = ResolutionContext(character=character_no_threads)

        with patch("world.mechanics.effect_handlers.process_damage_consequences", autospec=True):
            apply_effect(effect, context)

        vitals_no_threads.refresh_from_db()
        self.assertEqual(vitals_no_threads.health, 85)  # full 15 deducted


class SituationInstantiatedTrapEntryTest(_TrapSceneMixin, TestCase):
    """A Trap minted by instantiate_situation behaves exactly like a hand-placed one.

    Reuses _TrapSceneMixin's character/vitals/consequence-pool setup, but
    replaces the mixin's TrapFactory-built trap with one minted via
    instantiate_situation from a SituationTrapLink — same pool, same check
    types, same difficulties — so the existing damage assertions apply
    unchanged.
    """

    def setUp(self) -> None:
        super().setUp()
        pool = self.trap.consequence_pool
        detect_check_type = self.trap.detect_check_type
        disarm_check_type = self.trap.disarm_check_type
        self.trap.delete()

        template = SituationTemplateFactory()
        SituationTrapLinkFactory(
            situation_template=template,
            name="Situation Spike Pit",
            consequence_pool=pool,
            detect_check_type=detect_check_type,
            disarm_check_type=disarm_check_type,
            detect_difficulty=20,
            disarm_difficulty=20,
        )

        instantiate_situation(template, self.room)
        self.trap = self.room_profile.traps.get(name="Situation Spike Pit")

    def test_instantiated_trap_fires_on_failed_detection(self) -> None:
        with force_check_outcome(self.failure_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 70
        assert self.sheet in self.trap.detected_by.all()

    def test_instantiated_trap_detection_success_avoids_damage(self) -> None:
        with force_check_outcome(self.success_outcome):
            check_room_traps_on_entry(self.character, self.room)

        assert self._health() == 100
        assert self.sheet in self.trap.detected_by.all()
