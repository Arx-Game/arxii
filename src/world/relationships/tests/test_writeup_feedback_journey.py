"""E2E journey test: writeup kudos (telnet) + complaint (web) parity (#1537).

Journey:
1. Author A writes a SHARED update about subject B.
2. Subject B commends via the telnet path (CmdRelationship "kudos u<pk>").
   → WriteupKudos row created; author A's KudosPointsData.total_earned rises by
     WRITEUP_KUDOS_AMOUNT.
3. B commends again → rejected (still one row, total unchanged).
4. Bystander C files a complaint via the web path (POST /complaint/).
   → WriteupComplaint row exists with resolved=False.
5. The read serializer for the update exposes kudos_count/viewer_has_kudosed
   but NO complaint field — complaints are staff-only.

Deliberately exercises BOTH surfaces (telnet for kudos, web for complaint)
converging on the same models to prove parity.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from django.db.models import Count, Exists, OuterRef
from django.test import TestCase
from evennia.utils.idmapper.models import flush_cache
from rest_framework.test import APIRequestFactory, force_authenticate

from commands.relationships import CmdRelationship
from world.progression.factories import KudosSourceCategoryFactory
from world.progression.models import KudosPointsData
from world.relationships.constants import (
    RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    WRITEUP_KUDOS_AMOUNT,
    UpdateVisibility,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import RelationshipUpdate, WriteupComplaint, WriteupKudos
from world.relationships.serializers import RelationshipUpdateSerializer
from world.relationships.views import RelationshipUpdateViewSet
from world.roster.factories import RosterTenureFactory


def _make_cmd(caller: Any, args: str = "") -> CmdRelationship:
    """Build a CmdRelationship wired to ``caller`` with the given arg string."""
    cmd = CmdRelationship()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"relationship {args}".strip()
    cmd.cmdname = "relationship"
    return cmd


def _puppet_user(character):
    """Fake authenticated user whose ``puppet`` is ``character``.

    Sets ``pk`` to ``character.db_account_id`` (typically None in factory-built
    characters) to satisfy ``_resolve_actor``'s identity check: the comparison
    ``sheet.character.db_account_id != request.user.pk`` evaluates to
    ``None != None`` → False (passes) when both are None.

    The actual account used by ``get_account_for_character`` is resolved via
    RosterTenure, independently of this pk.
    """
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


def _make_linked_account(character_sheet):
    """Create a RosterTenure linking character_sheet.character to a fresh account."""
    tenure = RosterTenureFactory(roster_entry__character_sheet__character=character_sheet.character)
    return tenure.player_data.account


def _annotated_update(update_pk: int, account_pk: int) -> RelationshipUpdate:
    """Fetch the update annotated with kudos_count and viewer_has_kudosed."""
    return RelationshipUpdate.objects.annotate(
        kudos_count=Count("writeupkudos_set"),
        viewer_has_kudosed=Exists(
            WriteupKudos.objects.filter(account_id=account_pk, update=OuterRef("pk"))
        ),
    ).get(pk=update_pk)


class WriteupFeedbackJourneyTest(TestCase):
    """End-to-end journey: telnet kudos + web complaint converge on the same models.

    Setup: author A posts a SHARED update about subject B; bystander C is unrelated.
    All characters are linked to accounts via RosterTenure so get_account_for_character
    resolves on both surfaces.
    """

    def setUp(self) -> None:
        flush_cache()

        # Relationship: author A (source) wrote about subject B (target).
        rel = CharacterRelationshipFactory()
        self.author_sheet = rel.source
        self.subject_sheet = rel.target

        # Link both to accounts so get_account_for_character resolves.
        self.author_account = _make_linked_account(self.author_sheet)
        self.subject_account = _make_linked_account(self.subject_sheet)

        # Subject character used as the telnet caller; needs msg() mock.
        self.subject_char = self.subject_sheet.character
        self.subject_char.msg = MagicMock()

        # A SHARED update authored by A about B (SHARED is the model default).
        self.update = RelationshipUpdateFactory(
            relationship=rel,
            author=self.author_sheet,
            visibility=UpdateVisibility.SHARED,
        )

        # Bystander C — unrelated character + account for the web complaint step.
        bystander_rel = CharacterRelationshipFactory()
        self.bystander_sheet = bystander_rel.source
        self.bystander_account = _make_linked_account(self.bystander_sheet)
        self.bystander_char = self.bystander_sheet.character

        # Seed the KudosSourceCategory so award_kudos fires without a warn-skip.
        KudosSourceCategoryFactory(name=RELATIONSHIP_WRITEUP_KUDOS_CATEGORY)

        self.api_factory = APIRequestFactory()

    # ── helpers ────────────────────────────────────────────────────────────

    def _post_complaint(self, character, payload: dict):
        """POST to the complaint endpoint as the given character."""
        url = "/api/relationships/relationship-updates/complaint/"
        request = self.api_factory.post(url, payload, format="json")
        force_authenticate(request, user=_puppet_user(character))
        view = RelationshipUpdateViewSet.as_view({"post": "complaint"})
        return view(request)

    # ── the journey ────────────────────────────────────────────────────────

    def test_kudos_and_complaint_journey(self) -> None:
        """Full journey: telnet kudos (once and duplicate) + web complaint + read parity."""

        # ── Step 2: subject B commends via telnet ──────────────────────────
        _make_cmd(self.subject_char, f"kudos u{self.update.pk}").func()

        # A WriteupKudos row was created for the subject's account.
        self.assertTrue(
            WriteupKudos.objects.filter(account=self.subject_account, update=self.update).exists(),
            "WriteupKudos row must exist after the first telnet commendation.",
        )
        # Author A received WRITEUP_KUDOS_AMOUNT kudos points.
        points = KudosPointsData.objects.get(account=self.author_account)
        self.assertEqual(
            points.total_earned,
            WRITEUP_KUDOS_AMOUNT,
            f"Author's total_earned must equal {WRITEUP_KUDOS_AMOUNT} after one commendation.",
        )

        # ── Step 3: duplicate commend rejected ─────────────────────────────
        _make_cmd(self.subject_char, f"kudos u{self.update.pk}").func()

        # Still exactly one WriteupKudos row — no duplicate created.
        self.assertEqual(
            WriteupKudos.objects.filter(account=self.subject_account, update=self.update).count(),
            1,
            "Duplicate commendation must not create a second WriteupKudos row.",
        )
        # Author's total_earned is unchanged — no second award fired.
        points.refresh_from_db()
        self.assertEqual(
            points.total_earned,
            WRITEUP_KUDOS_AMOUNT,
            "Duplicate commendation must not award additional kudos points.",
        )

        # ── Step 4: bystander C files a complaint via the web API ──────────
        resp = self._post_complaint(
            self.bystander_char,
            {
                "writeup_type": "update",
                "writeup_id": self.update.pk,
                "reason": "This writeup fabricates events that did not occur.",
            },
        )
        self.assertEqual(
            resp.status_code,
            200,
            f"Complaint POST must return 200; got {resp.status_code}: {resp.data}",
        )
        self.assertTrue(resp.data["success"])

        # A WriteupComplaint row exists with resolved=False.
        self.assertTrue(
            WriteupComplaint.objects.filter(
                complainant=self.bystander_account, update=self.update, resolved=False
            ).exists(),
            "WriteupComplaint row must exist and be unresolved after the web complaint.",
        )

        # ── Step 5: read serializer — kudos visible, complaints absent ──────
        obj = _annotated_update(self.update.pk, self.subject_account.pk)
        request_ctx = SimpleNamespace(user=SimpleNamespace(pk=self.subject_account.pk))
        s = RelationshipUpdateSerializer(obj, context={"request": request_ctx})
        data = s.data

        # kudos_count reflects the one commendation.
        self.assertEqual(
            data["kudos_count"],
            1,
            "Read serializer must expose kudos_count=1 after one commendation.",
        )
        # viewer_has_kudosed is True for the commending subject.
        self.assertTrue(
            data["viewer_has_kudosed"],
            "Read serializer must expose viewer_has_kudosed=True for the commending subject.",
        )
        # No complaint data leaks into the player-facing read serializer.
        fields = set(data.keys())
        for forbidden in (
            "complaints",
            "complaint_count",
            "writeupcomplaints",
            "writeupcomplaints_count",
        ):
            self.assertNotIn(
                forbidden,
                fields,
                f"Complaint field '{forbidden}' must not appear in the read serializer.",
            )
