"""Sent Flying tests (#2638) — the plummet-pattern's first "in-flight" clone.

Covers: content seeding sanity; the trigger applies the marker + stamps the
damage carrier; the mid-air catch (armed guardian INTERPOSE fires, no impact,
budget consumed); an unanswered marker's hard-landing impact at
SENT_FLYING_IMPACT_FRACTION; the plummet chain when the victim's room has a
CHASM position; sends_flying=False never triggers anything.

Some tests are tagged ``postgres`` — anywhere the real ``apply_condition``
pipeline runs (the marker's own application, or a plummet-chain handoff into
``begin_plummet``/Plummeting) hits the same PG-only DISTINCT ON as the
existing plummet/interpose test suites (see ``test_plummet_begin.py``,
``test_guardian_reactions.py``). Everything else — the catch-seam budget
logic, the unanswered-impact resolution, and the sends_flying=False guard —
builds its marker directly via ``ConditionInstanceFactory`` (bypassing
``apply_condition``) and runs on the SQLite fast tier.

Built in setUp (not setUpTestData): factories create Evennia ObjectDB
instances (DbHolder — not deepcopyable), which would break setUpTestData's
deepcopy.
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.areas.positioning.constants import PLUMMETING_CONDITION_NAME, PositionKind
from world.areas.positioning.factories import wire_fall_triggers
from world.areas.positioning.models import Position
from world.areas.positioning.plummet_content import ensure_fall_content
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import SENT_FLYING_IMPACT_FRACTION, CombatManeuver
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatParticipant
from world.combat.sent_flying_content import (
    SENT_FLYING_CONDITION_NAME,
    SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME,
    ensure_sent_flying_content,
)
from world.combat.services import (
    _resolve_sent_flying_markers,
    _trigger_sent_flying,
    _try_catch_sent_flying,
    resolve_round,
)
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import (
    ConditionCategory,
    ConditionInstance,
    ConditionTemplate,
    DamageType,
)
from world.conditions.services import get_active_conditions
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_vitals(participant: CombatParticipant, *, health: int = 1000, max_health: int = 1000):
    return CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=health, max_health=max_health
    )


# ---------------------------------------------------------------------------
# Content seeding
# ---------------------------------------------------------------------------


class SentFlyingContentTests(TestCase):
    def test_seeds_impact_damage_type(self) -> None:
        ensure_sent_flying_content()
        dt = DamageType.objects.get(name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME)
        self.assertIsNone(dt.wound_pool)
        self.assertIsNone(dt.death_pool)

    def test_reuses_plummeting_falling_category(self) -> None:
        ensure_fall_content()
        ensure_sent_flying_content()
        tmpl = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
        plummeting = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        self.assertEqual(tmpl.category_id, plummeting.category_id)
        self.assertEqual(ConditionCategory.objects.filter(name="Falling").count(), 1)

    def test_marker_is_non_progressive_non_stackable_permanent(self) -> None:
        ensure_sent_flying_content()
        tmpl = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
        self.assertFalse(tmpl.has_progression)
        self.assertFalse(tmpl.is_stackable)
        self.assertEqual(tmpl.default_duration_type, DurationType.PERMANENT)

    def test_is_idempotent(self) -> None:
        ensure_sent_flying_content()
        ensure_sent_flying_content()
        self.assertEqual(
            DamageType.objects.filter(name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME).count(), 1
        )
        self.assertEqual(
            ConditionTemplate.objects.filter(name=SENT_FLYING_CONDITION_NAME).count(), 1
        )


# ---------------------------------------------------------------------------
# Trigger: applies the marker + stamps the damage carrier
# ---------------------------------------------------------------------------


@tag("postgres")  # apply_condition (marker application) uses DISTINCT ON (PG-only)
class SentFlyingTriggerTests(TestCase):
    def setUp(self) -> None:
        ensure_sent_flying_content()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        _make_vitals(self.participant)
        self.entry = ThreatPoolEntryFactory(sends_flying=True, base_damage=40)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.npc_action = CombatOpponentActionFactory(
            opponent=self.opponent, round_number=1, threat_entry=self.entry
        )

    def test_trigger_applies_marker_and_stamps_damage(self) -> None:
        _trigger_sent_flying(self.participant, self.npc_action, 40)

        character = self.participant.character_sheet.character
        self.assertTrue(
            get_active_conditions(character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists()
        )
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.sent_flying_damage, 40)

    def test_trigger_with_no_armed_guardian_leaves_marker_unanswered(self) -> None:
        _trigger_sent_flying(self.participant, self.npc_action, 40)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.sent_flying_damage, 40)
        character = self.participant.character_sheet.character
        self.assertTrue(
            get_active_conditions(character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists()
        )

    def test_trigger_with_armed_guardian_catches_and_clears_marker(self) -> None:
        guardian_sheet = CharacterSheetFactory()
        guardian_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=guardian_sheet
        )
        CombatRoundActionFactory(
            participant=guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
            focused_ally_target=self.participant,
        )

        _trigger_sent_flying(self.participant, self.npc_action, 40)

        self.participant.refresh_from_db()
        self.assertEqual(
            self.participant.sent_flying_damage, 0, "a caught marker must clear its carrier"
        )
        character = self.participant.character_sheet.character
        self.assertFalse(
            get_active_conditions(character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists(),
            "a caught marker must be removed",
        )
        guardian_participant.refresh_from_db()
        self.assertEqual(
            guardian_participant.reactions_used, 1, "the catch must spend the guardian's reaction"
        )


# ---------------------------------------------------------------------------
# The catch seam: budget-gated, no skill roll
# ---------------------------------------------------------------------------


class SentFlyingCatchSeamTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        sheet = CharacterSheetFactory()
        self.victim = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)

    def _guardian(self, *, focused_ally_target=None, is_ready: bool = True) -> CombatParticipant:
        guardian_sheet = CharacterSheetFactory()
        guardian = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=guardian_sheet
        )
        CombatRoundActionFactory(
            participant=guardian,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=is_ready,
            focused_ally_target=focused_ally_target,
        )
        return guardian

    def test_no_armed_guardian_returns_none(self) -> None:
        self.assertIsNone(_try_catch_sent_flying(self.victim))

    def test_specific_guard_catches(self) -> None:
        guardian = self._guardian(focused_ally_target=self.victim)

        caught_by = _try_catch_sent_flying(self.victim)

        self.assertEqual(caught_by, guardian.character_sheet.character)
        guardian.refresh_from_db()
        self.assertEqual(guardian.reactions_used, 1)

    def test_guard_anyone_catches(self) -> None:
        guardian = self._guardian(focused_ally_target=None)

        caught_by = _try_catch_sent_flying(self.victim)

        self.assertEqual(caught_by, guardian.character_sheet.character)

    def test_guarding_a_different_ally_does_not_catch(self) -> None:
        other_sheet = CharacterSheetFactory()
        other = CombatParticipantFactory(encounter=self.encounter, character_sheet=other_sheet)
        self._guardian(focused_ally_target=other)

        self.assertIsNone(_try_catch_sent_flying(self.victim))

    def test_self_interpose_cannot_catch_self(self) -> None:
        CombatRoundActionFactory(
            participant=self.victim,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
            focused_ally_target=None,
        )

        self.assertIsNone(_try_catch_sent_flying(self.victim))

    def test_budget_exhausted_guardian_does_not_catch(self) -> None:
        from world.combat.constants import REACTIONS_PER_ROUND

        guardian = self._guardian(focused_ally_target=self.victim)
        guardian.reactions_used = REACTIONS_PER_ROUND
        guardian.save(update_fields=["reactions_used"])

        self.assertIsNone(_try_catch_sent_flying(self.victim))

    def test_outside_resolving_status_returns_none(self) -> None:
        self._guardian(focused_ally_target=self.victim)
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.save(update_fields=["status"])

        self.assertIsNone(_try_catch_sent_flying(self.victim))


# ---------------------------------------------------------------------------
# Explicit resolution: unanswered impact + plummet chain
# ---------------------------------------------------------------------------


class SentFlyingUnansweredImpactTests(TestCase):
    def setUp(self) -> None:
        ensure_sent_flying_content()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        _make_vitals(self.participant, health=1000, max_health=1000)
        self.template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
        self.character = self.participant.character_sheet.character
        # Built directly (not via apply_condition): SQLite-safe, and this is
        # exactly the state _trigger_sent_flying leaves behind on a hit.
        ConditionInstanceFactory(target=self.character, condition=self.template)
        self.participant.sent_flying_damage = 40
        self.participant.save(update_fields=["sent_flying_damage"])

    def test_unanswered_marker_debits_impact_fraction(self) -> None:
        _resolve_sent_flying_markers(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.participant.character_sheet)
        expected_impact = int(40 * SENT_FLYING_IMPACT_FRACTION)
        self.assertEqual(vitals.health, 1000 - expected_impact)

    def test_resolution_clears_marker_and_carrier(self) -> None:
        _resolve_sent_flying_markers(self.encounter)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.sent_flying_damage, 0)
        self.assertFalse(
            get_active_conditions(self.character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists()
        )

    def test_no_marked_participants_is_a_noop(self) -> None:
        self.participant.sent_flying_damage = 0
        self.participant.save(update_fields=["sent_flying_damage"])

        # Must not raise even with no work to do.
        _resolve_sent_flying_markers(self.encounter)

    def test_already_cleared_marker_just_resets_stale_carrier(self) -> None:
        # Simulate a marker already removed by some other path while the
        # carrier field is still stale (defensive robustness).
        ConditionInstance.objects.filter(target=self.character, condition=self.template).delete()

        _resolve_sent_flying_markers(self.encounter)

        vitals = CharacterVitals.objects.get(character_sheet=self.participant.character_sheet)
        self.assertEqual(vitals.health, 1000, "no impact should apply to an already-cleared marker")
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.sent_flying_damage, 0)


@tag("postgres")  # begin_plummet -> apply_condition uses DISTINCT ON (PG-only)
class SentFlyingPlummetChainTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        ensure_fall_content()
        ensure_sent_flying_content()
        wire_fall_triggers()

        self.room = create_object("typeclasses.rooms.Room", key="SentFlyingRoom", nohome=True)
        self.chasm = Position.objects.create(
            room=self.room, name="the pit", kind=PositionKind.CHASM
        )

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.RESOLVING, round_number=1, room=self.room
        )
        sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        _make_vitals(self.participant)
        self.character = self.participant.character_sheet.character
        self.character.db_location = self.room
        self.character.save(update_fields=["db_location"])

        # A bystander so begin_plummet rides the attended (multi-round) path.
        bystander_sheet = CharacterSheetFactory()
        self.bystander = bystander_sheet.character
        self.bystander.db_location = self.room
        self.bystander.save(update_fields=["db_location"])

        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
        ConditionInstanceFactory(target=self.character, condition=template)
        self.participant.sent_flying_damage = 40
        self.participant.save(update_fields=["sent_flying_damage"])

    def test_chasm_room_launches_a_plummet_instead_of_local_impact(self) -> None:
        _resolve_sent_flying_markers(self.encounter)

        self.assertTrue(
            get_active_conditions(self.character)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
            "the victim should now be plummeting, not merely impacted locally",
        )
        self.assertFalse(
            get_active_conditions(self.character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists(),
            "the Sent Flying marker must be cleared once the plummet chain begins",
        )


# ---------------------------------------------------------------------------
# sends_flying=False never triggers anything
# ---------------------------------------------------------------------------


class SendsFlyingFalseNeverTriggersTests(TestCase):
    def test_normal_attack_never_applies_the_marker(self) -> None:
        ensure_sent_flying_content()
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        entry = ThreatPoolEntryFactory(sends_flying=False, base_damage=40, weight=100)
        opponent = CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        _make_vitals(participant)
        action = CombatOpponentActionFactory(opponent=opponent, round_number=1, threat_entry=entry)
        action.targets.set([participant])

        resolve_round(encounter)

        character = participant.character_sheet.character
        self.assertFalse(
            get_active_conditions(character)
            .filter(condition__name=SENT_FLYING_CONDITION_NAME)
            .exists()
        )
        participant.refresh_from_db()
        self.assertEqual(participant.sent_flying_damage, 0)
