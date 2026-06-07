"""End-to-end integration test for the Covenant Rite fire path (#516).

Exercises the full pipeline:
  wire_covenant_rite_content() → build fireable RitualSession → fire_session()
  → CovenantRiteInstance + ConditionInstance buffs at correct severity
  → dramatic late entry rescales all participants
  → cleanup_completed_encounter removes buffs + stamps completed_at
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.combat.constants import EncounterStatus
from world.combat.factories import CombatEncounterFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.services import get_condition_instance
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
    wire_covenant_rite_content,
)
from world.covenants.models import CovenantRiteInstance
from world.covenants.services import evaluate_scene_engagement
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.magic.services.sessions import fire_session
from world.scenes.factories import SceneFactory


def _make_room(key: str = "TestRoom"):
    """Create a Room typeclass instance usable as a combat/scene location."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_character_in_room(character, room) -> None:
    """Set a character's db_location directly and persist."""
    character.db_location = room
    character.save(update_fields=["db_location"])


class CovenantRiteFlowIntegrationTest(TestCase):
    """End-to-end exercise of the Covenant Rite fire path.

    Uses setUp (not setUpTestData) because Evennia typeclasses (ObjectDB subclasses)
    are not deepcopy-safe, which Django's setUpTestData mechanism requires.
    """

    def setUp(self) -> None:
        # ===== Phase 1: Seed content =====
        # wire_covenant_rite_content() is idempotent — returns the CovenantRite.
        self.rite = wire_covenant_rite_content()
        self.ritual = self.rite.ritual

        # ===== Phase 2: Covenant + members =====
        # level=2 set directly (materialized view path not available in tests).
        self.room = _make_room("RiteTestRoom")
        self.covenant = CovenantFactory(
            covenant_type=self.rite.covenant_type,
            level=2,
        )
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)

        # Three engaged members — all in the same covenant.
        self.mem1 = make_engaged_member(
            covenant=self.covenant,
            covenant_role=self.role,
        )
        self.mem2 = make_engaged_member(
            covenant=self.covenant,
            covenant_role=self.role,
        )
        self.mem3 = make_engaged_member(
            covenant=self.covenant,
            covenant_role=self.role,
        )

        # Place mem1 + mem2 in the room; mem3 stays out for now.
        _place_character_in_room(self.mem1.character_sheet.character, self.room)
        _place_character_in_room(self.mem2.character_sheet.character, self.room)

        # ===== Phase 3: Active CombatEncounter with a Scene in the room =====
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.encounter = CombatEncounterFactory(
            room=self.room,
            scene=self.scene,
            status=EncounterStatus.DECLARING,
        )

        # ===== Phase 4: Build a fireable RitualSession =====
        self.session = RitualSession.objects.create(
            ritual=self.ritual,
            initiator=self.mem1.character_sheet,
            proposed_terms="",
            session_kwargs={},
            expires_at=timezone.now() + timedelta(hours=1),
        )
        # Two ACCEPTED participants (the two present members).
        RitualSessionParticipant.objects.create(
            session=self.session,
            character_sheet=self.mem1.character_sheet,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionParticipant.objects.create(
            session=self.session,
            character_sheet=self.mem2.character_sheet,
            state=ParticipantState.ACCEPTED,
        )
        # Session-level COVENANT reference.
        RitualSessionReference.objects.create(
            session=self.session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=self.covenant,
            ref_covenant_role=None,
        )

    # ------------------------------------------------------------------
    # Phase A: Fire
    # ------------------------------------------------------------------

    def test_fire_returns_rite_instance_and_applies_buffs(self) -> None:
        """fire_session dispatches perform_covenant_rite and returns a CovenantRiteInstance."""
        result = fire_session(session=self.session)

        # Assert return type.
        self.assertIsInstance(result, CovenantRiteInstance)

        # The instance is linked to our covenant and encounter.
        self.assertEqual(result.covenant_id, self.covenant.pk)
        self.assertEqual(result.combat_encounter_id, self.encounter.pk)

        # Both present members are participants.
        participant_ids = set(result.participants.values_list("pk", flat=True))
        self.assertIn(self.mem1.character_sheet.pk, participant_ids)
        self.assertIn(self.mem2.character_sheet.pk, participant_ids)
        self.assertEqual(len(participant_ids), 2)

        # Severity for 2 present = base_severity(2) + extras(0) = 2.
        expected_severity = self.rite.severity_for(present_count=2)
        self.assertEqual(expected_severity, 2)

        for mem in (self.mem1, self.mem2):
            ci = get_condition_instance(
                mem.character_sheet.character,
                self.rite.granted_condition,
            )
            self.assertIsNotNone(
                ci,
                f"Expected Oathbound Resolve on {mem.character_sheet}",
            )
            self.assertEqual(
                ci.severity,
                expected_severity,
                f"Expected severity {expected_severity} on {mem.character_sheet}",
            )

        # Third member (not present) has no buff.
        self.assertIsNone(
            get_condition_instance(
                self.mem3.character_sheet.character,
                self.rite.granted_condition,
            )
        )

    # ------------------------------------------------------------------
    # Phase B: Dramatic late entry
    # ------------------------------------------------------------------

    def test_late_entry_rescales_all_participants(self) -> None:
        """Moving the 3rd member into the room rescales all buffs from 2 → 3."""
        fire_session(session=self.session)

        # Now move the 3rd member in and call evaluate_scene_engagement.
        _place_character_in_room(self.mem3.character_sheet.character, self.room)
        evaluate_scene_engagement(
            character_sheet=self.mem3.character_sheet,
            room=self.room,
        )

        # Severity for 3 present = 2 + (3 - 2) * 1 = 3.
        expected_severity = self.rite.severity_for(present_count=3)
        self.assertEqual(expected_severity, 3)

        # All three members now have the buff at severity 3.
        for mem in (self.mem1, self.mem2, self.mem3):
            ci = get_condition_instance(
                mem.character_sheet.character,
                self.rite.granted_condition,
            )
            self.assertIsNotNone(
                ci,
                f"Expected Oathbound Resolve on {mem.character_sheet} after late entry",
            )
            self.assertEqual(
                ci.severity,
                expected_severity,
                f"Expected severity {expected_severity} on {mem.character_sheet} after late entry",
            )

    # ------------------------------------------------------------------
    # Phase C: Combat-end sweep
    # ------------------------------------------------------------------

    def test_combat_end_removes_all_buffs_and_stamps_completed_at(self) -> None:
        """cleanup_completed_encounter removes buffs and stamps completed_at."""
        fire_session(session=self.session)

        # Late entry so all three have the buff.
        _place_character_in_room(self.mem3.character_sheet.character, self.room)
        evaluate_scene_engagement(
            character_sheet=self.mem3.character_sheet,
            room=self.room,
        )

        # Sanity: all three have the condition before cleanup.
        for mem in (self.mem1, self.mem2, self.mem3):
            self.assertIsNotNone(
                get_condition_instance(
                    mem.character_sheet.character,
                    self.rite.granted_condition,
                )
            )

        # Trigger combat-end cleanup.
        cleanup_completed_encounter(self.encounter)

        # All buffs gone.
        for mem in (self.mem1, self.mem2, self.mem3):
            self.assertIsNone(
                get_condition_instance(
                    mem.character_sheet.character,
                    self.rite.granted_condition,
                ),
                f"Expected Oathbound Resolve removed from {mem.character_sheet}",
            )

        # CovenantRiteInstance.completed_at is stamped.
        instance = CovenantRiteInstance.objects.get(
            rite=self.rite,
            covenant=self.covenant,
            combat_encounter=self.encounter,
        )
        self.assertIsNotNone(
            instance.completed_at,
            "Expected CovenantRiteInstance.completed_at to be set after cleanup",
        )
