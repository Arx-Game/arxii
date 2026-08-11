"""Minor (guest) membership standing (#2992).

Mirrors ``test_secondary_vows.py``'s setup style (built in ``setUp``, not
``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances,
which aren't deepcopyable).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.constants import CovenantType, MembershipStanding
from world.covenants.exceptions import (
    MinorStandingDuranceOnlyError,
    MinorStandingRequiresSecondaryEngageError,
    SecondaryVowRequiresEngagedPrimaryError,
    SecondaryVowSameAnchorError,
    VowGateError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    seed_mentor_bond_defaults,
)
from world.covenants.services import (
    add_member,
    induct_member_via_session,
    set_engaged_membership,
    step_back_to_minor,
    swear_core,
)


def _set_primary_level(sheet, level: int) -> None:
    """Helper: give sheet.character a primary CharacterClassLevel at the given level.

    Mirrors ``test_vow_gate.py``'s identically-named helper.
    """
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet,
        character_class=char_class,
        level=level,
        is_primary=True,
    )


class MinorStandingEngageTests(TestCase):
    """Engage-time behavior of MINOR-standing memberships (#2992)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

    def _minor_membership(self, role=None, covenant=None):
        role = role or CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = covenant or CovenantFactory(covenant_type=CovenantType.DURANCE)
        return CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=covenant,
            covenant_role=role,
            standing=MembershipStanding.MINOR,
        )

    def test_minor_row_cannot_engage_primary_lane(self) -> None:
        minor_membership = self._minor_membership()

        with self.assertRaises(MinorStandingRequiresSecondaryEngageError):
            set_engaged_membership(membership=minor_membership, as_secondary=False)

    def test_minor_row_engages_secondary_without_engaged_primary(self) -> None:
        minor_membership = self._minor_membership()

        set_engaged_membership(membership=minor_membership, as_secondary=True)

        minor_membership.refresh_from_db()
        self.assertTrue(minor_membership.engaged)
        self.assertTrue(minor_membership.is_secondary)

    def test_core_row_secondary_engage_still_requires_engaged_primary(self) -> None:
        core_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
        )

        with self.assertRaises(SecondaryVowRequiresEngagedPrimaryError):
            set_engaged_membership(membership=core_membership, as_secondary=True)

    def test_minor_standing_forbidden_on_battle_covenant(self) -> None:
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        battle_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.BATTLE),
            covenant_role=battle_role,
            standing=MembershipStanding.MINOR,
        )

        with self.assertRaises(ValidationError):
            battle_membership.full_clean()

    def test_minor_secondary_respects_same_anchor_and_thread_cap_when_primary_engaged(
        self,
    ) -> None:
        primary_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
        )
        set_engaged_membership(membership=primary_membership)

        minor_membership = self._minor_membership(role=self.primary_role)

        with self.assertRaises(SecondaryVowSameAnchorError):
            set_engaged_membership(membership=minor_membership, as_secondary=True)


class MinorInductionAndSwearCoreTests(TestCase):
    """Minor induction, level-band bypass, swear-core upgrade, step-back (#2992)."""

    def setUp(self) -> None:
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=4)  # band [2,6]
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

    def test_add_member_minor_bypasses_level_band(self) -> None:
        sheet = CharacterSheetFactory()
        _set_primary_level(sheet, 1)  # out of band [2,6]

        row = add_member(
            covenant=self.covenant,
            character_sheet=sheet,
            role=self.role,
            standing=MembershipStanding.MINOR,
        )
        self.assertEqual(row.standing, MembershipStanding.MINOR)

        other_sheet = CharacterSheetFactory()
        _set_primary_level(other_sheet, 1)  # also out of band
        other_covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=4)
        other_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        with self.assertRaises(VowGateError):
            add_member(
                covenant=other_covenant,
                character_sheet=other_sheet,
                role=other_role,
                standing=MembershipStanding.CORE,
            )

    def test_swear_core_runs_band_gate_and_flips_standing(self) -> None:
        from world.missions.constants import ExternalAct, OptionKind, OptionSource
        from world.missions.factories import (
            MissionInstanceFactory,
            MissionNodeFactory,
            MissionOptionFactory,
            MissionParticipantFactory,
            MissionTemplateFactory,
        )

        out_of_band_sheet = CharacterSheetFactory()
        _set_primary_level(out_of_band_sheet, 1)  # out of band
        out_of_band_membership = CharacterCovenantRoleFactory(
            character_sheet=out_of_band_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            standing=MembershipStanding.MINOR,
        )
        with self.assertRaises(VowGateError):
            swear_core(membership=out_of_band_membership)
        out_of_band_membership.refresh_from_db()
        self.assertEqual(out_of_band_membership.standing, MembershipStanding.MINOR)

        in_band_sheet = CharacterSheetFactory()
        _set_primary_level(in_band_sheet, 4)  # in band
        in_band_membership = CharacterCovenantRoleFactory(
            character_sheet=in_band_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            standing=MembershipStanding.MINOR,
        )

        # Same seam InductMemberExternalActWiringTests uses (world/missions/tests/
        # test_external_acts.py): a waiting EXTERNAL_ACT mission option advances
        # only when notify_external_act(COVENANT_SWORN) actually fires.
        template = MissionTemplateFactory(name="swear-core-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=in_band_sheet,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
            branch_target=target,
        )

        swear_core(membership=in_band_membership)

        in_band_membership.refresh_from_db()
        self.assertEqual(in_band_membership.standing, MembershipStanding.CORE)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, target)

    def _build_induction_session(self, *, candidate, standing="core"):
        """Minimal induction-session fixture (mirrors ``InductMemberViaSessionTests``
        in ``test_services.py``): one existing member (initiator) + the candidate,
        who chooses ``self.role``. Returns the session."""
        from datetime import UTC, datetime, timedelta

        from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        initiator_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=initiator_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
        )

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator_sheet,
            session_kwargs={"standing": standing},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=self.covenant,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator_sheet,
            state=ParticipantState.ACCEPTED,
        )
        candidate_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=candidate_p,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=self.role,
        )
        return session

    def test_induct_existing_minor_member_upgrades(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        candidate = CharacterSheetFactory()
        _set_primary_level(candidate, 4)  # in band, so the upgrade's gate passes
        existing_membership = CharacterCovenantRoleFactory(
            character_sheet=candidate,
            covenant=self.covenant,
            covenant_role=self.role,
            standing=MembershipStanding.MINOR,
        )

        session = self._build_induction_session(candidate=candidate, standing="core")

        membership = induct_member_via_session(session=session)

        self.assertEqual(membership.pk, existing_membership.pk)
        membership.refresh_from_db()
        self.assertEqual(membership.standing, MembershipStanding.CORE)
        self.assertEqual(
            CharacterCovenantRole.objects.filter(
                character_sheet=candidate, covenant=self.covenant, left_at__isnull=True
            ).count(),
            1,
        )

    def test_induct_minor_standing_requires_durance_covenant(self) -> None:
        """MINOR induction into a COURT covenant is rejected before add/upgrade runs."""
        court_covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        self.covenant = court_covenant
        self.role = CovenantRoleFactory(covenant_type=CovenantType.COURT)

        candidate = CharacterSheetFactory()
        session = self._build_induction_session(candidate=candidate, standing="minor")

        with self.assertRaises(MinorStandingDuranceOnlyError):
            induct_member_via_session(session=session)

    def test_induct_minor_standing_fires_no_external_act(self) -> None:
        """A fresh MINOR join is not a full swearing — no COVENANT_SWORN act fires."""
        from world.missions.constants import ExternalAct, OptionKind, OptionSource
        from world.missions.factories import (
            MissionInstanceFactory,
            MissionNodeFactory,
            MissionOptionFactory,
            MissionParticipantFactory,
            MissionTemplateFactory,
        )

        candidate = CharacterSheetFactory()
        session = self._build_induction_session(candidate=candidate, standing="minor")

        template = MissionTemplateFactory(name="minor-join-no-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=candidate,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
            branch_target=target,
        )

        membership = induct_member_via_session(session=session)

        self.assertEqual(membership.standing, MembershipStanding.MINOR)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, entry)

    def test_step_back_to_minor_unengages_primary_lane(self) -> None:
        core_membership = CharacterCovenantRoleFactory(
            character_sheet=CharacterSheetFactory(),
            covenant=self.covenant,
            covenant_role=self.role,
        )
        set_engaged_membership(membership=core_membership)
        rank_before = core_membership.rank

        step_back_to_minor(membership=core_membership)

        core_membership.refresh_from_db()
        self.assertFalse(core_membership.engaged)
        self.assertEqual(core_membership.standing, MembershipStanding.MINOR)
        self.assertEqual(core_membership.rank, rank_before)
