"""Tests for the custody API surfaces (#2001 Task 6).

Covers the two ViewSets Task 6 adds:

- ``StoryProtectedSubjectViewSet`` (``/api/protected-subjects/``): owner/lead-GM
  scoped CRUD, 404-not-filtered privacy, exactly-one-subject + story-ownership
  create-path validation.
- ``CustodyClearanceViewSet`` (``/api/custody-clearances/``): create
  (``request_clearance``) + the grant/deny/escalate/resolve/revoke lifecycle
  actions, each permission-gated per the Task 3 review's binding authority
  split (staff never grants/denies a PENDING request directly).

Model/service-level behavior (partial-unique constraint, notification
fan-out, ``check_subject_custody`` wiring) is already covered by
``test_protected_subjects.py`` and ``test_custody_clearance.py`` — this file
is API/permission/serializer behavior only, plus one E2E smoke test tying
the API to the custody-check seam.
"""

from datetime import timedelta
import json

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.narrative.models import NarrativeMessageDelivery
from world.stories.constants import CustodyClearanceStatus, CustodyScope, StakeSubjectKind
from world.stories.factories import (
    CustodyClearanceFactory,
    StoryFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.models import CustodyClearance
from world.stories.services.boundaries import _subject_identity
from world.stories.services.custody import check_subject_custody


def _post(client, url, data):
    return client.post(url, json.dumps(data), content_type="application/json")


def _patch(client, url, data):
    return client.patch(url, json.dumps(data), content_type="application/json")


class StoryProtectedSubjectViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_account = AccountFactory()
        cls.owner_gm = GMProfileFactory(account=cls.owner_account)
        cls.table = GMTableFactory(gm=cls.owner_gm)
        cls.story = StoryFactory(owners=[cls.owner_account], primary_table=cls.table)

        # A Lead GM who "leads" (primary_table.gm) but is NOT in story.owners.
        cls.lead_only_account = AccountFactory()
        cls.lead_only_gm = GMProfileFactory(account=cls.lead_only_account)
        cls.lead_only_table = GMTableFactory(gm=cls.lead_only_gm)
        cls.lead_only_story = StoryFactory(owners=[], primary_table=cls.lead_only_table)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.outsider_account = AccountFactory()

        cls.sheet = CharacterSheetFactory()
        cls.subject = StoryProtectedSubjectFactory(story=cls.story, subject_sheet=cls.sheet)

    def test_owner_can_list_and_retrieve(self):
        self.client.force_authenticate(user=self.owner_account)
        resp = self.client.get(reverse("storyprotectedsubject-list"))
        assert resp.status_code == status.HTTP_200_OK
        assert self.subject.pk in [row["id"] for row in resp.data["results"]]

        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = self.client.get(detail_url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["notes"] == self.subject.notes

    def test_lead_gm_without_owner_row_sees_their_story(self):
        """ "owns/leads" — a Lead GM not in story.owners still gets access."""
        subj = StoryProtectedSubjectFactory(
            story=self.lead_only_story, subject_sheet=CharacterSheetFactory()
        )
        self.client.force_authenticate(user=self.lead_only_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": subj.pk})
        resp = self.client.get(detail_url)
        assert resp.status_code == status.HTTP_200_OK

    def test_outsider_gets_404_not_403_on_retrieve(self):
        self.client.force_authenticate(user=self.outsider_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = self.client.get(detail_url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_outsider_list_excludes_row_entirely(self):
        self.client.force_authenticate(user=self.outsider_account)
        resp = self.client.get(reverse("storyprotectedsubject-list"))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["results"] == []

    def test_outsider_cannot_patch_or_delete(self):
        self.client.force_authenticate(user=self.outsider_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = _patch(self.client, detail_url, {"notes": "hacked"})
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        resp = self.client.delete(detail_url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_staff_can_access_any_subject(self):
        self.client.force_authenticate(user=self.staff_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = self.client.get(detail_url)
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_create(self):
        self.client.force_authenticate(user=self.owner_account)
        sheet = CharacterSheetFactory()
        resp = _post(
            self.client,
            reverse("storyprotectedsubject-list"),
            {
                "story": self.story.pk,
                "subject_kind": StakeSubjectKind.NPC_FATE,
                "subject_sheet": sheet.pk,
            },
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data

    def test_create_rejects_foreign_story(self):
        """DRF never calls has_object_permission on create — the serializer must gate it."""
        self.client.force_authenticate(user=self.outsider_account)
        sheet = CharacterSheetFactory()
        resp = _post(
            self.client,
            reverse("storyprotectedsubject-list"),
            {
                "story": self.story.pk,
                "subject_kind": StakeSubjectKind.NPC_FATE,
                "subject_sheet": sheet.pk,
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "story" in resp.data

    def test_create_rejects_zero_subjects(self):
        self.client.force_authenticate(user=self.owner_account)
        resp = _post(
            self.client,
            reverse("storyprotectedsubject-list"),
            {"story": self.story.pk, "subject_kind": StakeSubjectKind.NPC_FATE},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_rejects_two_subjects(self):
        self.client.force_authenticate(user=self.owner_account)
        sheet = CharacterSheetFactory()
        resp = _post(
            self.client,
            reverse("storyprotectedsubject-list"),
            {
                "story": self.story.pk,
                "subject_kind": StakeSubjectKind.NPC_FATE,
                "subject_sheet": sheet.pk,
                "subject_label": "Also this",
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_by_story_subject_kind_is_active(self):
        self.client.force_authenticate(user=self.owner_account)
        inactive = StoryProtectedSubjectFactory(
            story=self.story,
            subject_sheet=None,
            subject_label="Other",
            subject_kind=StakeSubjectKind.CUSTOM,
            is_active=False,
        )
        resp = self.client.get(reverse("storyprotectedsubject-list"), {"is_active": "false"})
        ids = [row["id"] for row in resp.data["results"]]
        assert inactive.pk in ids
        assert self.subject.pk not in ids

    def test_delete_soft_deactivates_not_hard_deletes(self):
        """Task 7 review Fix 1: DELETE must never hard-delete story-significant data —
        the row and its CustodyClearance decision trail must both survive, mirroring
        telnet's `story protect ... remove`."""
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=GMProfileFactory(),
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        self.client.force_authenticate(user=self.owner_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = self.client.delete(detail_url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        self.subject.refresh_from_db()
        assert self.subject.is_active is False
        assert CustodyClearance.objects.filter(protected_subject=self.subject).exists()

    def test_deactivated_subject_no_longer_blocks_custody(self):
        """A DELETE-deactivated subject stops blocking check_subject_custody — the
        is_active filter in ``_matching_protections`` covers the delete-path row too."""
        subject_identity = _subject_identity(
            StakeSubjectKind.NPC_FATE, self.sheet.pk, None, None, None, ""
        )
        before = check_subject_custody(
            subject_identity=subject_identity,
            actor_account=self.outsider_account,
            scope=CustodyScope.APPEAR,
        )
        assert not before.allowed

        self.client.force_authenticate(user=self.owner_account)
        detail_url = reverse("storyprotectedsubject-detail", kwargs={"pk": self.subject.pk})
        resp = self.client.delete(detail_url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        after = check_subject_custody(
            subject_identity=subject_identity,
            actor_account=self.outsider_account,
            scope=CustodyScope.APPEAR,
        )
        assert after.allowed


class CustodyClearanceCreateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.custodian_account = AccountFactory()
        cls.custodian_gm = GMProfileFactory(account=cls.custodian_account)
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.protecting_story = StoryFactory(owners=[cls.custodian_account], primary_table=cls.table)
        cls.subject = StoryProtectedSubjectFactory(
            story=cls.protecting_story, subject_sheet=CharacterSheetFactory()
        )

        cls.requester_account = AccountFactory()
        cls.requester_gm = GMProfileFactory(account=cls.requester_account)

        cls.non_gm_account = AccountFactory()

    def test_gm_can_request_clearance(self):
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": self.subject.pk, "scope": CustodyScope.APPEAR},
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert len(resp.data) == 1
        assert resp.data[0]["requested_by"] == self.requester_gm.pk
        assert resp.data[0]["status"] == CustodyClearanceStatus.PENDING

    def test_non_gm_account_rejected(self):
        """IsGMProfile gates create (Task 6 review Fix 2) — 403, not a 400 serializer error."""
        self.client.force_authenticate(user=self.non_gm_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": self.subject.pk, "scope": CustodyScope.APPEAR},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_live_request_rejected(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": self.subject.pk, "scope": CustodyScope.APPEAR},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_and_inactive_subject_give_identical_error_shape(self):
        """No-oracle: an inactive protection and a nonexistent pk must be indistinguishable."""
        inactive_subject = StoryProtectedSubjectFactory(
            story=self.protecting_story, subject_sheet=CharacterSheetFactory(), is_active=False
        )
        self.client.force_authenticate(user=self.requester_account)

        resp_missing = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": 9_999_999, "scope": CustodyScope.APPEAR},
        )
        resp_inactive = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": inactive_subject.pk, "scope": CustodyScope.APPEAR},
        )
        assert resp_missing.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_inactive.status_code == status.HTTP_400_BAD_REQUEST
        # Same field, same DRF error code (the pk itself differs, so the message
        # text necessarily embeds a different pk — the no-oracle guarantee is
        # that the shape/code is identical, not the pk-bearing prose).
        assert set(resp_missing.data) == {"protected_subject"}
        assert set(resp_inactive.data) == {"protected_subject"}
        assert resp_missing.data["protected_subject"][0].code == "does_not_exist"
        assert resp_inactive.data["protected_subject"][0].code == "does_not_exist"


def _gm_with_notification_sheet(gm_profile):
    """Give gm_profile's account a character with a resolvable primary-persona sheet."""
    char = CharacterFactory()
    char.db_account = gm_profile.account
    char.save()
    return CharacterSheetFactory(character=char)


class CustodyClearanceIdentityRequestTests(APITestCase):
    """Identity-based clearance requests (#2001 Task 6 review Fix 4).

    A blocked outsider GM only ever learns the custodian's username, never the
    ``protected_subject`` pk (see ``CustodyVerdict``) — these cover the
    ``subject_kind`` + typed-pointer/label alternative to the pk path.
    """

    @classmethod
    def setUpTestData(cls):
        cls.requester_account = AccountFactory()
        cls.requester_gm = GMProfileFactory(account=cls.requester_account)
        cls.non_gm_account = AccountFactory()

        cls.custodian_account = AccountFactory()
        cls.custodian_gm = GMProfileFactory(account=cls.custodian_account)
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.protecting_story = StoryFactory(owners=[cls.custodian_account], primary_table=cls.table)

        cls.sheet = CharacterSheetFactory()
        cls.subject = StoryProtectedSubjectFactory(
            story=cls.protecting_story, subject_sheet=cls.sheet
        )

    def _identity_payload(self, **overrides):
        payload = {
            "subject_kind": StakeSubjectKind.NPC_FATE,
            "subject_sheet": self.sheet.pk,
            "scope": CustodyScope.APPEAR,
        }
        payload.update(overrides)
        return payload

    def test_identity_path_happy_single_custodian(self):
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(self.client, reverse("custodyclearance-list"), self._identity_payload())
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert len(resp.data) == 1
        assert resp.data[0]["protected_subject"] == self.subject.pk
        assert resp.data[0]["requested_by"] == self.requester_gm.pk
        assert resp.data[0]["status"] == CustodyClearanceStatus.PENDING

    def test_identity_path_multi_protection_fan_out_notifies_both_custodians(self):
        """Two stories independently protect the same NPC -> two clearance rows,
        both custodians notified."""
        other_custodian_account = AccountFactory()
        other_custodian_gm = GMProfileFactory(account=other_custodian_account)
        other_table = GMTableFactory(gm=other_custodian_gm)
        other_story = StoryFactory(owners=[other_custodian_account], primary_table=other_table)
        other_subject = StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.sheet)

        custodian_sheet = _gm_with_notification_sheet(self.custodian_gm)
        other_custodian_sheet = _gm_with_notification_sheet(other_custodian_gm)

        self.client.force_authenticate(user=self.requester_account)
        resp = _post(self.client, reverse("custodyclearance-list"), self._identity_payload())
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert len(resp.data) == 2
        subject_ids = {row["protected_subject"] for row in resp.data}
        assert subject_ids == {self.subject.pk, other_subject.pk}

        recipient_ids = set(
            NarrativeMessageDelivery.objects.all().values_list(
                "recipient_character_sheet_id", flat=True
            )
        )
        assert custodian_sheet.pk in recipient_ids
        assert other_custodian_sheet.pk in recipient_ids

    def test_identity_no_match_error_shape_identical_to_pk_no_match(self):
        """No-oracle guarantee extends to the identity path (Fix 4): an identity
        with no matching active protection gets the exact does_not_exist shape."""
        unrelated_sheet = CharacterSheetFactory()
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            self._identity_payload(subject_sheet=unrelated_sheet.pk),
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert set(resp.data) == {"protected_subject"}
        assert resp.data["protected_subject"][0].code == "does_not_exist"

    def test_identity_path_duplicate_request_reported_as_already_pending(self):
        """A live request for the same (subject, requester, scope) is skipped
        (not re-created, not a 500) and reported back as-is."""
        existing = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester_gm,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(self.client, reverse("custodyclearance-list"), self._identity_payload())
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert len(resp.data) == 1
        assert resp.data[0]["id"] == existing.pk
        assert CustodyClearance.objects.filter(protected_subject=self.subject).count() == 1

    def test_exactly_one_of_paths_rejects_both_pk_and_identity(self):
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {**self._identity_payload(), "protected_subject": self.subject.pk},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "non_field_errors" in resp.data

    def test_exactly_one_of_paths_rejects_neither_pk_nor_identity(self):
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(self.client, reverse("custodyclearance-list"), {"scope": CustodyScope.APPEAR})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "non_field_errors" in resp.data

    def test_identity_path_requires_exactly_one_subject_field(self):
        """subject_kind alone (no typed pointer/label) is not a valid identity."""
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"subject_kind": StakeSubjectKind.NPC_FATE, "scope": CustodyScope.APPEAR},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "non_field_errors" in resp.data

    def test_non_gm_account_rejected_on_identity_path(self):
        self.client.force_authenticate(user=self.non_gm_account)
        resp = _post(self.client, reverse("custodyclearance-list"), self._identity_payload())
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class CustodyClearanceLifecycleTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.custodian_account = AccountFactory()
        cls.custodian_gm = GMProfileFactory(account=cls.custodian_account)
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.protecting_story = StoryFactory(owners=[cls.custodian_account], primary_table=cls.table)
        cls.subject = StoryProtectedSubjectFactory(
            story=cls.protecting_story, subject_sheet=CharacterSheetFactory()
        )

        cls.requester_account = AccountFactory()
        cls.requester_gm = GMProfileFactory(account=cls.requester_account)

        cls.staff_account = AccountFactory(is_staff=True)

        cls.outsider_gm_account = AccountFactory()
        cls.outsider_gm = GMProfileFactory(account=cls.outsider_gm_account)

    def _pending_clearance(self, **overrides):
        kwargs = {
            "protected_subject": self.subject,
            "requested_by": self.requester_gm,
            "scope": CustodyScope.APPEAR,
            "status": CustodyClearanceStatus.PENDING,
        }
        kwargs.update(overrides)
        return CustodyClearanceFactory(**kwargs)

    # -- grant --------------------------------------------------------

    def test_custodian_can_grant(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["status"] == CustodyClearanceStatus.GRANTED

    def test_staff_cannot_grant_pending(self):
        """Binding design decision: staff act only through escalate -> resolve."""
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_requester_cannot_grant_own_request(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unrelated_gm_cannot_grant(self):
        """A GM with no stake in this clearance can't even see it — 404, not 403.

        Mirrors the 404-not-filtered privacy posture: get_queryset already
        excludes the row for a GM who is neither the requester, the
        custodian, nor staff, so the object 404s before permission checks
        even run.
        """
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.outsider_gm_account)
        resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_grant_on_non_pending_rejected(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.GRANTED)
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # -- deny ---------------------------------------------------------

    def test_custodian_can_deny(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-deny", kwargs={"pk": clearance.pk}),
            {"response_note": "not now"},
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["status"] == CustodyClearanceStatus.DENIED

    def test_staff_cannot_deny_pending(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(self.client, reverse("custodyclearance-deny", kwargs={"pk": clearance.pk}), {})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    # -- escalate -------------------------------------------------------

    def test_requester_can_escalate_denied(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.DENIED)
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client, reverse("custodyclearance-escalate", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["status"] == CustodyClearanceStatus.ESCALATED

    def test_custodian_cannot_escalate(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.DENIED)
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client, reverse("custodyclearance-escalate", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_cannot_escalate(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.DENIED)
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(
            self.client, reverse("custodyclearance-escalate", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_fresh_pending_not_eligible_for_escalation(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client, reverse("custodyclearance-escalate", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_stale_pending_eligible_for_escalation(self):
        clearance = self._pending_clearance()
        # queryset.update() bypasses idmapper's identity-map cache (the cached
        # instance would keep stale in-memory created_at) — mutate through the
        # same object + save() instead, which auto_now_add allows on update.
        clearance.created_at = timezone.now() - timedelta(days=8)
        clearance.save(update_fields=["created_at"])
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client, reverse("custodyclearance-escalate", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data

    # -- resolve --------------------------------------------------------

    def test_staff_can_resolve_escalated(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.ESCALATED)
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-resolve", kwargs={"pk": clearance.pk}),
            {"grant": True, "response_note": "staff call"},
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["status"] == CustodyClearanceStatus.GRANTED

    def test_custodian_cannot_resolve(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.ESCALATED)
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-resolve", kwargs={"pk": clearance.pk}),
            {"grant": True},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_requester_cannot_resolve(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.ESCALATED)
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-resolve", kwargs={"pk": clearance.pk}),
            {"grant": True},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_resolve_non_escalated_rejected(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(
            self.client,
            reverse("custodyclearance-resolve", kwargs={"pk": clearance.pk}),
            {"grant": True},
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # -- revoke -----------------------------------------------------------

    def test_custodian_can_revoke_granted(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.GRANTED)
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client, reverse("custodyclearance-revoke", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["revoked_at"] is not None

    def test_staff_can_revoke_granted(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.GRANTED)
        self.client.force_authenticate(user=self.staff_account)
        resp = _post(
            self.client, reverse("custodyclearance-revoke", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data

    def test_requester_cannot_revoke(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.GRANTED)
        self.client.force_authenticate(user=self.requester_account)
        resp = _post(
            self.client, reverse("custodyclearance-revoke", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_revoke_non_granted_rejected(self):
        clearance = self._pending_clearance()
        self.client.force_authenticate(user=self.custodian_account)
        resp = _post(
            self.client, reverse("custodyclearance-revoke", kwargs={"pk": clearance.pk}), {}
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # -- list scoping + escalation queue filter --------------------------

    def test_list_scoping_and_escalated_filter(self):
        own_request = self._pending_clearance()
        # Different scope — same (protected_subject, requested_by) pair would
        # collide with the partial-unique live-clearance constraint otherwise.
        escalated = self._pending_clearance(
            scope=CustodyScope.HARM, status=CustodyClearanceStatus.ESCALATED
        )

        # Requester sees their own requests.
        self.client.force_authenticate(user=self.requester_account)
        resp = self.client.get(reverse("custodyclearance-list"))
        ids = {row["id"] for row in resp.data["results"]}
        assert {own_request.pk, escalated.pk} <= ids

        # Unrelated GM sees nothing.
        self.client.force_authenticate(user=self.outsider_gm_account)
        resp = self.client.get(reverse("custodyclearance-list"))
        assert resp.data["results"] == []

        # Custodian (protecting story owner) sees requests targeting their subject.
        self.client.force_authenticate(user=self.custodian_account)
        resp = self.client.get(reverse("custodyclearance-list"))
        ids = {row["id"] for row in resp.data["results"]}
        assert {own_request.pk, escalated.pk} <= ids

        # Staff sees all, and the status=escalated filter narrows to the queue.
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.get(reverse("custodyclearance-list"), {"status": "escalated"})
        ids = {row["id"] for row in resp.data["results"]}
        assert escalated.pk in ids
        assert own_request.pk not in ids


class CustodyClearanceE2ETests(APITestCase):
    """POST request -> POST grant via the API, then verify check_subject_custody allows."""

    @classmethod
    def setUpTestData(cls):
        cls.custodian_account = AccountFactory()
        cls.custodian_gm = GMProfileFactory(account=cls.custodian_account)
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.protecting_story = StoryFactory(owners=[cls.custodian_account], primary_table=cls.table)
        cls.sheet = CharacterSheetFactory()
        cls.subject = StoryProtectedSubjectFactory(
            story=cls.protecting_story, subject_sheet=cls.sheet
        )
        cls.subject_identity = _subject_identity(
            StakeSubjectKind.NPC_FATE, cls.sheet.pk, None, None, None, ""
        )

        cls.requester_account = AccountFactory()
        cls.requester_gm = GMProfileFactory(account=cls.requester_account)

    def test_request_then_grant_unlocks_custody(self):
        before = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=self.requester_account,
            scope=CustodyScope.APPEAR,
        )
        assert not before.allowed

        self.client.force_authenticate(user=self.requester_account)
        create_resp = _post(
            self.client,
            reverse("custodyclearance-list"),
            {"protected_subject": self.subject.pk, "scope": CustodyScope.APPEAR},
        )
        assert create_resp.status_code == status.HTTP_201_CREATED, create_resp.data
        clearance_id = create_resp.data[0]["id"]

        self.client.force_authenticate(user=self.custodian_account)
        grant_resp = _post(
            self.client, reverse("custodyclearance-grant", kwargs={"pk": clearance_id}), {}
        )
        assert grant_resp.status_code == status.HTTP_200_OK, grant_resp.data

        after = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=self.requester_account,
            scope=CustodyScope.APPEAR,
        )
        assert after.allowed
