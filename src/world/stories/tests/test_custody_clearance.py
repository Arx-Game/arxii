"""Tests for CustodyClearance model + lifecycle services + notifications (#2001).

Covers: the partial-unique live-clearance constraint, every lifecycle
transition (including illegal ones — typed guard errors), the
``check_subject_custody`` E2E wiring through ``active_clearance_exists``, and
notification fan-out (asserting ``NarrativeMessage``/delivery rows land on
the right recipient).
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import (
    CUSTODY_ESCALATION_STALE_DAYS,
    CustodyClearanceStatus,
    CustodyScope,
    StakeSubjectKind,
)
from world.stories.exceptions import CustodyClearanceAuthorityError, CustodyClearanceStateError
from world.stories.factories import (
    CustodyClearanceFactory,
    StoryFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.services.boundaries import _subject_identity
from world.stories.services.custody import check_subject_custody
from world.stories.services.custody_clearance import (
    active_clearance_exists,
    deny_clearance,
    escalate_clearance,
    grant_clearance,
    request_clearance,
    resolve_escalation,
    revoke_clearance,
)
from world.stories.types import StoryStatus


def _gm_with_notification_sheet(gm_profile):
    """Give gm_profile's account a character with a resolvable primary-persona sheet."""
    char = CharacterFactory()
    char.db_account = gm_profile.account
    char.save()
    return CharacterSheetFactory(character=char)


def _account_playing(character_sheet):
    """An AccountDB currently playing character_sheet's character (live tenure)."""
    entry = RosterEntryFactory(character_sheet=character_sheet)
    player_data = PlayerDataFactory()
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return player_data.account


class CustodyClearanceModelTests(TestCase):
    def setUp(self):
        self.subject = StoryProtectedSubjectFactory()
        self.requester = GMProfileFactory()

    def test_two_live_clearances_same_key_rejected(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustodyClearanceFactory(
                protected_subject=self.subject,
                requested_by=self.requester,
                scope=CustodyScope.APPEAR,
                status=CustodyClearanceStatus.ESCALATED,
            )

    def test_second_live_clearance_different_scope_allowed(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        other = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.PENDING,
        )
        assert other.pk is not None

    def test_resolved_status_does_not_block_new_request(self):
        """A GRANTED/DENIED clearance is not "live" — a fresh request at the same
        key may exist alongside it (partial unique only covers PENDING/ESCALATED)."""
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.DENIED,
        )
        new = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.PENDING,
        )
        assert new.pk is not None


class RequestClearanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.subject = StoryProtectedSubjectFactory(story=cls.story)
        cls.requester = GMProfileFactory()

    def test_creates_pending_clearance(self):
        clearance = request_clearance(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            message="Please let my scene touch this NPC.",
        )
        assert clearance.pk is not None
        assert clearance.status == CustodyClearanceStatus.PENDING
        assert clearance.scope == CustodyScope.HARM
        assert clearance.message == "Please let my scene touch this NPC."

    def test_rejects_second_live_request_same_key(self):
        request_clearance(
            protected_subject=self.subject, requested_by=self.requester, scope=CustodyScope.HARM
        )
        with self.assertRaises(CustodyClearanceStateError):
            request_clearance(
                protected_subject=self.subject,
                requested_by=self.requester,
                scope=CustodyScope.HARM,
            )

    def test_notifies_custodian_gm(self):
        custodian_sheet = _gm_with_notification_sheet(self.custodian_gm)
        count_before = NarrativeMessage.objects.count()
        request_clearance(
            protected_subject=self.subject, requested_by=self.requester, scope=CustodyScope.HARM
        )
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.requester.account.username in msg.body
        assert CustodyScope.HARM in msg.body
        deliveries = NarrativeMessageDelivery.objects.filter(message=msg)
        recipient_sheet_ids = set(deliveries.values_list("recipient_character_sheet_id", flat=True))
        assert custodian_sheet.pk in recipient_sheet_ids

    def test_no_crash_when_custodian_has_no_notification_target(self):
        # custodian_gm has no character/sheet — must skip gracefully.
        count_before = NarrativeMessage.objects.count()
        clearance = request_clearance(
            protected_subject=self.subject, requested_by=self.requester, scope=CustodyScope.APPEAR
        )
        assert clearance.pk is not None
        assert NarrativeMessage.objects.count() == count_before

    def test_orphaned_protecting_story_notifies_no_one(self):
        orphan_subject = StoryProtectedSubjectFactory(story=StoryFactory(primary_table=None))
        count_before = NarrativeMessage.objects.count()
        clearance = request_clearance(
            protected_subject=orphan_subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
        )
        assert clearance.pk is not None
        assert NarrativeMessage.objects.count() == count_before


class GrantDenyClearanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.subject = StoryProtectedSubjectFactory(story=cls.story)
        cls.requester = GMProfileFactory()

    def _pending_clearance(self, **kwargs):
        defaults = {
            "protected_subject": self.subject,
            "requested_by": self.requester,
            "scope": CustodyScope.HARM,
            "status": CustodyClearanceStatus.PENDING,
        }
        defaults.update(kwargs)
        return CustodyClearanceFactory(**defaults)

    def test_grant_sets_granted_status_and_fields(self):
        clearance = self._pending_clearance()
        updated = grant_clearance(
            clearance, granted_by=self.custodian_gm, response_note="Go ahead."
        )
        assert updated.status == CustodyClearanceStatus.GRANTED
        assert updated.granted_by_id == self.custodian_gm.pk
        assert updated.response_note == "Go ahead."
        assert updated.resolved_at is not None

    def test_grant_rejects_non_custodian(self):
        clearance = self._pending_clearance()
        outsider_gm = GMProfileFactory()
        with self.assertRaises(CustodyClearanceAuthorityError):
            grant_clearance(clearance, granted_by=outsider_gm)

    def test_grant_rejects_non_pending_status(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.DENIED)
        with self.assertRaises(CustodyClearanceStateError):
            grant_clearance(clearance, granted_by=self.custodian_gm)

    def test_deny_sets_denied_status_and_fields(self):
        clearance = self._pending_clearance()
        updated = deny_clearance(clearance, denied_by=self.custodian_gm, response_note="No.")
        assert updated.status == CustodyClearanceStatus.DENIED
        assert updated.granted_by_id == self.custodian_gm.pk
        assert updated.response_note == "No."
        assert updated.resolved_at is not None

    def test_deny_rejects_non_custodian(self):
        clearance = self._pending_clearance()
        outsider_gm = GMProfileFactory()
        with self.assertRaises(CustodyClearanceAuthorityError):
            deny_clearance(clearance, denied_by=outsider_gm)

    def test_deny_rejects_non_pending_status(self):
        clearance = self._pending_clearance(status=CustodyClearanceStatus.GRANTED)
        with self.assertRaises(CustodyClearanceStateError):
            deny_clearance(clearance, denied_by=self.custodian_gm)

    def test_grant_notifies_requester(self):
        requester_sheet = _gm_with_notification_sheet(self.requester)
        clearance = self._pending_clearance()
        count_before = NarrativeMessage.objects.count()
        grant_clearance(clearance, granted_by=self.custodian_gm)
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.custodian_gm.account.username in msg.body
        deliveries = NarrativeMessageDelivery.objects.filter(message=msg)
        recipient_ids = set(deliveries.values_list("recipient_character_sheet_id", flat=True))
        assert requester_sheet.pk in recipient_ids

    def test_deny_notifies_requester(self):
        _gm_with_notification_sheet(self.requester)
        clearance = self._pending_clearance()
        count_before = NarrativeMessage.objects.count()
        deny_clearance(clearance, denied_by=self.custodian_gm)
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.custodian_gm.account.username in msg.body


class EscalateClearanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.subject = StoryProtectedSubjectFactory(story=cls.story)
        cls.requester = GMProfileFactory()

    def test_escalate_denied_clearance(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.DENIED,
        )
        updated = escalate_clearance(clearance)
        assert updated.status == CustodyClearanceStatus.ESCALATED

    def test_escalate_stale_pending_clearance(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.PENDING,
        )
        # Mutate the identity-mapped instance directly and save() rather than
        # queryset.update() + refresh_from_db(): the idmapper cache would hand
        # refresh_from_db() the SAME cached Python object back, so a bulk
        # .update() would never actually become visible on `clearance` (see
        # the sharedmemory-model skill). auto_now_add only forces the value
        # on INSERT, so an explicit assignment survives a later save().
        clearance.created_at = timezone.now() - timedelta(days=CUSTODY_ESCALATION_STALE_DAYS + 1)
        clearance.save(update_fields=["created_at"])
        updated = escalate_clearance(clearance)
        assert updated.status == CustodyClearanceStatus.ESCALATED

    def test_escalate_rejects_fresh_pending_clearance(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.PENDING,
        )
        with self.assertRaises(CustodyClearanceStateError):
            escalate_clearance(clearance)

    def test_escalate_rejects_already_granted(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
        )
        with self.assertRaises(CustodyClearanceStateError):
            escalate_clearance(clearance)

    def test_escalate_notifies_custodian(self):
        _gm_with_notification_sheet(self.custodian_gm)
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.DENIED,
        )
        count_before = NarrativeMessage.objects.count()
        escalate_clearance(clearance)
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.requester.account.username in msg.body


class ResolveEscalationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.subject = StoryProtectedSubjectFactory(story=cls.story)
        cls.requester = GMProfileFactory()
        cls.staff_account = AccountFactory(is_staff=True)

    def _escalated_clearance(self):
        return CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.REMOVE,
            status=CustodyClearanceStatus.ESCALATED,
        )

    def test_resolve_grant(self):
        clearance = self._escalated_clearance()
        updated = resolve_escalation(
            clearance, staff_account=self.staff_account, grant=True, response_note="OK."
        )
        assert updated.status == CustodyClearanceStatus.GRANTED
        assert updated.staff_resolver_id == self.staff_account.pk
        assert updated.resolved_at is not None

    def test_resolve_deny(self):
        clearance = self._escalated_clearance()
        updated = resolve_escalation(clearance, staff_account=self.staff_account, grant=False)
        assert updated.status == CustodyClearanceStatus.DENIED
        assert updated.staff_resolver_id == self.staff_account.pk

    def test_resolve_rejects_non_staff(self):
        clearance = self._escalated_clearance()
        non_staff = AccountFactory(is_staff=False)
        with self.assertRaises(CustodyClearanceAuthorityError):
            resolve_escalation(clearance, staff_account=non_staff, grant=True)

    def test_resolve_rejects_non_escalated_status(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.REMOVE,
            status=CustodyClearanceStatus.PENDING,
        )
        with self.assertRaises(CustodyClearanceStateError):
            resolve_escalation(clearance, staff_account=self.staff_account, grant=True)

    def test_resolve_notifies_requester(self):
        _gm_with_notification_sheet(self.requester)
        clearance = self._escalated_clearance()
        count_before = NarrativeMessage.objects.count()
        resolve_escalation(clearance, staff_account=self.staff_account, grant=True)
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.staff_account.username in msg.body


class RevokeClearanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.subject = StoryProtectedSubjectFactory(story=cls.story)
        cls.requester = GMProfileFactory()

    def _granted_clearance(self):
        return CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
            granted_by=self.custodian_gm,
        )

    def test_custodian_can_revoke(self):
        clearance = self._granted_clearance()
        revoke_clearance(clearance, revoked_by=self.custodian_gm.account)
        clearance.refresh_from_db()
        assert clearance.revoked_at is not None

    def test_staff_can_revoke(self):
        clearance = self._granted_clearance()
        staff_account = AccountFactory(is_staff=True)
        revoke_clearance(clearance, revoked_by=staff_account)
        clearance.refresh_from_db()
        assert clearance.revoked_at is not None

    def test_outsider_cannot_revoke(self):
        clearance = self._granted_clearance()
        outsider_account = AccountFactory(is_staff=False)
        with self.assertRaises(CustodyClearanceAuthorityError):
            revoke_clearance(clearance, revoked_by=outsider_account)

    def test_cannot_revoke_pending_clearance(self):
        clearance = CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.PENDING,
        )
        with self.assertRaises(CustodyClearanceStateError):
            revoke_clearance(clearance, revoked_by=self.custodian_gm.account)

    def test_cannot_double_revoke(self):
        clearance = self._granted_clearance()
        revoke_clearance(clearance, revoked_by=self.custodian_gm.account)
        clearance.refresh_from_db()
        with self.assertRaises(CustodyClearanceStateError):
            revoke_clearance(clearance, revoked_by=self.custodian_gm.account)

    def test_revoke_notifies_requester(self):
        _gm_with_notification_sheet(self.requester)
        clearance = self._granted_clearance()
        count_before = NarrativeMessage.objects.count()
        revoke_clearance(clearance, revoked_by=self.custodian_gm.account)
        assert NarrativeMessage.objects.count() == count_before + 1
        msg = NarrativeMessage.objects.latest("pk")
        assert self.custodian_gm.account.username in msg.body


class ActiveClearanceExistsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.subject = StoryProtectedSubjectFactory()
        cls.requester = GMProfileFactory()
        cls.account = cls.requester.account

    def test_false_when_no_clearance(self):
        assert not active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.APPEAR
        )

    def test_false_when_account_none(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
        )
        assert not active_clearance_exists(
            protected_subject=self.subject, account=None, scope=CustodyScope.APPEAR
        )

    def test_true_at_granted_scope(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
        )
        assert active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.HARM
        )

    def test_true_when_granted_scope_stronger_than_required(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.REMOVE,
            status=CustodyClearanceStatus.GRANTED,
        )
        assert active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.APPEAR
        )

    def test_false_when_granted_scope_weaker_than_required(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
        )
        assert not active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.REMOVE
        )

    def test_false_when_pending(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.PENDING,
        )
        assert not active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.HARM
        )

    def test_false_when_revoked(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
            revoked_at=timezone.now(),
        )
        assert not active_clearance_exists(
            protected_subject=self.subject, account=self.account, scope=CustodyScope.HARM
        )

    def test_false_for_different_account(self):
        CustodyClearanceFactory(
            protected_subject=self.subject,
            requested_by=self.requester,
            scope=CustodyScope.HARM,
            status=CustodyClearanceStatus.GRANTED,
        )
        other_account = AccountFactory()
        assert not active_clearance_exists(
            protected_subject=self.subject, account=other_account, scope=CustodyScope.HARM
        )


class CheckSubjectCustodyClearanceWiringTests(TestCase):
    """E2E: check_subject_custody's stubbed clearance branch now really unblocks."""

    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.custodian_gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.custodian_gm)
        cls.story.primary_table = cls.table
        cls.story.save(update_fields=["primary_table"])
        cls.npc_sheet = CharacterSheetFactory()
        cls.subject = StoryProtectedSubjectFactory(story=cls.story, subject_sheet=cls.npc_sheet)
        cls.subject_identity = _subject_identity(
            StakeSubjectKind.NPC_FATE, cls.npc_sheet.pk, None, None, None, ""
        )

    def test_outsider_blocked_then_granted_clearance_allows_at_scope(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        blocked = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.HARM,
        )
        assert not blocked.allowed

        outsider_gm = GMProfileFactory(account=outsider_account)
        clearance = request_clearance(
            protected_subject=self.subject, requested_by=outsider_gm, scope=CustodyScope.HARM
        )
        grant_clearance(clearance, granted_by=self.custodian_gm)

        allowed = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.HARM,
        )
        assert allowed.allowed

    def test_clearance_at_lower_scope_does_not_cover_higher_scope(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)
        outsider_gm = GMProfileFactory(account=outsider_account)
        clearance = request_clearance(
            protected_subject=self.subject, requested_by=outsider_gm, scope=CustodyScope.APPEAR
        )
        grant_clearance(clearance, granted_by=self.custodian_gm)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.REMOVE,
        )
        assert not verdict.allowed

    def test_revoked_clearance_blocks_again(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)
        outsider_gm = GMProfileFactory(account=outsider_account)
        clearance = request_clearance(
            protected_subject=self.subject, requested_by=outsider_gm, scope=CustodyScope.HARM
        )
        grant_clearance(clearance, granted_by=self.custodian_gm)

        allowed = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.HARM,
        )
        assert allowed.allowed

        revoke_clearance(clearance, revoked_by=self.custodian_gm.account)

        blocked_again = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.HARM,
        )
        assert not blocked_again.allowed
