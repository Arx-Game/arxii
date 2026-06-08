"""Tests for Tasks 3 + 4: covenant_members_present helper and perform_covenant_rite service.
Tests for Task 5: fold_arrival_into_active_rites (late-arrival fold-in).
Tests for Task 6: complete_rites_for_encounter (combat-end buff sweep).
Tests for Tasks 6-9: CovenantRiteParticipant through model — role-aware fire, late-join,
and per-participant sweep.

Uses setUp (not setUpTestData) because Evennia typeclasses (ObjectDB subclasses)
are not deepcopy-safe, which Django's setUpTestData mechanism requires.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.covenants.constants import RoleArchetype
from world.covenants.factories import (
    CharacterSheetFactory,
    CovenantFactory,
    CovenantRiteFactory,
    CovenantRiteRolePackageFactory,
    CovenantRoleFactory,
    make_engaged_member,
)
from world.covenants.models import CovenantRite, CovenantRiteInstance
from world.covenants.services import (
    complete_rites_for_encounter,
    covenant_members_present,
    evaluate_scene_engagement,
    fold_arrival_into_active_rites,
    perform_covenant_rite,
)


def _make_room(key: str = "TestRoom"):
    """Create a Room typeclass instance usable as a combat/scene location."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_character_in_room(character, room) -> None:
    """Set a character's db_location directly."""
    character.db_location = room
    character.save(update_fields=["db_location"])


def _make_rite(*, covenant, ritual, condition_template) -> CovenantRite:
    """Create a CovenantRite with sensible defaults for testing."""
    return CovenantRite.objects.create(
        ritual=ritual,
        covenant_type=covenant.covenant_type,
        min_covenant_level=1,
        min_members_present=2,
        granted_condition=condition_template,
        base_severity=2,
        severity_per_extra_participant=1,
        max_severity=None,
        duration_rounds=3,
    )


def _make_active_encounter(room, scene):
    """Create a CombatEncounter in RESOLVING status for the given room and scene."""
    from world.combat.constants import EncounterStatus
    from world.combat.factories import CombatEncounterFactory
    from world.combat.models import CombatEncounter

    encounter = CombatEncounterFactory(room=room, scene=scene)
    CombatEncounter.objects.filter(pk=encounter.pk).update(status=EncounterStatus.RESOLVING)
    encounter.refresh_from_db()
    return encounter


class _RiteSceneTestCase(TestCase):
    """Shared setUp for tests that need: room, covenant, role, 2 engaged members,
    a condition template, a ritual+rite, an active CombatEncounter, and a RitualSession
    with a COVENANT reference.

    Subclasses may override or extend setUp; all common objects are available as
    self.room, self.covenant, self.role, self.mem_a, self.mem_b,
    self.condition_template, self.ritual, self.rite, self.scene,
    self.encounter, self.session.
    """

    _room_key: str = "BaseRiteRoom"
    _covenant_level: int = 3

    def setUp(self) -> None:
        from world.covenants.constants import CovenantType
        from world.magic.constants import ReferenceKind
        from world.magic.factories import RitualFactory, RitualSessionFactory
        from world.magic.models.sessions import RitualSessionReference
        from world.scenes.factories import SceneFactory

        self.room = _make_room(self._room_key)
        self.covenant = CovenantFactory(
            covenant_type=CovenantType.DURANCE, level=self._covenant_level
        )
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

        self.mem_a = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        self.mem_b = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        _place_character_in_room(self.mem_a.character_sheet.character, self.room)
        _place_character_in_room(self.mem_b.character_sheet.character, self.room)

        self.condition_template = ConditionTemplateFactory()
        self.ritual = RitualFactory(
            service_function_path="world.covenants.services.perform_covenant_rite"
        )
        self.rite = _make_rite(
            covenant=self.covenant,
            ritual=self.ritual,
            condition_template=self.condition_template,
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        self.encounter = _make_active_encounter(room=self.room, scene=self.scene)

        self.session = RitualSessionFactory(
            ritual=self.ritual,
            initiator=self.mem_a.character_sheet,
        )
        RitualSessionReference.objects.create(
            session=self.session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=self.covenant,
            ref_covenant_role=None,
        )


class CovenantMembersPresentTests(TestCase):
    """Unit tests for the covenant_members_present helper."""

    def setUp(self) -> None:
        from world.covenants.constants import CovenantType

        self.room = _make_room("PresentRoom")
        self.other_room = _make_room("OtherRoom")
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

    def test_returns_engaged_members_in_room(self) -> None:
        """Engaged (active) members in the room appear in results."""
        mem_a = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        mem_b = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        _place_character_in_room(mem_a.character_sheet.character, self.room)
        _place_character_in_room(mem_b.character_sheet.character, self.room)

        result = covenant_members_present(covenant=self.covenant, room=self.room)

        sheet_ids = {s.pk for s in result}
        self.assertIn(mem_a.character_sheet.pk, sheet_ids)
        self.assertIn(mem_b.character_sheet.pk, sheet_ids)
        self.assertEqual(len(result), 2)

    def test_includes_non_engaged_active_member_in_room(self) -> None:
        """A non-engaged but active member present in the room is now included."""
        from world.covenants.factories import CharacterCovenantRoleFactory

        engaged = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        non_engaged_ccr = CharacterCovenantRoleFactory(
            covenant=self.covenant, covenant_role=self.role, engaged=False, left_at=None
        )
        _place_character_in_room(engaged.character_sheet.character, self.room)
        _place_character_in_room(non_engaged_ccr.character_sheet.character, self.room)

        result = covenant_members_present(covenant=self.covenant, room=self.room)

        sheet_ids = {s.pk for s in result}
        self.assertIn(engaged.character_sheet.pk, sheet_ids)
        self.assertIn(non_engaged_ccr.character_sheet.pk, sheet_ids)

    def test_excludes_active_member_in_different_room(self) -> None:
        """An active member who is in a different room is excluded."""
        in_room = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        elsewhere = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        _place_character_in_room(in_room.character_sheet.character, self.room)
        _place_character_in_room(elsewhere.character_sheet.character, self.other_room)

        result = covenant_members_present(covenant=self.covenant, room=self.room)

        sheet_ids = {s.pk for s in result}
        self.assertIn(in_room.character_sheet.pk, sheet_ids)
        self.assertNotIn(elsewhere.character_sheet.pk, sheet_ids)

    def test_empty_room_returns_empty_list(self) -> None:
        """No one in the room means an empty list."""
        make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        result = covenant_members_present(covenant=self.covenant, room=self.room)
        self.assertEqual(result, [])


class PerformCovenantRiteHappyPathTests(_RiteSceneTestCase):
    """Happy-path tests for perform_covenant_rite."""

    _room_key = "RiteRoom"

    def setUp(self) -> None:
        super().setUp()

        # Add a third engaged member in the room (beyond the two from base setUp).
        self.mem_c = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

    def test_returns_rite_instance(self) -> None:
        """Happy path: returns a CovenantRiteInstance."""
        result = perform_covenant_rite(session=self.session)
        self.assertIsInstance(result, CovenantRiteInstance)

    def test_instance_linked_to_covenant_and_encounter(self) -> None:
        """The created instance is linked to the correct covenant and encounter."""
        result = perform_covenant_rite(session=self.session)
        self.assertEqual(result.covenant_id, self.covenant.pk)
        self.assertEqual(result.combat_encounter_id, self.encounter.pk)

    def test_participants_set_to_all_three_present(self) -> None:
        """All three present engaged members are in the participants M2M."""
        result = perform_covenant_rite(session=self.session)
        participant_ids = set(result.participants.values_list("pk", flat=True))
        self.assertIn(self.mem_a.character_sheet.pk, participant_ids)
        self.assertIn(self.mem_b.character_sheet.pk, participant_ids)
        self.assertIn(self.mem_c.character_sheet.pk, participant_ids)
        self.assertEqual(len(participant_ids), 3)

    def test_condition_applied_to_each_participant(self) -> None:
        """Each present engaged member has a live ConditionInstance for granted_condition."""
        perform_covenant_rite(session=self.session)
        sheets = [
            self.mem_a.character_sheet,
            self.mem_b.character_sheet,
            self.mem_c.character_sheet,
        ]
        for sheet in sheets:
            has_it = ConditionInstance.objects.filter(
                target=sheet.character,
                condition=self.condition_template,
            ).exists()
            self.assertTrue(has_it, f"Expected condition on {sheet}")

    def test_condition_severity_scaled_by_present_count(self) -> None:
        """Condition severity matches rite.severity_for(present_count=3).

        With base_severity=2, severity_per_extra=1, min_members_present=2:
        severity = 2 + (3 - 2) * 1 = 3.
        """
        perform_covenant_rite(session=self.session)
        expected_severity = self.rite.severity_for(present_count=3)  # = 3
        instance = ConditionInstance.objects.filter(
            target=self.mem_a.character_sheet.character,
            condition=self.condition_template,
        ).first()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.severity, expected_severity)

    def test_rite_instance_row_persisted(self) -> None:
        """A CovenantRiteInstance row exists after a successful call."""
        perform_covenant_rite(session=self.session)
        self.assertTrue(
            CovenantRiteInstance.objects.filter(
                rite=self.rite,
                covenant=self.covenant,
                combat_encounter=self.encounter,
            ).exists()
        )


class PerformCovenantRiteGateTests(_RiteSceneTestCase):
    """Gate failure tests: each gate must raise the typed exception and roll back."""

    _room_key = "GateRoom"

    def test_covenant_level_too_low_raises_and_rolls_back(self) -> None:
        """covenant.level < rite.min_covenant_level → CovenantLevelTooLowError, no rows."""
        from world.covenants.exceptions import CovenantLevelTooLowError

        self.covenant.level = 0  # below min_covenant_level=1
        self.covenant.save(update_fields=["level"])

        with self.assertRaises(CovenantLevelTooLowError):
            perform_covenant_rite(session=self.session)

        self.assertFalse(CovenantRiteInstance.objects.filter(rite=self.rite).exists())
        self.assertFalse(
            ConditionInstance.objects.filter(condition=self.condition_template).exists()
        )

    def test_no_active_encounter_raises_and_rolls_back(self) -> None:
        """No active encounter in room → NoActiveBattleError, no rows."""
        from world.combat.constants import EncounterStatus
        from world.combat.models import CombatEncounter
        from world.covenants.exceptions import NoActiveBattleError

        CombatEncounter.objects.filter(pk=self.encounter.pk).update(
            status=EncounterStatus.COMPLETED
        )
        self.encounter.refresh_from_db()

        with self.assertRaises(NoActiveBattleError):
            perform_covenant_rite(session=self.session)

        self.assertFalse(CovenantRiteInstance.objects.filter(rite=self.rite).exists())
        self.assertFalse(
            ConditionInstance.objects.filter(condition=self.condition_template).exists()
        )

    def test_not_enough_members_present_raises_and_rolls_back(self) -> None:
        """Fewer members present than min_members_present → NotEnoughMembersPresentError."""
        from world.covenants.exceptions import NotEnoughMembersPresentError

        # Remove mem_b from the room so only 1 active member is present.
        other_room = _make_room("Elsewhere")
        _place_character_in_room(self.mem_b.character_sheet.character, other_room)

        with self.assertRaises(NotEnoughMembersPresentError):
            perform_covenant_rite(session=self.session)

        self.assertFalse(CovenantRiteInstance.objects.filter(rite=self.rite).exists())
        self.assertFalse(
            ConditionInstance.objects.filter(condition=self.condition_template).exists()
        )

    def test_missing_covenant_ref_raises_and_rolls_back(self) -> None:
        """Session with no COVENANT reference → CovenantRiteError, no rows."""
        from world.covenants.exceptions import CovenantRiteError
        from world.magic.factories import RitualSessionFactory

        # Session without a COVENANT ref.
        bare_session = RitualSessionFactory(
            ritual=self.ritual,
            initiator=self.mem_a.character_sheet,
        )

        with self.assertRaises(CovenantRiteError):
            perform_covenant_rite(session=bare_session)

        self.assertFalse(CovenantRiteInstance.objects.filter(rite=self.rite).exists())


# ---------------------------------------------------------------------------
# Task 5: fold_arrival_into_active_rites
# ---------------------------------------------------------------------------


class FoldArrivalIntoActiveRitesTests(_RiteSceneTestCase):
    """Tests for the late-arrival fold-in service function.

    Rite params: base_severity=2, severity_per_extra_participant=1,
    min_members_present=2 → severity_for(2)=2, severity_for(3)=3.
    """

    _room_key = "FoldRoom"

    def setUp(self) -> None:
        super().setUp()

        # Fire the rite for the two initial members → creates a CovenantRiteInstance.
        self.rite_instance = perform_covenant_rite(session=self.session)
        # Verify baseline: 2 participants, severity=2.
        self.assertEqual(self.rite_instance.participants.count(), 2)
        self.assertEqual(self.rite.severity_for(present_count=2), 2)
        self.assertEqual(self.rite.severity_for(present_count=3), 3)

        # Third engaged member — added but NOT in the room yet.
        self.mem_c = make_engaged_member(covenant=self.covenant, covenant_role=self.role)

    # ------------------------------------------------------------------
    # Test 1: re-scale on arrival
    # ------------------------------------------------------------------

    def test_rescale_on_arrival(self) -> None:
        """Third member arrives → gets buff at severity_for(3); existing two are rescaled up."""
        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

        fold_arrival_into_active_rites(character_sheet=self.mem_c.character_sheet, room=self.room)

        expected_severity = self.rite.severity_for(present_count=3)  # == 3

        # Third member has the buff at new severity.
        inst_c = ConditionInstance.objects.filter(
            target=self.mem_c.character_sheet.character,
            condition=self.condition_template,
        ).first()
        self.assertIsNotNone(inst_c)
        self.assertEqual(inst_c.severity, expected_severity)

        # Original two participants were rescaled.
        for member in (self.mem_a, self.mem_b):
            inst = ConditionInstance.objects.filter(
                target=member.character_sheet.character,
                condition=self.condition_template,
            ).first()
            self.assertIsNotNone(inst, f"Expected live condition on {member.character_sheet}")
            self.assertEqual(
                inst.severity,
                expected_severity,
                f"Expected severity {expected_severity} on {member.character_sheet},"
                f" got {inst.severity}",
            )

    # ------------------------------------------------------------------
    # Test 2: already a participant — no-op
    # ------------------------------------------------------------------

    def test_already_participant_is_noop(self) -> None:
        """Calling fold-in for a member already in participants is a no-op."""
        # mem_a is already a participant; call fold-in for them again.
        _place_character_in_room(self.mem_a.character_sheet.character, self.room)

        fold_arrival_into_active_rites(character_sheet=self.mem_a.character_sheet, room=self.room)

        # Participant count should still be 2 (no third was added).
        self.rite_instance.refresh_from_db()
        self.assertEqual(self.rite_instance.participants.count(), 2)

        # Severity of mem_a's buff unchanged (still 2).
        inst = ConditionInstance.objects.filter(
            target=self.mem_a.character_sheet.character,
            condition=self.condition_template,
        ).first()
        self.assertIsNotNone(inst)
        self.assertEqual(inst.severity, self.rite.severity_for(present_count=2))

    # ------------------------------------------------------------------
    # Test 3: non-member ignored
    # ------------------------------------------------------------------

    def test_non_member_ignored(self) -> None:
        """A character not engaged with the covenant gets no buff and does not change count."""
        outsider_sheet = CharacterSheetFactory()
        _place_character_in_room(outsider_sheet.character, self.room)

        fold_arrival_into_active_rites(character_sheet=outsider_sheet, room=self.room)

        # No condition applied to outsider.
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=outsider_sheet.character,
                condition=self.condition_template,
            ).exists()
        )
        # Participant count unchanged.
        self.rite_instance.refresh_from_db()
        self.assertEqual(self.rite_instance.participants.count(), 2)

    # ------------------------------------------------------------------
    # Test 4: completed instance ignored
    # ------------------------------------------------------------------

    def test_completed_instance_ignored(self) -> None:
        """If the instance's encounter is COMPLETED, arriving member is ignored."""
        from world.combat.constants import EncounterStatus
        from world.combat.models import CombatEncounter

        CombatEncounter.objects.filter(pk=self.encounter.pk).update(
            status=EncounterStatus.COMPLETED
        )
        self.encounter.refresh_from_db()

        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

        fold_arrival_into_active_rites(character_sheet=self.mem_c.character_sheet, room=self.room)

        # mem_c should NOT have the condition.
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.mem_c.character_sheet.character,
                condition=self.condition_template,
            ).exists()
        )
        # Participant count unchanged.
        self.rite_instance.refresh_from_db()
        self.assertEqual(self.rite_instance.participants.count(), 2)

    # ------------------------------------------------------------------
    # Test 5: ratchet-only (severity never lowered)
    # ------------------------------------------------------------------

    def test_ratchet_only(self) -> None:
        """Fold-in for a new member never lowers an existing participant's severity.

        Scenario: fold in the 3rd → severity becomes 3. Then fold in a 4th
        (which would push it to 4). The check is only that after both operations
        no participant's severity is lower than severity_for(3).
        """
        _place_character_in_room(self.mem_c.character_sheet.character, self.room)
        fold_arrival_into_active_rites(character_sheet=self.mem_c.character_sheet, room=self.room)
        # After 3rd member: severity_for(3) = 3.
        sev_after_3 = self.rite.severity_for(present_count=3)

        mem_d = make_engaged_member(covenant=self.covenant, covenant_role=self.role)
        _place_character_in_room(mem_d.character_sheet.character, self.room)
        fold_arrival_into_active_rites(character_sheet=mem_d.character_sheet, room=self.room)
        # After 4th member: severity_for(4) = 4.
        sev_after_4 = self.rite.severity_for(present_count=4)

        for member in (self.mem_a, self.mem_b, self.mem_c, mem_d):
            inst = ConditionInstance.objects.filter(
                target=member.character_sheet.character,
                condition=self.condition_template,
            ).first()
            self.assertIsNotNone(inst)
            self.assertGreaterEqual(
                inst.severity,
                sev_after_3,
                f"{member.character_sheet} severity should not be below {sev_after_3}",
            )
        # Final check: everyone is at sev_after_4.
        for member in (self.mem_a, self.mem_b, self.mem_c, mem_d):
            inst = ConditionInstance.objects.get(
                target=member.character_sheet.character,
                condition=self.condition_template,
            )
            self.assertEqual(inst.severity, sev_after_4)

    # ------------------------------------------------------------------
    # Test 6: wiring — evaluate_scene_engagement triggers fold-in
    # ------------------------------------------------------------------

    def test_evaluate_scene_engagement_triggers_fold_in(self) -> None:
        """evaluate_scene_engagement wiring: arriving engaged member gets folded in."""
        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

        evaluate_scene_engagement(character_sheet=self.mem_c.character_sheet, room=self.room)

        expected_severity = self.rite.severity_for(present_count=3)
        inst = ConditionInstance.objects.filter(
            target=self.mem_c.character_sheet.character,
            condition=self.condition_template,
        ).first()
        self.assertIsNotNone(inst, "Expected fold-in buff on arriving member")
        self.assertEqual(inst.severity, expected_severity)


# ---------------------------------------------------------------------------
# Task 6: complete_rites_for_encounter
# ---------------------------------------------------------------------------


class CompleteRitesForEncounterTests(_RiteSceneTestCase):
    """Tests for complete_rites_for_encounter (combat-end buff sweep).

    Uses the same fixture pattern as FoldArrivalIntoActiveRitesTests:
    2 initial engaged members fire the rite, producing 2 ConditionInstance rows.
    """

    _room_key = "SweepRoom"

    def setUp(self) -> None:
        super().setUp()

        # Fire the rite for the two members.
        self.rite_instance = perform_covenant_rite(session=self.session)
        # Sanity: both have the buff.
        for mem in (self.mem_a, self.mem_b):
            self.assertTrue(
                ConditionInstance.objects.filter(
                    target=mem.character_sheet.character,
                    condition=self.condition_template,
                ).exists(),
                f"setUp: expected condition on {mem.character_sheet}",
            )

    # ------------------------------------------------------------------
    # Test 1: sweep on completion
    # ------------------------------------------------------------------

    def test_sweep_removes_buffs_and_stamps_completed_at(self) -> None:
        """complete_rites_for_encounter removes the buff from all participants
        and sets completed_at on the instance.
        """
        from world.conditions.services import get_condition_instance

        complete_rites_for_encounter(encounter=self.encounter)

        self.rite_instance.refresh_from_db()
        self.assertIsNotNone(
            self.rite_instance.completed_at,
            "completed_at should be stamped after sweep",
        )
        for mem in (self.mem_a, self.mem_b):
            live = get_condition_instance(mem.character_sheet.character, self.condition_template)
            self.assertIsNone(
                live,
                f"Expected buff removed from {mem.character_sheet} after combat end",
            )

    # ------------------------------------------------------------------
    # Test 2: idempotent
    # ------------------------------------------------------------------

    def test_idempotent_double_call(self) -> None:
        """Calling complete_rites_for_encounter twice does not error;
        completed_at remains set and the second call is a true no-op.
        """
        complete_rites_for_encounter(encounter=self.encounter)
        self.rite_instance.refresh_from_db()
        first_completed_at = self.rite_instance.completed_at

        # Second call should not raise and should leave completed_at unchanged.
        complete_rites_for_encounter(encounter=self.encounter)
        self.rite_instance.refresh_from_db()
        self.assertEqual(
            self.rite_instance.completed_at,
            first_completed_at,
            "completed_at should not change on second call",
        )

    # ------------------------------------------------------------------
    # Test 3: integration via cleanup_completed_encounter
    # ------------------------------------------------------------------

    def test_cleanup_completed_encounter_sweeps_rite_buffs(self) -> None:
        """cleanup_completed_encounter wires to complete_rites_for_encounter:
        calling it stamps completed_at and removes buffs from participants.
        """
        from world.combat.services import cleanup_completed_encounter
        from world.conditions.services import get_condition_instance

        cleanup_completed_encounter(self.encounter)

        self.rite_instance.refresh_from_db()
        self.assertIsNotNone(
            self.rite_instance.completed_at,
            "completed_at should be stamped after cleanup_completed_encounter",
        )
        for mem in (self.mem_a, self.mem_b):
            live = get_condition_instance(mem.character_sheet.character, self.condition_template)
            self.assertIsNone(
                live,
                f"Expected buff removed from {mem.character_sheet} after cleanup",
            )


# ---------------------------------------------------------------------------
# Task 5 (new model): CovenantRiteRolePackage + package_for
# ---------------------------------------------------------------------------


class CovenantRiteRolePackageTests(TestCase):
    """Unit tests for CovenantRiteRolePackage and CovenantRite.package_for."""

    def setUp(self) -> None:
        # Minimal rite; granted_condition acts as the fallback.
        self.rite = CovenantRiteFactory()

    def test_package_for_selects_highest_band_and_falls_back(self) -> None:
        """package_for returns the highest matching band or falls back to granted_condition."""
        sword = CovenantRoleFactory(
            name="Sword", slug="sword-pkg-test", archetype=RoleArchetype.SWORD
        )
        low = ConditionTemplateFactory(name="fury_i")
        high = ConditionTemplateFactory(name="fury_ii")
        CovenantRiteRolePackageFactory(
            rite=self.rite, covenant_role=sword, min_covenant_level=1, condition_template=low
        )
        CovenantRiteRolePackageFactory(
            rite=self.rite, covenant_role=sword, min_covenant_level=4, condition_template=high
        )

        self.assertEqual(self.rite.package_for(sword, 1), low)  # exactly the low band
        self.assertEqual(self.rite.package_for(sword, 5), high)  # highest band <= level
        # Below lowest band → fallback to granted_condition.
        self.assertEqual(self.rite.package_for(sword, 0), self.rite.granted_condition)
        # Unmapped role → fallback to granted_condition.
        other = CovenantRoleFactory(
            name="Crown", slug="crown-pkg-test", archetype=RoleArchetype.CROWN
        )
        self.assertEqual(self.rite.package_for(other, 5), self.rite.granted_condition)


# ---------------------------------------------------------------------------
# Tasks 6-9: per-participant CovenantRiteParticipant through model
# ---------------------------------------------------------------------------


class _RiteTwoRoleTestCase(_RiteSceneTestCase):
    """Extends _RiteSceneTestCase with a second role + role-specific packages.

    self.role_a / self.mem_a get condition_a.
    self.role_b / self.mem_b get condition_b.
    Both are authored as CovenantRiteRolePackage rows on self.rite.
    """

    _room_key = "TwoRoleRoom"

    def setUp(self) -> None:
        from world.covenants.constants import CovenantType

        # Run base setUp (creates self.role, self.mem_a, self.mem_b with same role).
        super().setUp()

        # Replace mem_b with a member that has a DIFFERENT role.
        self.role_a = self.role  # alias for clarity
        self.role_b = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
            archetype=RoleArchetype.SHIELD,
            name="TwoRole-Shield",
            slug="tworole-shield",
        )

        # Re-assign mem_b to role_b (close old membership, create new one).
        from world.covenants.services import change_role

        self.mem_b = change_role(membership=self.mem_b, new_role=self.role_b)

        # Re-engage mem_b after role change (change_role closes the old row, opens new one).
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=self.mem_b)

        # Author role-specific packages on the rite.
        self.condition_a = ConditionTemplateFactory(name="fury_role_a")
        self.condition_b = ConditionTemplateFactory(name="fury_role_b")
        CovenantRiteRolePackageFactory(
            rite=self.rite,
            covenant_role=self.role_a,
            min_covenant_level=1,
            condition_template=self.condition_a,
        )
        CovenantRiteRolePackageFactory(
            rite=self.rite,
            covenant_role=self.role_b,
            min_covenant_level=1,
            condition_template=self.condition_b,
        )


class RoleAwareFireTests(_RiteTwoRoleTestCase):
    """Task 7: fire path assigns role-specific packages per participant."""

    def test_fire_assigns_different_conditions_by_role(self) -> None:
        """Two members of different roles receive different recorded granted_condition."""
        result = perform_covenant_rite(session=self.session)

        rec_a = result.participant_records.filter(
            character_sheet=self.mem_a.character_sheet
        ).first()
        rec_b = result.participant_records.filter(
            character_sheet=self.mem_b.character_sheet
        ).first()

        self.assertIsNotNone(rec_a, "Expected participant record for mem_a")
        self.assertIsNotNone(rec_b, "Expected participant record for mem_b")
        self.assertEqual(rec_a.granted_condition, self.condition_a)
        self.assertEqual(rec_b.granted_condition, self.condition_b)

    def test_fire_participant_records_count_matches_beneficiaries(self) -> None:
        """One CovenantRiteParticipant row per beneficiary."""
        result = perform_covenant_rite(session=self.session)
        self.assertEqual(result.participant_records.count(), 2)
        self.assertEqual(result.participants.count(), 2)


class RoleAwareLateJoinTests(_RiteTwoRoleTestCase):
    """Task 8: late-join assigns the newcomer's role package and rescales prior participants."""

    def setUp(self) -> None:
        super().setUp()
        # Fire the rite for the two initial members (different roles).
        self.rite_instance = perform_covenant_rite(session=self.session)

        # Third member with role_a (same as mem_a).
        self.mem_c = make_engaged_member(covenant=self.covenant, covenant_role=self.role_a)

    def test_late_join_newcomer_gets_role_package(self) -> None:
        """Newcomer (role_a) is folded in and their participant record uses condition_a."""
        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

        fold_arrival_into_active_rites(character_sheet=self.mem_c.character_sheet, room=self.room)

        rec_c = self.rite_instance.participant_records.filter(
            character_sheet=self.mem_c.character_sheet
        ).first()
        self.assertIsNotNone(rec_c, "Expected participant record for mem_c after late join")
        self.assertEqual(rec_c.granted_condition, self.condition_a)

    def test_late_join_prior_participants_rescaled_up(self) -> None:
        """Prior participants' severity rises when a newcomer joins."""
        from world.conditions.services import get_condition_instance

        _place_character_in_room(self.mem_c.character_sheet.character, self.room)

        # severity_for(2)=2, severity_for(3)=3 with rite params base=2,extra=1,min=2.
        old_severity = self.rite.severity_for(present_count=2)
        new_severity = self.rite.severity_for(present_count=3)
        self.assertGreater(new_severity, old_severity)

        fold_arrival_into_active_rites(character_sheet=self.mem_c.character_sheet, room=self.room)

        # mem_a's condition is condition_a; verify it was rescaled.
        live_a = get_condition_instance(self.mem_a.character_sheet.character, self.condition_a)
        self.assertIsNotNone(live_a, "Expected live condition on mem_a after late join")
        self.assertEqual(live_a.severity, new_severity)

        # mem_b's condition is condition_b; verify it was rescaled.
        live_b = get_condition_instance(self.mem_b.character_sheet.character, self.condition_b)
        self.assertIsNotNone(live_b, "Expected live condition on mem_b after late join")
        self.assertEqual(live_b.severity, new_severity)


class PerParticipantSweepTests(_RiteTwoRoleTestCase):
    """Task 9: sweep removes each participant's OWN recorded condition."""

    def setUp(self) -> None:
        super().setUp()
        self.rite_instance = perform_covenant_rite(session=self.session)

    def test_sweep_removes_own_conditions(self) -> None:
        """complete_rites_for_encounter removes each participant's own granted_condition."""
        from world.conditions.services import get_condition_instance

        complete_rites_for_encounter(encounter=self.encounter)

        self.rite_instance.refresh_from_db()
        self.assertIsNotNone(self.rite_instance.completed_at)

        # mem_a had condition_a; it should be gone.
        self.assertIsNone(
            get_condition_instance(self.mem_a.character_sheet.character, self.condition_a),
            "Expected condition_a removed from mem_a after sweep",
        )
        # mem_b had condition_b; it should be gone.
        self.assertIsNone(
            get_condition_instance(self.mem_b.character_sheet.character, self.condition_b),
            "Expected condition_b removed from mem_b after sweep",
        )
