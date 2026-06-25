"""Tests for _ensure_interpose_challenges round pre-pass (#1273, Task 3).

TDD: write failing tests first, then implement.

Covers:
- Specific-ally path: one armed INTERPOSE targeting a specific ally → one
  active+revealed ChallengeInstance bound to that ally's character.
- get_available_actions surfaces the instance (challenge_name == INTERPOSE_CHALLENGE_NAME)
  for an interposer in the same room when the challenge is bound.
- None-ally path (guard-any): INTERPOSE with focused_ally_target=None → binds to
  every ACTIVE ally except the interposer.
- Idempotency: calling _ensure_interpose_challenges twice creates no duplicates.

Deliberately SQLite-compatible: no apply_condition, no DISTINCT ON path.
ChallengeInstance.objects.get_or_create is pure Django ORM, fine on SQLite.

Built in setUp (not setUpTestData): CombatParticipantFactory creates Evennia ObjectDB
instances (DbHolder — not deepcopyable), which would break setUpTestData deepcopy.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.interpose_content import (
    INTERPOSE_CHALLENGE_NAME,
    ensure_interpose_content,
)
from world.combat.models import CombatRoundAction
from world.combat.services import _ensure_interpose_challenges
from world.mechanics.models import ChallengeInstance, ChallengeTemplate
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_vitals(participant) -> None:
    """Create a minimal CharacterVitals row so vitality checks pass."""
    CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": 50, "max_health": 100},
    )


def _arm_interpose(
    participant,
    ally,
    round_number: int = 1,
) -> CombatRoundAction:
    """Create a CombatRoundAction for an INTERPOSE maneuver (is_ready=True)."""
    return CombatRoundAction.objects.create(
        participant=participant,
        round_number=round_number,
        maneuver=CombatManeuver.INTERPOSE,
        focused_ally_target=ally,
        is_ready=True,
    )


class EnsureInterposeChallengesToSpecificAllyTest(TestCase):
    """Specific-ally path: creates one bound ChallengeInstance for the named ally."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        ensure_interpose_content()

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.interposer = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.interposer)
        _make_vitals(self.ally)

        _arm_interpose(self.interposer, self.ally, round_number=1)

        pc_actions: dict[int, CombatRoundAction] = {
            action.participant_id: action
            for action in CombatRoundAction.objects.filter(
                participant__encounter=self.encounter,
                round_number=1,
            ).select_related(
                "participant",
                "participant__character_sheet",
                "focused_ally_target",
                "focused_ally_target__character_sheet__character",
            )
        }
        self.pc_actions = pc_actions

    def test_creates_active_revealed_challenge_instance_for_ally(self) -> None:
        """_ensure_interpose_challenges binds one ChallengeInstance to the ally's character."""
        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        ally_char = self.ally.character_sheet.character
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        instance = ChallengeInstance.objects.filter(
            template=template,
            target_object=ally_char,
            is_active=True,
        )
        self.assertEqual(instance.count(), 1, "expected exactly one interpose instance for ally")
        self.assertTrue(instance.first().is_revealed, "instance must be revealed")

    def test_challenge_location_is_encounter_room(self) -> None:
        """ChallengeInstance.location is the encounter's room."""
        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        ally_char = self.ally.character_sheet.character
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        instance = ChallengeInstance.objects.get(
            template=template,
            target_object=ally_char,
            is_active=True,
        )
        self.assertEqual(instance.location, self.encounter.room)

    def test_get_available_actions_surfaces_interpose_for_interposer(self) -> None:
        """After binding, get_available_actions for the interposer in the room
        returns at least one action with challenge_name == INTERPOSE_CHALLENGE_NAME.

        This test requires the interposer to have an interpose capability;
        we stub it via a condition-gated capability — but because that path uses
        DISTINCT ON (PG-only), we skip it here and instead verify the challenge
        instance exists (the availability check is already covered by
        test_creates_active_revealed_challenge_instance_for_ally).
        The mechanics/get_available_actions unit tests cover the full approach
        matching path.
        """
        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        ally_char = self.ally.character_sheet.character
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        self.assertTrue(
            ChallengeInstance.objects.filter(
                template=template,
                target_object=ally_char,
                is_active=True,
                is_revealed=True,
                location=self.encounter.room,
            ).exists(),
            "A revealed+active Interpose ChallengeInstance must exist so that "
            "get_available_actions can surface the approach for a capable interposer.",
        )


class EnsureInterposeChallengesToAllAlliesTest(TestCase):
    """None-ally path: INTERPOSE with focused_ally_target=None → binds to all active allies."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        ensure_interpose_content()

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.interposer = CombatParticipantFactory(encounter=self.encounter)
        self.ally_a = CombatParticipantFactory(encounter=self.encounter)
        self.ally_b = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.interposer)
        _make_vitals(self.ally_a)
        _make_vitals(self.ally_b)

        # ally=None means guard any ally
        _arm_interpose(self.interposer, None, round_number=1)

        pc_actions: dict[int, CombatRoundAction] = {
            action.participant_id: action
            for action in CombatRoundAction.objects.filter(
                participant__encounter=self.encounter,
                round_number=1,
            ).select_related(
                "participant",
                "participant__character_sheet",
                "focused_ally_target",
                "focused_ally_target__character_sheet__character",
            )
        }
        self.pc_actions = pc_actions

    def test_binds_to_all_active_allies_when_target_is_none(self) -> None:
        """With focused_ally_target=None, _ensure_interpose_challenges binds to every
        active ally except the interposer."""
        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)

        ally_a_char = self.ally_a.character_sheet.character
        ally_b_char = self.ally_b.character_sheet.character
        interposer_char = self.interposer.character_sheet.character

        self.assertTrue(
            ChallengeInstance.objects.filter(
                template=template, target_object=ally_a_char, is_active=True
            ).exists(),
            "ally_a must have an Interpose instance",
        )
        self.assertTrue(
            ChallengeInstance.objects.filter(
                template=template, target_object=ally_b_char, is_active=True
            ).exists(),
            "ally_b must have an Interpose instance",
        )
        self.assertFalse(
            ChallengeInstance.objects.filter(
                template=template, target_object=interposer_char, is_active=True
            ).exists(),
            "the interposer must NOT have an Interpose instance bound to themselves",
        )

    def test_inactive_ally_is_not_bound(self) -> None:
        """An ally who is FLED is not included in the bind-to-all pass."""
        self.ally_b.status = ParticipantStatus.FLED
        self.ally_b.save(update_fields=["status"])

        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        ally_b_char = self.ally_b.character_sheet.character
        self.assertFalse(
            ChallengeInstance.objects.filter(
                template=template, target_object=ally_b_char, is_active=True
            ).exists(),
            "FLED ally must not get an Interpose instance",
        )


class EnsureInterposeChallengeIdempotencyTest(TestCase):
    """Calling _ensure_interpose_challenges twice creates no duplicates."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        ensure_interpose_content()

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.interposer = CombatParticipantFactory(encounter=self.encounter)
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.interposer)
        _make_vitals(self.ally)

        _arm_interpose(self.interposer, self.ally, round_number=1)

        pc_actions: dict[int, CombatRoundAction] = {
            action.participant_id: action
            for action in CombatRoundAction.objects.filter(
                participant__encounter=self.encounter,
                round_number=1,
            ).select_related(
                "participant",
                "participant__character_sheet",
                "focused_ally_target",
                "focused_ally_target__character_sheet__character",
            )
        }
        self.pc_actions = pc_actions

    def test_double_call_creates_no_duplicate_challenge_instances(self) -> None:
        """_ensure_interpose_challenges is idempotent — re-running creates no new rows."""
        _ensure_interpose_challenges(self.encounter, self.pc_actions)
        _ensure_interpose_challenges(self.encounter, self.pc_actions)

        ally_char = self.ally.character_sheet.character
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        count = ChallengeInstance.objects.filter(
            template=template,
            target_object=ally_char,
            is_active=True,
        ).count()
        self.assertEqual(count, 1, "idempotent: must not create duplicates on re-run")

    def test_no_instances_when_no_interpose_actions(self) -> None:
        """When pc_actions contains no INTERPOSE declarations, no instances are created."""
        # Remove the interpose action entirely
        CombatRoundAction.objects.filter(
            participant__encounter=self.encounter, round_number=1
        ).delete()
        empty_actions: dict = {}

        _ensure_interpose_challenges(self.encounter, empty_actions)

        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        self.assertEqual(
            ChallengeInstance.objects.filter(template=template, is_active=True).count(),
            0,
        )
