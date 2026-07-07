"""CustodyClearance lifecycle services + notifications (#2001).

A ``CustodyClearance`` is a GM's request for permission to act (at some
``CustodyScope``) on another story's ``StoryProtectedSubject``. The custodian —
the Lead GM of the protecting story (``protected_subject.story.primary_table.gm``),
or staff — decides PENDING requests; a denied or stale-pending request may be
escalated, and only staff resolves an ESCALATED tiebreak.

``active_clearance_exists`` is the seam ``world.stories.services.custody``'s
``check_subject_custody`` calls (via ``_active_clearance_allows``) to decide
whether an active, unrevoked clearance covers an actor at a given scope — the
single source of truth for "does a clearance let this actor through."

``matching_active_protected_subjects`` is the seam
``CustodyClearanceRequestSerializer`` calls to resolve an identity-based
clearance request (subject_kind + typed pointer/label, no pk known) to the
active ``StoryProtectedSubject`` row(s) it protects — reuses the same
``_subject_identity`` tuple ``world.stories.services.custody`` matches
``Stake``/``TreasuredSubject`` rows against.

Programmer-error guards only (this app has no API endpoints for these actions
yet — Task 6 adds permission classes; Task 7 adds telnet). Until then, these
services enforce authority themselves, mirroring
``world.gm.services.surrender_character_story``. State-transition guards raise
the typed ``CustodyClearanceError`` family (see ``exceptions.py``) rather than
bare ``ValueError``, matching the existing ``AssistantClaimError`` family
convention for a well-known lifecycle.

Disclosure rule for notification bodies (mirrors ADR-0033's posture): only the
subject's display label, the scope, and the counterpart GM's (or staff's)
username may appear. Never the other side's story title or notes. To keep
``related_story`` (which IS exposed to API/telnet readers of the resulting
``NarrativeMessage``) from leaking a story the recipient doesn't own, every
notification tags ``related_story`` with a story the RECIPIENT already has
standing in: the custodian's own protecting story when notifying the
custodian, or the requester's own ``requesting_story`` when notifying the
requester — never the counterpart's.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.stories.constants import (
    CUSTODY_ESCALATION_STALE_DAYS,
    CUSTODY_SCOPE_ORDER,
    CustodyClearanceStatus,
    custody_scope_index,
)
from world.stories.exceptions import CustodyClearanceAuthorityError, CustodyClearanceStateError
from world.stories.models import CustodyClearance, StoryProtectedSubject
from world.stories.services.boundaries import SubjectIdentity, _subject_identity

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.gm.models import GMProfile
    from world.stories.models import Beat, Story

_LIVE_STATUSES = (CustodyClearanceStatus.PENDING, CustodyClearanceStatus.ESCALATED)


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def _custodian_gm(protected_subject: StoryProtectedSubject) -> GMProfile | None:
    """The Lead GM of the story protecting ``protected_subject``, or None if orphaned."""
    table = protected_subject.story.primary_table
    return table.gm if table is not None else None


def _is_custodian_account(protected_subject: StoryProtectedSubject, account: AccountDB) -> bool:
    """Whether ``account`` is the custodian GM's account, or staff."""
    if account.is_staff:
        return True
    custodian = _custodian_gm(protected_subject)
    return custodian is not None and custodian.account_id == account.pk


def _require_custodian_gm(protected_subject: StoryProtectedSubject, gm_profile: GMProfile) -> None:
    """Raise unless ``gm_profile`` is the exact custodian GM of ``protected_subject``.

    Deliberately does not accept a staff bypass here — staff act through the
    dedicated ``resolve_escalation`` path, never by posing as the custodian.
    """
    custodian = _custodian_gm(protected_subject)
    if custodian is None or custodian.pk != gm_profile.pk:
        msg = "Only the protecting story's Lead GM may decide this clearance."
        raise CustodyClearanceAuthorityError(msg)


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------


def _subject_display_label(protected_subject: StoryProtectedSubject) -> str:
    """A player/GM-safe display label for the protected subject.

    Mirrors ``StoryProtectedSubject.clean()``'s exactly-one-subject precedence
    ordering. Never touches ``notes`` (GM-private) or the protecting story's title.
    """
    if protected_subject.subject_label:
        return protected_subject.subject_label
    if protected_subject.subject_sheet_id is not None:
        return protected_subject.subject_sheet.primary_persona.name
    if protected_subject.subject_item_id is not None:
        return str(protected_subject.subject_item)
    if protected_subject.subject_society_id is not None:
        return protected_subject.subject_society.name
    if protected_subject.subject_organization_id is not None:
        return protected_subject.subject_organization.name
    return f"subject #{protected_subject.pk}"


def _notify_gm(gm_profile: GMProfile, *, body: str, related_story: Story | None) -> None:
    """Send a SYSTEM NarrativeMessage to ``gm_profile``'s notification-target sheet.

    Skips gracefully (mirrors ``tables._send_offer_notification``) when the GM
    has no resolvable CharacterSheet.
    """
    from world.gm.services import get_notification_target_for_gm  # noqa: PLC0415

    character_sheet = get_notification_target_for_gm(gm_profile)
    if character_sheet is None:
        return
    send_narrative_message(
        recipients=[character_sheet],
        body=body,
        category=NarrativeCategory.SYSTEM,
        related_story=related_story,
    )


def _notify_requester(clearance: CustodyClearance, *, body: str) -> None:
    _notify_gm(clearance.requested_by, body=body, related_story=clearance.requesting_story)


def _notify_custodian(clearance: CustodyClearance, *, body: str) -> None:
    custodian = _custodian_gm(clearance.protected_subject)
    if custodian is None:
        return  # orphaned protecting story — no one to notify.
    _notify_gm(custodian, body=body, related_story=clearance.protected_subject.story)


# ---------------------------------------------------------------------------
# Lifecycle services
# ---------------------------------------------------------------------------


@transaction.atomic
def request_clearance(  # noqa: PLR0913
    *,
    protected_subject: StoryProtectedSubject,
    requested_by: GMProfile,
    scope: str,
    requesting_story: Story | None = None,
    requesting_beat: Beat | None = None,
    message: str = "",
) -> CustodyClearance:
    """Create a PENDING CustodyClearance and notify the custodian GM.

    Guards against a second live (PENDING/ESCALATED) request for the same
    (protected_subject, requested_by, scope) — the DB partial-unique
    constraint is the backstop; this check gives a typed error instead of an
    IntegrityError.
    """
    already_live = CustodyClearance.objects.filter(
        protected_subject=protected_subject,
        requested_by=requested_by,
        scope=scope,
        status__in=_LIVE_STATUSES,
    ).exists()
    if already_live:
        msg = (
            f"{requested_by} already has a live clearance request for "
            f"{protected_subject} at scope={scope!r}."
        )
        raise CustodyClearanceStateError(msg)

    clearance = CustodyClearance.objects.create(
        protected_subject=protected_subject,
        requested_by=requested_by,
        requesting_story=requesting_story,
        requesting_beat=requesting_beat,
        scope=scope,
        status=CustodyClearanceStatus.PENDING,
        message=message,
    )
    subject_label = _subject_display_label(protected_subject)
    _notify_custodian(
        clearance,
        body=(
            f"{requested_by.account.username} has requested {scope} clearance for {subject_label}."
        ),
    )
    return clearance


@transaction.atomic
def grant_clearance(
    clearance: CustodyClearance,
    *,
    granted_by: GMProfile,
    response_note: str = "",
) -> CustodyClearance:
    """Custodian GM grants a PENDING clearance request."""
    if clearance.status != CustodyClearanceStatus.PENDING:
        msg = (
            f"Clearance {clearance.pk} is not PENDING (status={clearance.status!r}); "
            "only a PENDING request can be granted directly (see resolve_escalation)."
        )
        raise CustodyClearanceStateError(msg)
    _require_custodian_gm(clearance.protected_subject, granted_by)

    clearance.status = CustodyClearanceStatus.GRANTED
    clearance.granted_by = granted_by
    clearance.response_note = response_note
    clearance.resolved_at = timezone.now()
    clearance.save(
        update_fields=["status", "granted_by", "response_note", "resolved_at"],
    )
    subject_label = _subject_display_label(clearance.protected_subject)
    _notify_requester(
        clearance,
        body=(
            f"{granted_by.account.username} granted your {clearance.scope} clearance "
            f"for {subject_label}."
        ),
    )
    return clearance


@transaction.atomic
def deny_clearance(
    clearance: CustodyClearance,
    *,
    denied_by: GMProfile,
    response_note: str = "",
) -> CustodyClearance:
    """Custodian GM denies a PENDING clearance request."""
    if clearance.status != CustodyClearanceStatus.PENDING:
        msg = (
            f"Clearance {clearance.pk} is not PENDING (status={clearance.status!r}); "
            "only a PENDING request can be denied directly (see resolve_escalation)."
        )
        raise CustodyClearanceStateError(msg)
    _require_custodian_gm(clearance.protected_subject, denied_by)

    clearance.status = CustodyClearanceStatus.DENIED
    clearance.granted_by = denied_by
    clearance.response_note = response_note
    clearance.resolved_at = timezone.now()
    clearance.save(
        update_fields=["status", "granted_by", "response_note", "resolved_at"],
    )
    subject_label = _subject_display_label(clearance.protected_subject)
    _notify_requester(
        clearance,
        body=(
            f"{denied_by.account.username} denied your {clearance.scope} clearance "
            f"request for {subject_label}."
        ),
    )
    return clearance


def clearance_is_stale(clearance: CustodyClearance) -> bool:
    """Whether ``clearance`` is older than the escalation staleness threshold.

    Public — ``CustodyClearanceEscalateInputSerializer`` needs to pre-validate
    escalation eligibility without reaching into a private service function
    (Task 6 review Fix 3).
    """
    threshold = timedelta(days=CUSTODY_ESCALATION_STALE_DAYS)
    return timezone.now() - clearance.created_at >= threshold


_clearance_is_stale = clearance_is_stale  # internal alias; used by escalate_clearance below.


@transaction.atomic
def escalate_clearance(clearance: CustodyClearance) -> CustodyClearance:
    """Escalate a DENIED clearance, or a PENDING one older than the staleness threshold.

    No actor parameter: only the requester may call this in practice, but that
    authorization boundary belongs to Task 6's permission classes (this app has
    no API endpoint yet) — mirrors the signature pinned in the Task 3 brief.
    """
    is_denied = clearance.status == CustodyClearanceStatus.DENIED
    is_stale_pending = clearance.status == CustodyClearanceStatus.PENDING and _clearance_is_stale(
        clearance
    )
    if not (is_denied or is_stale_pending):
        msg = (
            f"Clearance {clearance.pk} (status={clearance.status!r}) is not eligible for "
            "escalation — must be DENIED, or PENDING and older than "
            f"{CUSTODY_ESCALATION_STALE_DAYS} days."
        )
        raise CustodyClearanceStateError(msg)

    clearance.status = CustodyClearanceStatus.ESCALATED
    clearance.resolved_at = None
    clearance.save(update_fields=["status", "resolved_at"])
    subject_label = _subject_display_label(clearance.protected_subject)
    _notify_custodian(
        clearance,
        body=(
            f"{clearance.requested_by.account.username} escalated their {clearance.scope} "
            f"clearance request for {subject_label} to staff review."
        ),
    )
    return clearance


@transaction.atomic
def resolve_escalation(
    clearance: CustodyClearance,
    *,
    staff_account: AccountDB,
    grant: bool,
    response_note: str = "",
) -> CustodyClearance:
    """Staff resolves an ESCALATED clearance's tiebreak."""
    if not staff_account.is_staff:
        msg = "Only staff may resolve an escalated custody clearance."
        raise CustodyClearanceAuthorityError(msg)
    if clearance.status != CustodyClearanceStatus.ESCALATED:
        msg = (
            f"Clearance {clearance.pk} is not ESCALATED (status={clearance.status!r}); "
            "only an escalated request can be staff-resolved."
        )
        raise CustodyClearanceStateError(msg)

    clearance.status = CustodyClearanceStatus.GRANTED if grant else CustodyClearanceStatus.DENIED
    clearance.staff_resolver = staff_account
    clearance.response_note = response_note
    clearance.resolved_at = timezone.now()
    clearance.save(
        update_fields=["status", "staff_resolver", "response_note", "resolved_at"],
    )
    subject_label = _subject_display_label(clearance.protected_subject)
    verb = "granted" if grant else "denied"
    _notify_requester(
        clearance,
        body=(
            f"Staff ({staff_account.username}) {verb} your escalated {clearance.scope} "
            f"clearance request for {subject_label}."
        ),
    )
    return clearance


@transaction.atomic
def revoke_clearance(clearance: CustodyClearance, *, revoked_by: AccountDB) -> None:
    """Soft-revoke a GRANTED clearance. Custodian GM's account or staff only.

    Never deletes the row — the decision trail survives (mirrors the
    story-significant-data-never-hard-deleted rule).
    """
    if not _is_custodian_account(clearance.protected_subject, revoked_by):
        msg = "Only the protecting story's Lead GM or staff may revoke this clearance."
        raise CustodyClearanceAuthorityError(msg)
    if clearance.status != CustodyClearanceStatus.GRANTED or clearance.revoked_at is not None:
        msg = (
            f"Clearance {clearance.pk} is not an active GRANTED clearance "
            f"(status={clearance.status!r}, revoked_at={clearance.revoked_at!r}) and "
            "cannot be revoked."
        )
        raise CustodyClearanceStateError(msg)

    clearance.revoked_at = timezone.now()
    clearance.save(update_fields=["revoked_at"])
    subject_label = _subject_display_label(clearance.protected_subject)
    _notify_requester(
        clearance,
        body=(
            f"{revoked_by.username} revoked your {clearance.scope} clearance for {subject_label}."
        ),
    )


def active_clearance_exists(
    *,
    protected_subject: StoryProtectedSubject,
    account: AccountDB | None,
    scope: str,
) -> bool:
    """Whether an active, unrevoked clearance at >= ``scope`` covers ``account``.

    Active = status GRANTED, revoked_at null, scope index >= the required
    scope's index (mirrors the ``RISK_LADDER``-style ladder comparison used
    throughout stories/constants.py), and the clearance's requester's account
    is ``account``. THE seam ``check_subject_custody`` calls via
    ``_active_clearance_allows`` — never re-derive this lookup elsewhere.
    """
    if account is None:
        return False
    required_index = custody_scope_index(scope)
    qualifying_scopes = CUSTODY_SCOPE_ORDER[required_index:]
    return CustodyClearance.objects.filter(
        protected_subject=protected_subject,
        status=CustodyClearanceStatus.GRANTED,
        revoked_at__isnull=True,
        scope__in=qualifying_scopes,
        requested_by__account=account,
    ).exists()


def matching_active_protected_subjects(
    subject_identity: SubjectIdentity,
) -> list[StoryProtectedSubject]:
    """Active ``StoryProtectedSubject`` rows matching ``subject_identity`` (Task 6 Fix 4).

    Backs ``CustodyClearanceRequestSerializer``'s identity-based request path
    (a blocked outsider GM who only knows the custodian's username, never the
    ``protected_subject`` pk). Deliberately mirrors the pk create-path's own
    oracle exactly — ``is_active=True`` only, with NO protection-window
    filtering (unlike ``world.stories.services.custody``'s
    ``_matching_protections``, which additionally requires the beat/story
    window to be open): the pk path's ``CustodyClearanceRequestSerializer``
    queryset never checks the window either, so adding that check here would
    let identity-path callers distinguish "inactive" from "active but
    window-closed" — a new oracle the pk path doesn't have.

    Ordered oldest-first (mirrors ``_matching_protections``) so a
    multi-protection fan-out request routes to (and notifies) the original
    custodian first.
    """
    kind = subject_identity[0]
    candidates = StoryProtectedSubject.objects.filter(subject_kind=kind, is_active=True).order_by(
        "created_at", "pk"
    )
    return [
        row
        for row in candidates
        if _subject_identity(
            row.subject_kind,
            row.subject_sheet_id,
            row.subject_item_id,
            row.subject_society_id,
            row.subject_organization_id,
            row.subject_label,
        )
        == subject_identity
    ]
