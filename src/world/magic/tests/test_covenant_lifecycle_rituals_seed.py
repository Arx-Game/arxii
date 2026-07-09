"""Tests for wire_covenant_lifecycle_rituals() seeding (#2114).

Proves the covenant/org lifecycle Ritual rows + MentorBondConfig singleton are
reachable from a fresh DB via seed_magic_dev() (the Big Button path,
CLUSTER_SEEDERS["magic"]) — not just from test factories — and that
re-running the seed is idempotent per the spec's user story 7.

Also proves "Renew the Oath" is genuinely fireable (not just a bare Ritual
row): perform_covenant_rite reads session.ritual.covenant_rite, a required
OneToOne sidecar that the bare RenewTheOathRitualFactory() does not create —
wire_covenant_lifecycle_rituals() must delegate to the existing
wire_covenant_rite_content() helper instead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantRoleFactory
from world.covenants.models import Covenant, CovenantRite, MentorBondConfig
from world.magic.constants import (
    ParticipantState,
    ParticipationRule,
    ReferenceKind,
    RitualExecutionKind,
)
from world.magic.factories import wire_covenant_lifecycle_rituals
from world.magic.models import Ritual
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.seeds.game_content.magic import seed_magic_dev
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationMembership

_EXPECTED_RITUALS: dict[str, str] = {
    "Covenant Formation": "world.covenants.services.create_covenant_via_session",
    "Covenant Induction": "world.covenants.services.induct_member_via_session",
    "Call the Banners": "world.covenants.services.rise_battle_covenant_via_session",
    "Mentor's Vow": "world.covenants.services.establish_mentor_bond_via_session",
    "Renew the Oath": "world.covenants.services.perform_covenant_rite",
    "Organization Induction": (
        "world.societies.membership_services.induct_organization_member_via_session"
    ),
}


class CovenantLifecycleRitualsSeedTests(TestCase):
    """A fresh-DB seed_magic_dev() run (the Big Button path) yields every
    covenant-lifecycle Ritual row, findable by exact name and dispatch-ready."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result = seed_magic_dev()

    def test_all_covenant_lifecycle_rituals_seeded_with_correct_dispatch(self) -> None:
        for name, service_path in _EXPECTED_RITUALS.items():
            ritual = Ritual.objects.get(name=name)
            self.assertEqual(ritual.execution_kind, RitualExecutionKind.SERVICE)
            self.assertEqual(ritual.service_function_path, service_path)

    def test_formation_ritual_serves_durance_and_battle_only(self) -> None:
        """Decision #5: coverage is DURANCE + BATTLE only; COURT is out of scope."""
        ritual = Ritual.objects.get(name="Covenant Formation")
        covenant_type_field = next(
            f for f in ritual.input_schema["fields"] if f["name"] == "covenant_type"
        )
        self.assertEqual(set(covenant_type_field["options"]), {"DURANCE", "BATTLE"})

    def test_renew_the_oath_has_covenant_rite_sidecar(self) -> None:
        """perform_covenant_rite reads session.ritual.covenant_rite — the sidecar
        must exist, not just the bare Ritual row (else firing crashes)."""
        ritual = Ritual.objects.get(name="Renew the Oath")
        rite = CovenantRite.objects.get(ritual=ritual)
        self.assertEqual(rite.ritual_id, ritual.pk)
        self.assertIsNotNone(rite.granted_condition)

    def test_mentor_bond_config_singleton_seeded(self) -> None:
        config = MentorBondConfig.objects.get(pk=1)
        self.assertIsNotNone(config.band_width)

    def test_covenant_lifecycle_content_returned_from_seed_magic_dev(self) -> None:
        content = self.result.covenant_lifecycle_content
        self.assertEqual(content.formation_ritual.name, "Covenant Formation")
        self.assertEqual(content.induction_ritual.name, "Covenant Induction")
        self.assertEqual(content.banner_call_ritual.name, "Call the Banners")
        self.assertEqual(content.mentors_vow_ritual.name, "Mentor's Vow")
        self.assertEqual(content.renew_the_oath_ritual.name, "Renew the Oath")
        self.assertEqual(content.org_induction_ritual.name, "Organization Induction")
        self.assertIsNotNone(content.mentor_bond_config)
        self.assertIsInstance(content.covenant_rite, CovenantRite)


class WireCovenantLifecycleRitualsIdempotencyTests(TestCase):
    """Re-running wire_covenant_lifecycle_rituals() on a populated DB is a no-op
    for the Ritual/CovenantRite rows and preserves staff edits (user story 7)."""

    def test_second_run_creates_no_duplicate_rituals(self) -> None:
        wire_covenant_lifecycle_rituals()
        count_after_first = Ritual.objects.filter(name__in=_EXPECTED_RITUALS).count()
        self.assertEqual(count_after_first, len(_EXPECTED_RITUALS))

        wire_covenant_lifecycle_rituals()
        count_after_second = Ritual.objects.filter(name__in=_EXPECTED_RITUALS).count()
        self.assertEqual(count_after_second, len(_EXPECTED_RITUALS))
        self.assertEqual(CovenantRite.objects.count(), 1)

    def test_staff_edit_to_ritual_survives_second_run(self) -> None:
        wire_covenant_lifecycle_rituals()
        ritual = Ritual.objects.get(name="Mentor's Vow")
        ritual.description = "Staff-edited description."
        ritual.save(update_fields=["description"])

        wire_covenant_lifecycle_rituals()

        ritual.refresh_from_db()
        self.assertEqual(ritual.description, "Staff-edited description.")

    def test_staff_edit_to_covenant_rite_survives_second_run(self) -> None:
        wire_covenant_lifecycle_rituals()
        ritual = Ritual.objects.get(name="Renew the Oath")
        rite = CovenantRite.objects.get(ritual=ritual)
        rite.min_covenant_level = 99
        rite.save(update_fields=["min_covenant_level"])

        wire_covenant_lifecycle_rituals()

        rite.refresh_from_db()
        self.assertEqual(rite.min_covenant_level, 99)

    def test_mentor_bond_config_reset_to_authored_defaults_each_run(self) -> None:
        """MentorBondConfig is a pre-launch tuning knob (update_or_create by
        design — see seed_mentor_bond_defaults docstring), unlike the Ritual
        rows above, which preserve staff edits."""
        wire_covenant_lifecycle_rituals()
        config = MentorBondConfig.objects.get(pk=1)
        config.band_width = 999
        config.save(update_fields=["band_width"])

        wire_covenant_lifecycle_rituals()

        config.refresh_from_db()
        self.assertNotEqual(config.band_width, 999)


class SeededFormationRitualDispatchTests(TestCase):
    """Prove the seed_magic_dev()-seeded "Covenant Formation" Ritual row (not a
    freshly-built factory row) resolves and dispatches to create_covenant_via_session."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_magic_dev()

    def test_seeded_formation_ritual_fires_and_creates_covenant(self) -> None:
        from world.covenants.services import create_covenant_via_session

        ritual = Ritual.objects.get(name="Covenant Formation")
        self.assertEqual(ritual.participation_rule, ParticipationRule.FORMATION)

        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        role_for_initiator = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        role_for_invitee = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={
                "name": "The Seeded Circle",
                "covenant_type": CovenantType.DURANCE,
                "sworn_objective": "Prove the seeded ritual dispatches.",
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
        self.assertEqual(covenant.name, "The Seeded Circle")
        self.assertEqual(covenant.covenant_type, CovenantType.DURANCE)


class SeededOrganizationInductionRitualDispatchTests(TestCase):
    """Prove the seed_magic_dev()-seeded "Organization Induction" Ritual row
    resolves and dispatches to induct_organization_member_via_session."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_magic_dev()

    def test_seeded_org_induction_ritual_fires_and_creates_membership(self) -> None:
        from world.societies.membership_services import induct_organization_member_via_session

        ritual = Ritual.objects.get(name="Organization Induction")
        self.assertEqual(ritual.participation_rule, ParticipationRule.BILATERAL)

        org = OrganizationFactory()
        leader_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=org,
            persona=leader_sheet.primary_persona,
            rank=1,
        )
        candidate_sheet = CharacterSheetFactory()

        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=leader_sheet,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.ORGANIZATION,
            ref_organization=org,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=leader_sheet,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate_sheet,
            state=ParticipantState.ACCEPTED,
        )

        membership = induct_organization_member_via_session(session=session)

        self.assertIsInstance(membership, OrganizationMembership)
        self.assertEqual(membership.persona, candidate_sheet.primary_persona)
        self.assertEqual(membership.organization, org)
        self.assertIsNone(membership.left_at)
