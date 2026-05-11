"""Tests for covenant service functions (Tasks 22–23)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import DuplicateFounderError, InsufficientFoundersError
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    GearArchetypeCompatibilityFactory,
)
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import (
    add_member,
    assign_covenant_role,
    change_role,
    clear_engaged_for_type,
    clear_engaged_membership,
    create_covenant,
    dissolve_covenant,
    end_covenant_role,
    is_gear_compatible,
    set_engaged_membership,
)
from world.covenants.types import CovenantFounder
from world.items.constants import GearArchetype


class CreateCovenantTests(TestCase):
    def test_creates_covenant_with_two_founder_memberships(self) -> None:
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_b = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov = create_covenant(
            name="Founders",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="Forge bonds.",
            founders=[
                CovenantFounder(character_sheet=sheet_a, role=role_a),
                CovenantFounder(character_sheet=sheet_b, role=role_b),
            ],
        )
        self.assertEqual(cov.covenant_type, CovenantType.DURANCE)
        membership_a = CharacterCovenantRole.objects.get(character_sheet=sheet_a, covenant=cov)
        membership_b = CharacterCovenantRole.objects.get(character_sheet=sheet_b, covenant=cov)
        self.assertEqual(membership_a.covenant_role, role_a)
        self.assertEqual(membership_b.covenant_role, role_b)
        for membership in (membership_a, membership_b):
            self.assertIsNone(membership.left_at)
            self.assertFalse(membership.engaged)

    def test_rejects_single_founder(self) -> None:
        """Covenant formation requires ≥2 founders; solo formation is a programmer error."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        with self.assertRaises(InsufficientFoundersError):
            create_covenant(
                name="Solo",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="Alone.",
                founders=[CovenantFounder(character_sheet=sheet, role=role)],
            )

    def test_rejects_empty_founders(self) -> None:
        with self.assertRaises(InsufficientFoundersError):
            create_covenant(
                name="None",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="Empty.",
                founders=[],
            )

    def test_rejects_duplicate_founder_sheet(self) -> None:
        """Two founder entries pointing at the same character sheet is rejected."""
        sheet = CharacterSheetFactory()
        role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_b = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        with self.assertRaises(DuplicateFounderError):
            create_covenant(
                name="Dupe",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="Same person twice.",
                founders=[
                    CovenantFounder(character_sheet=sheet, role=role_a),
                    CovenantFounder(character_sheet=sheet, role=role_b),
                ],
            )


class AddMemberTests(TestCase):
    def test_creates_active_membership(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        membership = add_member(covenant=cov, character_sheet=sheet, role=role)
        self.assertIsNone(membership.left_at)
        self.assertEqual(membership.covenant, cov)

    def test_duplicate_active_raises_integrity_error(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        add_member(covenant=cov, character_sheet=sheet, role=role)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                add_member(covenant=cov, character_sheet=sheet, role=role)


class ChangeRoleTests(TestCase):
    def test_closes_old_creates_new(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        old_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        new_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov, covenant_role=old_role
        )
        new_membership = change_role(membership=membership, new_role=new_role)

        membership.refresh_from_db()
        self.assertIsNotNone(membership.left_at)
        self.assertFalse(membership.engaged)

        self.assertIsNone(new_membership.left_at)
        self.assertEqual(new_membership.covenant_role, new_role)
        self.assertFalse(new_membership.engaged)  # explicit re-engagement required


class DissolveCovenantTests(TestCase):
    def test_ends_all_memberships_and_unengages(self) -> None:
        cov = CovenantFactory()
        s1 = CharacterSheetFactory()
        s2 = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        m1 = CharacterCovenantRoleFactory(character_sheet=s1, covenant=cov, covenant_role=role)
        m2 = CharacterCovenantRoleFactory(character_sheet=s2, covenant=cov, covenant_role=role)
        # Set m1 engaged directly (no service yet)
        m1.engaged = True
        m1.save(update_fields=["engaged"])

        dissolve_covenant(covenant=cov)

        cov.refresh_from_db()
        self.assertIsNotNone(cov.dissolved_at)
        for m in (m1, m2):
            m.refresh_from_db()
            self.assertIsNotNone(m.left_at)
            self.assertFalse(m.engaged)

    def test_idempotent(self) -> None:
        cov = CovenantFactory()
        dissolve_covenant(covenant=cov)
        cov.refresh_from_db()
        first_dissolved_at = cov.dissolved_at
        dissolve_covenant(covenant=cov)
        cov.refresh_from_db()
        self.assertEqual(cov.dissolved_at, first_dissolved_at)


class AssignCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.cov = CovenantFactory()
        cls.role = CovenantRoleFactory(slug="vanguard", covenant_type=cls.cov.covenant_type)

    def test_assign_creates_active_row(self) -> None:
        assignment = assign_covenant_role(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )
        self.assertIsNone(assignment.left_at)
        self.assertEqual(assignment.character_sheet, self.sheet)
        self.assertEqual(assignment.covenant_role, self.role)

    def test_assign_invalidates_handler(self) -> None:
        # Warm the cache before assigning.
        _ = list(self.sheet.character.covenant_roles.currently_engaged_roles())

        new_cov = CovenantFactory()
        new_role = CovenantRoleFactory(slug="anchor", covenant_type=new_cov.covenant_type)
        assign_covenant_role(character_sheet=self.sheet, covenant=new_cov, covenant_role=new_role)

        # currently_held_role_in should reflect the new assignment, not stale cache.
        self.assertEqual(
            self.sheet.character.covenant_roles.currently_held_role_in(new_cov), new_role
        )

    def test_assign_duplicate_active_raises_integrity_error(self) -> None:
        # Create an active assignment first.
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )

        with self.assertRaises(IntegrityError):
            assign_covenant_role(
                character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
            )


class EndCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.cov = CovenantFactory()
        cls.role = CovenantRoleFactory(slug="shield-end", covenant_type=cls.cov.covenant_type)

    def test_end_sets_left_at(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )
        end_covenant_role(assignment=assignment)
        self.assertIsNotNone(assignment.left_at)

    def test_end_is_idempotent(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )
        end_covenant_role(assignment=assignment)
        first_left_at = assignment.left_at

        # Calling again should not modify left_at.
        end_covenant_role(assignment=assignment)
        self.assertEqual(assignment.left_at, first_left_at)

    def test_end_invalidates_handler(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )
        # Warm the cache so currently_held_role_in returns role.
        self.assertEqual(
            self.sheet.character.covenant_roles.currently_held_role_in(self.cov), self.role
        )

        end_covenant_role(assignment=assignment)

        # After ending, currently_held_role_in should return None.
        self.assertIsNone(self.sheet.character.covenant_roles.currently_held_role_in(self.cov))


class IsGearCompatibleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory(slug="crown-gear")

    def test_is_gear_compatible_returns_true_when_row_exists(self) -> None:
        GearArchetypeCompatibilityFactory(
            covenant_role=self.role, gear_archetype=GearArchetype.HEAVY_ARMOR
        )
        self.assertTrue(is_gear_compatible(self.role, GearArchetype.HEAVY_ARMOR))

    def test_is_gear_compatible_returns_false_when_row_missing(self) -> None:
        self.assertFalse(is_gear_compatible(self.role, GearArchetype.LIGHT_ARMOR))


class SetEngagedMembershipTests(TestCase):
    def test_engages_membership(self) -> None:
        m = CharacterCovenantRoleFactory()
        set_engaged_membership(membership=m)
        m.refresh_from_db()
        self.assertTrue(m.engaged)

    def test_un_engages_other_same_type(self) -> None:
        sheet = CharacterSheetFactory()
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE)
        role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_b = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        m_a = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov_a, covenant_role=role_a
        )
        set_engaged_membership(membership=m_a)
        m_b = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov_b, covenant_role=role_b
        )
        set_engaged_membership(membership=m_b)
        m_a.refresh_from_db()
        m_b.refresh_from_db()
        self.assertFalse(m_a.engaged)
        self.assertTrue(m_b.engaged)

    def test_does_not_touch_battle_when_engaging_durance(self) -> None:
        sheet = CharacterSheetFactory()
        battle_cov = CovenantFactory(covenant_type=CovenantType.BATTLE)
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        m_battle = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=battle_cov,
            covenant_role=battle_role,
        )
        set_engaged_membership(membership=m_battle)

        durance_cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        durance_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        m_durance = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=durance_cov,
            covenant_role=durance_role,
        )
        set_engaged_membership(membership=m_durance)

        m_battle.refresh_from_db()
        m_durance.refresh_from_db()
        self.assertTrue(m_battle.engaged)
        self.assertTrue(m_durance.engaged)


class ClearEngagedMembershipTests(TestCase):
    def test_clears_engaged_flag(self) -> None:
        m = CharacterCovenantRoleFactory()
        set_engaged_membership(membership=m)
        clear_engaged_membership(membership=m)
        m.refresh_from_db()
        self.assertFalse(m.engaged)

    def test_idempotent(self) -> None:
        m = CharacterCovenantRoleFactory()  # engaged=False by default
        clear_engaged_membership(membership=m)
        m.refresh_from_db()
        self.assertFalse(m.engaged)


class ClearEngagedForTypeTests(TestCase):
    def test_unengages_all_engaged_of_given_type(self) -> None:
        sheet = CharacterSheetFactory()
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE)
        m_a = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=cov_a,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
        )
        m_b = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=cov_b,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
        )
        # Engage one (set_engaged_membership would un-engage the other; for the
        # test we just want both engaged temporarily, so set them directly).
        m_a.engaged = True
        m_a.save(update_fields=["engaged"])
        m_b.engaged = True
        m_b.save(update_fields=["engaged"])

        clear_engaged_for_type(character_sheet=sheet, covenant_type=CovenantType.DURANCE)
        m_a.refresh_from_db()
        m_b.refresh_from_db()
        self.assertFalse(m_a.engaged)
        self.assertFalse(m_b.engaged)

    def test_does_not_touch_other_types(self) -> None:
        sheet = CharacterSheetFactory()
        battle_m = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.BATTLE),
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.BATTLE),
        )
        battle_m.engaged = True
        battle_m.save(update_fields=["engaged"])

        clear_engaged_for_type(character_sheet=sheet, covenant_type=CovenantType.DURANCE)
        battle_m.refresh_from_db()
        self.assertTrue(battle_m.engaged)


class MemberRosterInvalidationTests(TestCase):
    def test_add_member_invalidates_member_roster(self) -> None:
        cov = CovenantFactory()
        # Warm the roster cache:
        _ = cov.member_roster.active_memberships
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        add_member(covenant=cov, character_sheet=sheet, role=role)
        rows = cov.member_roster.active_memberships
        self.assertEqual(len(rows), 1)

    def test_change_role_invalidates_member_roster(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        old_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        new_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov, covenant_role=old_role
        )
        # Warm the roster cache:
        _ = cov.member_roster.active_memberships
        change_role(membership=membership, new_role=new_role)
        rows = cov.member_roster.active_memberships
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].covenant_role, new_role)

    def test_dissolve_covenant_invalidates_member_roster(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        # Warm the roster cache:
        _ = cov.member_roster.active_memberships
        dissolve_covenant(covenant=cov)
        rows = cov.member_roster.active_memberships
        self.assertEqual(len(rows), 0)

    def test_assign_covenant_role_invalidates_member_roster(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        # Warm the roster cache:
        _ = cov.member_roster.active_memberships
        assign_covenant_role(character_sheet=sheet, covenant=cov, covenant_role=role)
        rows = cov.member_roster.active_memberships
        self.assertEqual(len(rows), 1)

    def test_end_covenant_role_invalidates_member_roster(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        assignment = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov, covenant_role=role
        )
        # Warm the roster cache:
        _ = cov.member_roster.active_memberships
        end_covenant_role(assignment=assignment)
        rows = cov.member_roster.active_memberships
        self.assertEqual(len(rows), 0)


class MakeEngagedMemberTests(TestCase):
    def test_creates_engaged_row(self) -> None:
        from world.covenants.factories import make_engaged_member

        membership = make_engaged_member()
        self.assertTrue(membership.engaged)
        self.assertIsNone(membership.left_at)


class CreateCovenantViaSessionTests(TestCase):
    def test_unpacks_session_and_creates_covenant(self) -> None:
        """Set up a FORMATION session with two ACCEPTED participants who each
        chose a role, fire-style invoke the wrapper, assert the covenant exists
        with both memberships and correct roles."""
        from datetime import UTC, datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.models import Covenant
        from world.covenants.services import create_covenant_via_session
        from world.magic.constants import (
            ParticipantState,
            ParticipationRule,
            ReferenceKind,
        )
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        # Manually build a "post-accept, pre-fire" session state — skipping
        # draft/accept services to focus this test on the wrapper:
        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        role_for_initiator = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
        )
        role_for_invitee = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
        )
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={
                "name": "Sword of Aerith",
                "covenant_type": CovenantType.DURANCE,
                "sworn_objective": "End the curse.",
            },
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        p_init = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
        )
        p_inv = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=invitee,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=p_init,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=role_for_initiator,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=p_inv,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=role_for_invitee,
        )

        covenant = create_covenant_via_session(session=session)
        self.assertIsInstance(covenant, Covenant)
        self.assertEqual(covenant.name, "Sword of Aerith")
        self.assertEqual(covenant.covenant_type, CovenantType.DURANCE)
        self.assertEqual(covenant.sworn_objective, "End the curse.")
        # Both founders should have memberships with their chosen roles:
        memberships = list(covenant.member_roster.active_memberships)
        self.assertEqual(len(memberships), 2)
        roles_by_sheet = {m.character_sheet_id: m.covenant_role_id for m in memberships}
        self.assertEqual(roles_by_sheet[initiator.pk], role_for_initiator.pk)
        self.assertEqual(roles_by_sheet[invitee.pk], role_for_invitee.pk)

    def test_missing_participant_role_reference_raises(self) -> None:
        """If an ACCEPTED participant has no COVENANT_ROLE reference, raise."""
        from datetime import UTC, datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant_via_session
        from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
        from world.magic.exceptions import RequiredReferenceMissingError
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={
                "name": "Half-Founded",
                "covenant_type": CovenantType.DURANCE,
                "sworn_objective": "x",
            },
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        p_init = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
        )
        # Initiator has reference; invitee does NOT:
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=invitee,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=p_init,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=role,
        )

        with self.assertRaises(RequiredReferenceMissingError):
            create_covenant_via_session(session=session)

    def test_name_conflict_translates_to_covenant_name_conflict_error(self) -> None:
        """Duplicate covenant name → IntegrityError → typed CovenantNameConflictError."""
        from datetime import UTC, datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.exceptions import CovenantNameConflictError
        from world.covenants.factories import CovenantFactory, CovenantRoleFactory
        from world.covenants.services import create_covenant_via_session
        from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        # Pre-existing covenant with the name we'll try to use:
        CovenantFactory(name="Already Taken")

        ritual = RitualFactory(participation_rule=ParticipationRule.FORMATION)
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={
                "name": "Already Taken",
                "covenant_type": CovenantType.DURANCE,
                "sworn_objective": "x",
            },
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        p_init = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
        )
        p_inv = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=invitee,
            state=ParticipantState.ACCEPTED,
        )
        for p in [p_init, p_inv]:
            RitualSessionReference.objects.create(
                session=session,
                participant=p,
                kind=ReferenceKind.COVENANT_ROLE,
                ref_covenant_role=role,
            )

        with self.assertRaises(CovenantNameConflictError):
            create_covenant_via_session(session=session)


class InductMemberViaSessionTests(TestCase):
    def _build_induction_session(
        self,
        *,
        existing_members: int = 2,
        candidate_chooses_role: bool = True,
    ):
        """Helper: set up an INDUCTION session with target_covenant ref +
        candidate's COVENANT_ROLE ref. Returns (session, covenant, candidate, role).

        Initiator and any extra existing-member participants are ACCEPTED but
        have no role reference (existing members don't choose new roles).
        Candidate is ACCEPTED with a role reference (if candidate_chooses_role)."""
        from datetime import UTC, datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        existing_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        # Existing members (initiator + extras):
        existing_sheets = [CharacterSheetFactory() for _ in range(existing_members)]
        for sheet in existing_sheets:
            CharacterCovenantRoleFactory(
                character_sheet=sheet,
                covenant=covenant,
                covenant_role=existing_role,
            )
        candidate = CharacterSheetFactory()
        chosen_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=existing_sheets[0],
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        # Session-level reference: which covenant the induction targets
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=covenant,
        )
        # Existing members are participants in ACCEPTED state, no role ref:
        for sheet in existing_sheets:
            RitualSessionParticipant.objects.create(
                session=session,
                character_sheet=sheet,
                state=ParticipantState.ACCEPTED,
            )
        # Candidate is ACCEPTED with a role choice:
        candidate_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate,
            state=ParticipantState.ACCEPTED,
        )
        if candidate_chooses_role:
            RitualSessionReference.objects.create(
                session=session,
                participant=candidate_p,
                kind=ReferenceKind.COVENANT_ROLE,
                ref_covenant_role=chosen_role,
            )
        return session, covenant, candidate, chosen_role

    def test_unpacks_session_and_adds_member(self):
        from world.covenants.models import CharacterCovenantRole
        from world.covenants.services import induct_member_via_session

        session, covenant, candidate, chosen_role = self._build_induction_session()
        membership = induct_member_via_session(session=session)
        self.assertIsInstance(membership, CharacterCovenantRole)
        self.assertEqual(membership.character_sheet, candidate)
        self.assertEqual(membership.covenant, covenant)
        self.assertEqual(membership.covenant_role, chosen_role)
        self.assertIsNone(membership.left_at)

    def test_missing_target_covenant_reference_raises(self):
        """Session-level COVENANT reference is required."""
        from datetime import UTC, datetime, timedelta

        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.services import induct_member_via_session
        from world.magic.constants import ParticipationRule
        from world.magic.exceptions import SessionTargetMissingError
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=CharacterSheetFactory(),
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        with self.assertRaises(SessionTargetMissingError):
            induct_member_via_session(session=session)

    def test_missing_candidate_role_reference_raises(self):
        """The candidate must have a COVENANT_ROLE choice."""
        from world.covenants.services import induct_member_via_session
        from world.magic.exceptions import RequiredReferenceMissingError

        session, _covenant, _candidate, _ = self._build_induction_session(
            candidate_chooses_role=False,
        )
        with self.assertRaises(RequiredReferenceMissingError):
            induct_member_via_session(session=session)
