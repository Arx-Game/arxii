"""Telnet E2E: organization membership lifecycle journey (#1511).

Drives the full membership lifecycle through ``CmdOrg`` over the shared
``dispatch_player_action`` seam — the same REGISTRY path the web uses —
asserting DB state after each step and telnet feedback via ``caller.msg``.

Journey layout:
  1. ``org invite <person> in <org>`` — officer invites an outsider → PENDING INVITE.
  2. ``org join <org>``                — outsider accepts → active membership at base rank (tier 5).
  3. ``org promote <person> in <org>`` — officer promotes → rank tier 5 → 4.
  4. ``org demote <person> in <org>``  — officer demotes  → rank tier 4 → 5.
  5. ``org expel <person> in <org>``   — officer expels   → membership exiled (left_at + exiled_at).
  6. ``org leave <org>``               — a second member leaves voluntarily (left_at, no exiled_at).
  7. ``org apply <org>``               — a fresh outsider applies → PENDING APPLICATION.

All assertions run on the SQLite fast tier — no ``@tag("postgres")`` needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils import idmapper

from commands.organizations import CmdOrg
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
)
from world.societies.membership_services import (
    active_membership_for_persona,
    ensure_default_rank_ladder,
    promote_member,
)
from world.societies.models import OrganizationMembershipOffer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(label: str = "OrgE2ERoom") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_pc(db_key: str, room: object) -> tuple[object, object]:
    """Create a PC character + sheet in *room*. Returns (character, sheet).

    ``CharacterSheetFactory`` auto-creates a PRIMARY persona — the active face
    the org Actions resolve via ``active_persona_for_sheet``.
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    return char, sheet


def _run(caller: object, args: str = "") -> CmdOrg:
    """Instantiate CmdOrg wired to *caller*; does NOT call func().

    Mirrors the covenant e2e pattern: the caller wires ``cmd.caller.search``
    if needed, then calls ``cmd.func()``.
    """
    cmd = CmdOrg()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"org {args}".strip()
    cmd.cmdname = "org"
    caller.msg = MagicMock()
    return cmd


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------


class OrganizationLifecycleE2EJourneyTest(TestCase):
    """Full org membership lifecycle through telnet CmdOrg.

    invite → join → promote → demote → expel; plus a parallel leave + apply
    sub-journey to cover the voluntary-exit and application paths.
    """

    def setUp(self) -> None:
        idmapper.models.flush_cache()
        self.room = _make_room()

        # A generic (non-covenant) organization with a five-tier rank ladder.
        # OrganizationFactory auto-creates the default ladder via
        # ensure_default_rank_ladder when the first membership is created.
        self.org = OrganizationFactory(name="Thieves Guild")
        # Tier 1 = Leader (can_invite, can_kick, can_manage_ranks); tier 5 = Contact.
        # The ladder is lazily created on first join — touch it now so ranks exist.
        ensure_default_rank_ladder(self.org)

        # Officer — a tier-1 member with management perms.
        self.officer_char, self.officer_sheet = _make_pc("Officer", self.room)
        self.officer_persona = self.officer_sheet.primary_persona
        officer_rank = self.org.ranks.get(tier=1)
        self.officer_membership = OrganizationMembershipFactory(
            organization=self.org,
            persona=self.officer_persona,
            rank=officer_rank,
        )

        # Member — a tier-5 member who will be promoted/demoted/expelled.
        self.member_char, self.member_sheet = _make_pc("Member", self.room)
        self.member_persona = self.member_sheet.primary_persona
        base_rank = self.org.ranks.get(tier=5)
        self.member_membership = OrganizationMembershipFactory(
            organization=self.org,
            persona=self.member_persona,
            rank=base_rank,
        )

        # Outsider — not yet a member; will be invited + join.
        self.outsider_char, self.outsider_sheet = _make_pc("Outsider", self.room)
        self.outsider_persona = self.outsider_sheet.primary_persona

    # ------------------------------------------------------------------
    # invite → join
    # ------------------------------------------------------------------

    def test_invite_creates_pending_invite(self) -> None:
        """org invite <person> in <org> → PENDING OrganizationMembershipOffer (INVITE)."""
        cmd = _run(self.officer_char, f"invite Outsider in {self.org.name}")
        cmd.caller.search = MagicMock(return_value=self.outsider_char)
        cmd.func()

        offer = OrganizationMembershipOffer.objects.filter(
            organization=self.org,
            to_persona=self.outsider_persona,
            kind=OrganizationMembershipOffer.Kind.INVITE,
            status=OrganizationMembershipOffer.Status.PENDING,
        ).first()
        self.assertIsNotNone(offer, "invite should create a PENDING INVITE offer")
        self.assertEqual(offer.from_persona, self.officer_persona)
        self.officer_char.msg.assert_called()
        self.assertIn("invite", self.officer_char.msg.call_args[0][0].lower())

    def test_join_accepts_invite_and_creates_membership(self) -> None:
        """org join <org> → active membership at base rank (tier 5)."""
        # First, officer invites the outsider.
        cmd = _run(self.officer_char, f"invite Outsider in {self.org.name}")
        cmd.caller.search = MagicMock(return_value=self.outsider_char)
        cmd.func()

        # Outsider accepts via join.
        cmd = _run(self.outsider_char, f"join {self.org.name}")
        cmd.func()

        membership = active_membership_for_persona(self.org, self.outsider_persona)
        self.assertIsNotNone(membership, "join should create an active membership")
        self.assertEqual(membership.rank.tier, 5, "new member starts at base rank (tier 5)")

        # The offer is now ACCEPTED.
        offer = OrganizationMembershipOffer.objects.get(
            organization=self.org,
            to_persona=self.outsider_persona,
            kind=OrganizationMembershipOffer.Kind.INVITE,
        )
        self.assertEqual(offer.status, OrganizationMembershipOffer.Status.ACCEPTED)

        self.outsider_char.msg.assert_called()
        self.assertIn("join", self.outsider_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # promote → demote
    # ------------------------------------------------------------------

    def test_promote_moves_member_up_one_tier(self) -> None:
        """org promote <person> in <org> → rank tier 5 → 4."""
        cmd = _run(self.officer_char, f"promote Member in {self.org.name}")
        cmd.caller.search = MagicMock(return_value=self.member_char)
        cmd.func()

        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.rank.tier,
            4,
            "promote should move the member up one tier (5 → 4)",
        )
        self.officer_char.msg.assert_called()
        self.assertIn("promote", self.officer_char.msg.call_args[0][0].lower())

    def test_demote_moves_member_down_one_tier(self) -> None:
        """org demote <person> in <org> → rank tier 4 → 5.

        Starts from tier 4 (pre-promoted) to exercise the demote path.
        """
        # Pre-promote to tier 4 so demote has room to move down.
        promote_member(self.member_membership, self.officer_membership)

        cmd = _run(self.officer_char, f"demote Member in {self.org.name}")
        cmd.caller.search = MagicMock(return_value=self.member_char)
        cmd.func()

        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.rank.tier,
            5,
            "demote should move the member down one tier (4 → 5)",
        )
        self.officer_char.msg.assert_called()
        self.assertIn("demote", self.officer_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # expel
    # ------------------------------------------------------------------

    def test_expel_deactivates_membership_with_exile(self) -> None:
        """org expel <person> in <org> → membership left_at + exiled_at set."""
        cmd = _run(self.officer_char, f"expel Member in {self.org.name}")
        cmd.caller.search = MagicMock(return_value=self.member_char)
        cmd.func()

        self.member_membership.refresh_from_db()
        self.assertIsNotNone(self.member_membership.left_at, "expel sets left_at")
        self.assertIsNotNone(self.member_membership.exiled_at, "expel sets exiled_at")

        # No longer an active member.
        self.assertIsNone(
            active_membership_for_persona(self.org, self.member_persona),
            "expelled member should have no active membership",
        )
        self.officer_char.msg.assert_called()
        self.assertIn("expel", self.officer_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # leave (voluntary)
    # ------------------------------------------------------------------

    def test_leave_deactivates_membership_without_exile(self) -> None:
        """org leave <org> → membership left_at set, exiled_at null (voluntary)."""
        cmd = _run(self.member_char, f"leave {self.org.name}")
        cmd.func()

        self.member_membership.refresh_from_db()
        self.assertIsNotNone(self.member_membership.left_at, "leave sets left_at")
        self.assertIsNone(self.member_membership.exiled_at, "leave does NOT set exiled_at")

        self.assertIsNone(
            active_membership_for_persona(self.org, self.member_persona),
            "departed member should have no active membership",
        )
        self.member_char.msg.assert_called()
        self.assertIn("leave", self.member_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------

    def test_apply_creates_pending_application(self) -> None:
        """org apply <org> → PENDING OrganizationMembershipOffer (APPLICATION)."""
        cmd = _run(self.outsider_char, f"apply {self.org.name}")
        cmd.func()

        offer = OrganizationMembershipOffer.objects.filter(
            organization=self.org,
            from_persona=self.outsider_persona,
            kind=OrganizationMembershipOffer.Kind.APPLICATION,
            status=OrganizationMembershipOffer.Status.PENDING,
        ).first()
        self.assertIsNotNone(offer, "apply should create a PENDING APPLICATION offer")
        self.assertIsNone(offer.to_persona, "applications have no to_persona")

        self.outsider_char.msg.assert_called()
        self.assertIn("apply", self.outsider_char.msg.call_args[0][0].lower())

    # ------------------------------------------------------------------
    # hub
    # ------------------------------------------------------------------

    def test_bare_org_lists_subverbs(self) -> None:
        """Bare ``org`` (no args) prints the subverb hub."""
        cmd = _run(self.officer_char, "")
        cmd.func()
        self.officer_char.msg.assert_called()
        hub_msg = self.officer_char.msg.call_args[0][0]
        for verb in ("invite", "apply", "join", "leave", "promote", "demote", "expel"):
            self.assertIn(verb, hub_msg, f"hub should list '{verb}'")
