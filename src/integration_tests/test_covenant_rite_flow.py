"""End-to-end integration test for the Covenant Rite fire path (#516).

Exercises the full pipeline:
  wire_covenant_rite_content() → build fireable RitualSession → fire_session()
  → CovenantRiteInstance + ConditionInstance buffs at correct severity
  → dramatic late entry rescales all participants
  → cleanup_completed_encounter removes buffs + stamps completed_at

CovenantRiteRolePackageFlowIntegrationTest (#753) extends this to exercise
the role-aware, level-banded, severity-scaling stat packages end-to-end against
the seeded Oathbound Resolve / Fury I / Fury II / Bulwark content.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.combat.factories import CombatEncounterFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.services import get_condition_instance, get_condition_modifier_total
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
    wire_covenant_rite_content,
)
from world.covenants.models import CovenantRite, CovenantRiteInstance, CovenantRole
from world.covenants.services import evaluate_scene_engagement
from world.magic.constants import ParticipantState, ReferenceKind
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.magic.services.sessions import fire_session
from world.mechanics.models import ModifierTarget
from world.scenes.constants import RoundStatus
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
            status=RoundStatus.DECLARING,
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


# ---------------------------------------------------------------------------
# #753: Role-aware, level-banded, severity-scaling stat packages — E2E test
# ---------------------------------------------------------------------------


def _build_session_for_covenant(
    *,
    rite: CovenantRite,
    covenant: object,
    initiator_sheet: object,
    accepted_sheets: list[object],
) -> RitualSession:
    """Build a fireable RitualSession for `rite` against `covenant`.

    Creates ACCEPTED participant rows for each sheet in `accepted_sheets`
    and a session-level COVENANT reference. Mirrors the pattern used in
    CovenantRiteFlowIntegrationTest.setUp().
    """
    session = RitualSession.objects.create(
        ritual=rite.ritual,
        initiator=initiator_sheet,
        proposed_terms="",
        session_kwargs={},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    for sheet in accepted_sheets:
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=sheet,
            state=ParticipantState.ACCEPTED,
        )
    RitualSessionReference.objects.create(
        session=session,
        participant=None,
        kind=ReferenceKind.COVENANT,
        ref_covenant=covenant,
        ref_covenant_role=None,
    )
    return session


class CovenantRiteRolePackageFlowIntegrationTest(TestCase):
    """End-to-end test for role-aware, level-banded, severity-scaling stat packages (#753).

    Exercises the full pipeline against the seeded Oathbound content from
    wire_covenant_rite_content():
      - Role divergence: Sword member gets Fury I; Shield member gets Bulwark.
      - Level band: same Sword role at covenant level ≥4 receives Fury II
        (strength+presence+wits) instead of Fury I (strength+presence).
      - Late-join rescale: prior Sword participant's get_condition_modifier_total
        (strength) rises when a new member arrives, because the severity increases.
      - Sweep: each participant's OWN recorded condition is removed at combat end.

    Assertions are genuine: they FAIL if all participants received the same
    condition, or if late-join did not rescale existing participants' totals.

    Uses setUp (not setUpTestData) — Evennia ObjectDB subclasses are not
    deepcopy-safe, so setUpTestData cannot be used for rooms/characters.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _modifier_target(name: str) -> ModifierTarget:
        """Fetch the ModifierTarget for a named stat (must exist after wire())."""
        return ModifierTarget.objects.get(name=name)

    # ------------------------------------------------------------------
    # setUp
    # ------------------------------------------------------------------

    def setUp(self) -> None:
        # Seed the canonical content (idempotent).
        self.rite = wire_covenant_rite_content()

        # Fetch the seeded reference-rite roles.
        self.sword_role: CovenantRole = CovenantRole.objects.get(slug="oath-rite-sword-role")
        self.shield_role: CovenantRole = CovenantRole.objects.get(slug="oath-rite-shield-role")

        # Covenant at level 2 (satisfies rite.min_covenant_level=2; gives Fury I to Sword).
        self.room = ObjectDBFactory(
            db_key="RoleTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.covenant = CovenantFactory(
            covenant_type=self.rite.covenant_type,
            level=2,
        )

        # Two initial members with DIFFERENT roles: one Sword, one Shield.
        self.sword_mem = make_engaged_member(
            covenant=self.covenant,
            covenant_role=self.sword_role,
        )
        self.shield_mem = make_engaged_member(
            covenant=self.covenant,
            covenant_role=self.shield_role,
        )
        # Place both in the room.
        _place_character_in_room(self.sword_mem.character_sheet.character, self.room)
        _place_character_in_room(self.shield_mem.character_sheet.character, self.room)

        # Active scene + encounter.
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.encounter = CombatEncounterFactory(
            room=self.room,
            scene=self.scene,
            status=RoundStatus.DECLARING,
        )

        # Build + fire the rite session.
        self.session = _build_session_for_covenant(
            rite=self.rite,
            covenant=self.covenant,
            initiator_sheet=self.sword_mem.character_sheet,
            accepted_sheets=[
                self.sword_mem.character_sheet,
                self.shield_mem.character_sheet,
            ],
        )

    # ------------------------------------------------------------------
    # Test A: role divergence — Sword gets Fury I; Shield gets Bulwark
    # ------------------------------------------------------------------

    def test_role_divergence_different_conditions_granted(self) -> None:
        """Sword and Shield members receive DIFFERENT role-specific conditions on fire.

        Sword member's participant record must reference 'Oathbound Fury I' (not Oathbound
        Resolve and not Oathbound Bulwark). Shield member must reference 'Oathbound Bulwark'.
        This assertion fails if all participants received the same granted_condition.
        """
        instance = fire_session(session=self.session)
        self.assertIsInstance(instance, CovenantRiteInstance)

        rec_sword = instance.participant_records.filter(
            character_sheet=self.sword_mem.character_sheet
        ).first()
        rec_shield = instance.participant_records.filter(
            character_sheet=self.shield_mem.character_sheet
        ).first()

        self.assertIsNotNone(rec_sword, "Missing participant record for Sword member")
        self.assertIsNotNone(rec_shield, "Missing participant record for Shield member")

        self.assertEqual(
            rec_sword.granted_condition.name,
            "Oathbound Fury I",
            f"Sword at level 2 should receive Fury I, got: {rec_sword.granted_condition.name}",
        )
        self.assertEqual(
            rec_shield.granted_condition.name,
            "Oathbound Bulwark",
            f"Shield should receive Oathbound Bulwark, got: {rec_shield.granted_condition.name}",
        )
        # The two conditions must be different rows.
        self.assertNotEqual(
            rec_sword.granted_condition.pk,
            rec_shield.granted_condition.pk,
            "Sword and Shield received the same condition — role divergence test FAILED",
        )

    def test_role_divergence_modifier_totals_differ_by_stat(self) -> None:
        """Sword has a 'strength' buff; Shield does NOT have a 'strength' buff.

        The Sword gets Oathbound Fury I (strength + presence); the Shield gets
        Oathbound Bulwark (stability + stamina). Their get_condition_modifier_total
        for 'strength' must differ — Sword > 0, Shield = 0.
        """
        fire_session(session=self.session)

        strength_target = self._modifier_target("strength")
        stability_target = self._modifier_target("stability")

        sword_strength = get_condition_modifier_total(
            self.sword_mem.character_sheet, strength_target
        )
        shield_strength = get_condition_modifier_total(
            self.shield_mem.character_sheet, strength_target
        )

        self.assertGreater(
            sword_strength,
            0,
            "Sword member should have a positive strength modifier from Fury I",
        )
        self.assertEqual(
            shield_strength,
            0,
            "Shield member should have NO strength modifier from Oathbound Bulwark",
        )

        # And the Shield has a stability buff; the Sword does not.
        sword_stability = get_condition_modifier_total(
            self.sword_mem.character_sheet, stability_target
        )
        shield_stability = get_condition_modifier_total(
            self.shield_mem.character_sheet, stability_target
        )
        self.assertGreater(
            shield_stability,
            0,
            "Shield member should have a positive stability modifier from Oathbound Bulwark",
        )
        self.assertEqual(
            sword_stability,
            0,
            "Sword member should have NO stability modifier from Fury I",
        )

    # ------------------------------------------------------------------
    # Test B: level band — Sword at level ≥4 gets Fury II (with wits)
    # ------------------------------------------------------------------

    def test_level_band_sword_at_level_4_receives_fury_ii(self) -> None:
        """Same Sword role at covenant level=4 receives Oathbound Fury II (strength+presence+wits).

        Fury I (level-1 band) has strength + presence only.
        Fury II (level-4 band) has strength + presence + wits.
        Asserting the granted_condition name + wits modifier total is the
        decisive proof that the band selection worked.
        """
        # Advance covenant to level 4.
        self.covenant.level = 4
        self.covenant.save(update_fields=["level"])

        # Build a fresh session at the same covenant (now level 4).
        session_l4 = _build_session_for_covenant(
            rite=self.rite,
            covenant=self.covenant,
            initiator_sheet=self.sword_mem.character_sheet,
            accepted_sheets=[
                self.sword_mem.character_sheet,
                self.shield_mem.character_sheet,
            ],
        )
        instance_l4 = fire_session(session=session_l4)

        rec_sword = instance_l4.participant_records.filter(
            character_sheet=self.sword_mem.character_sheet
        ).first()

        self.assertIsNotNone(rec_sword)
        self.assertEqual(
            rec_sword.granted_condition.name,
            "Oathbound Fury II",
            (
                f"Sword at covenant level 4 should receive Fury II, "
                f"got: {rec_sword.granted_condition.name}"
            ),
        )

        # Fury II has a wits modifier; Fury I does not.
        wits_target = self._modifier_target("wits")
        sword_wits = get_condition_modifier_total(self.sword_mem.character_sheet, wits_target)
        self.assertGreater(
            sword_wits,
            0,
            "Sword member at level 4 should have a positive wits modifier from Fury II",
        )

    def test_level_band_sword_at_level_1_has_no_wits_modifier(self) -> None:
        """Sword at level 2 (Fury I) has NO wits modifier, confirming band boundary."""
        # covenant is at level 2 by default in setUp — gives Fury I.
        fire_session(session=self.session)

        wits_target = self._modifier_target("wits")
        sword_wits = get_condition_modifier_total(self.sword_mem.character_sheet, wits_target)
        self.assertEqual(
            sword_wits,
            0,
            "Sword member at covenant level 2 (Fury I) should NOT have a wits modifier",
        )

    # ------------------------------------------------------------------
    # Test C: late-join rescale — prior participant's modifier total rises
    # ------------------------------------------------------------------

    def test_late_join_raises_modifier_total_for_prior_participants(self) -> None:
        """Non-engaged active member arrives mid-combat → prior Sword participant's
        strength modifier total increases (severity bumped by larger turnout).

        This test FAILS if late-join did not rescale existing participants.
        """
        from world.covenants.factories import CharacterCovenantRoleFactory

        fire_session(session=self.session)

        strength_target = self._modifier_target("strength")

        # Record the Sword member's strength modifier total BEFORE the late join.
        sword_strength_before = get_condition_modifier_total(
            self.sword_mem.character_sheet, strength_target
        )
        self.assertGreater(sword_strength_before, 0, "Sword should have strength buff before join")

        # A third member (Sword role; active but not engaged) arrives.
        # Use CharacterCovenantRoleFactory to create a non-engaged active member
        # (skipping set_engaged_membership intentionally — to test the broader
        # covenant_members_present path which includes non-engaged active members).
        third_mem = CharacterCovenantRoleFactory(
            covenant=self.covenant,
            covenant_role=self.sword_role,
            engaged=False,
            left_at=None,
        )
        _place_character_in_room(third_mem.character_sheet.character, self.room)

        # Engage the third member so fold_arrival_into_active_rites picks them up.
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=third_mem)

        evaluate_scene_engagement(
            character_sheet=third_mem.character_sheet,
            room=self.room,
        )

        # The Sword member's strength modifier total MUST be higher than before.
        sword_strength_after = get_condition_modifier_total(
            self.sword_mem.character_sheet, strength_target
        )
        self.assertGreater(
            sword_strength_after,
            sword_strength_before,
            (
                f"Sword member's strength modifier total should have risen after late join "
                f"(before={sword_strength_before}, after={sword_strength_after})"
            ),
        )

        # The newcomer also has a strength buff (Sword role package).
        third_strength = get_condition_modifier_total(third_mem.character_sheet, strength_target)
        self.assertGreater(
            third_strength,
            0,
            "Late-joining Sword member should have received a strength buff",
        )

    # ------------------------------------------------------------------
    # Test D: sweep — each participant's OWN condition removed at combat end
    # ------------------------------------------------------------------

    def test_sweep_removes_each_participants_own_condition(self) -> None:
        """cleanup_completed_encounter removes each participant's OWN granted_condition.

        Sword had Fury I (strength buff); Shield had Bulwark (stability buff).
        After sweep, both conditions are gone — get_condition_instance returns None
        for each participant's OWN recorded condition.
        """
        instance = fire_session(session=self.session)

        # Record which condition each participant was granted.
        rec_sword = instance.participant_records.get(character_sheet=self.sword_mem.character_sheet)
        rec_shield = instance.participant_records.get(
            character_sheet=self.shield_mem.character_sheet
        )
        sword_condition = rec_sword.granted_condition
        shield_condition = rec_shield.granted_condition

        # Sanity: both have live conditions before sweep.
        self.assertIsNotNone(
            get_condition_instance(self.sword_mem.character_sheet.character, sword_condition),
            "Sword member should have a live condition before sweep",
        )
        self.assertIsNotNone(
            get_condition_instance(self.shield_mem.character_sheet.character, shield_condition),
            "Shield member should have a live condition before sweep",
        )
        # The two conditions are DIFFERENT (confirms per-role divergence was preserved).
        self.assertNotEqual(sword_condition.pk, shield_condition.pk)

        # Trigger combat-end cleanup.
        cleanup_completed_encounter(self.encounter)

        # Both conditions must be gone.
        self.assertIsNone(
            get_condition_instance(self.sword_mem.character_sheet.character, sword_condition),
            "Sword member's Fury I should be removed after combat end",
        )
        self.assertIsNone(
            get_condition_instance(self.shield_mem.character_sheet.character, shield_condition),
            "Shield member's Oathbound Bulwark should be removed after combat end",
        )

        # CovenantRiteInstance.completed_at is stamped.
        instance.refresh_from_db()
        self.assertIsNotNone(
            instance.completed_at,
            "CovenantRiteInstance.completed_at should be stamped after cleanup",
        )
