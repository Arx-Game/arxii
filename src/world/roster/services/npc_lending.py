"""Lending a major NPC to a Guide or GM to play (#4418).

A loan moves who plays a story NPC without moving who holds it. The holder keeps
their ``RosterTenure``; an ACTIVE ``NPCLoan`` takes the NPC out of the holder's
playable characters and puts it into the borrower's. ``playable_entries`` is the one
place that rule lives, and both availability seams read it:
``PlayerData.get_available_roster_entries`` (puppeting, ``mine``, selection) and
``Account.cached_roster_entries`` (persona ownership for posting and consent).

Two ways in:

- A scene's GM offers an NPC they own to a Guide for that scene (``offer_npc``); the
  Guide accepts or declines (``answer_loan``). The loan ends with the scene
  (``end_scene_loans``) or when the owner takes it back (``end_loan``).
- A GM or Guide asks to borrow a listed NPC (``request_borrow``). The owner's
  ``lend_policy`` decides: ``on_request`` waits for the owner's answer,
  ``without_asking`` is active at once.

Every change clears the borrower's and the holder's identity-mapped caches (account
and ``PlayerData``) so the change shows on the next read, and an ending loan
unpuppets the borrower's sessions on the character.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from world.roster.constants import NPCBorrowAudience, NPCLendPolicy, NPCLoanStatus
from world.roster.models import NPCLoan
from world.roster.types import HandOffCounts

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from evennia.accounts.models import AccountDB

    from world.roster.models import RosterEntry, StoryNPCSettings
    from world.scenes.models import Scene

# Loans that still hold or may soon hold the NPC: what a scene's end closes.
_OPEN_STATUSES = (NPCLoanStatus.OFFERED, NPCLoanStatus.REQUESTED, NPCLoanStatus.ACTIVE)


class NPCLendingError(Exception):
    """A loan the rules refuse; ``user_message`` is safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


# -- who is who ---------------------------------------------------------------


def _is_staff(account: AccountDB | None) -> bool:
    return bool(account is not None and account.is_staff)


def _is_owner(entry: RosterEntry, account: AccountDB) -> bool:
    return entry.created_by_account_id == account.pk


def _is_active_guide(account: AccountDB) -> bool:
    from world.gm.models import GuideProfile  # noqa: PLC0415

    return GuideProfile.objects.filter(account=account, is_active=True).exists()


def _is_gm(account: AccountDB) -> bool:
    return account.gm_profile_or_none is not None


def _holder_account(entry: RosterEntry) -> AccountDB | None:
    tenure = entry.current_tenure
    if tenure is None or tenure.player_data is None:
        return None
    return tenure.player_data.account


def _holds(entry: RosterEntry, account: AccountDB) -> bool:
    holder = _holder_account(entry)
    return holder is not None and holder.pk == account.pk


# -- reading loans -------------------------------------------------------------


def active_loan_for(entry: RosterEntry) -> NPCLoan | None:
    """The ACTIVE loan of ``entry``, or None (at most one by constraint)."""
    return (
        NPCLoan.objects.filter(roster_entry=entry, status=NPCLoanStatus.ACTIVE)
        .select_related("borrower")
        .first()
    )


def active_loans_touching(account: AccountDB, entry_ids: Iterable[int]) -> list[NPCLoan]:
    """ACTIVE loans ``account`` borrows, or that lend out one of ``entry_ids``.

    One query. The rows carry what the playable-character readers need (the
    entry's roster, sheet and character, the scene and settings for ``mine``).
    """
    return list(
        NPCLoan.objects.filter(status=NPCLoanStatus.ACTIVE)
        .filter(Q(borrower=account) | Q(roster_entry_id__in=list(entry_ids)))
        .select_related(
            "roster_entry__roster",
            "roster_entry__character_sheet__character",
            "roster_entry__story_npc_settings",
            "scene",
            "offered_by",
            "borrower",
        )
        .order_by("pk")
    )


def playable_entries(
    account: AccountDB,
    tenure_entries: list[RosterEntry],
    loans: list[NPCLoan] | None = None,
) -> list[RosterEntry]:
    """The entries ``account`` may play: its tenures minus those lent away, plus loans.

    ``loans`` is ``active_loans_touching(account, ...)`` when the caller already
    holds it cached (``PlayerData.cached_npc_loans``); otherwise it is read here.
    """
    if loans is None:
        loans = active_loans_touching(account, [entry.pk for entry in tenure_entries])
    lent_away = {loan.roster_entry_id for loan in loans if loan.borrower_id != account.pk}
    entries = [entry for entry in tenure_entries if entry.pk not in lent_away]
    held = {entry.pk for entry in entries}
    for loan in loans:
        if loan.borrower_id == account.pk and loan.roster_entry_id not in held:
            entries.append(loan.roster_entry)
            held.add(loan.roster_entry_id)
    return entries


# -- keeping the caches honest -------------------------------------------------


def _clear_account_caches(account: AccountDB | None) -> None:
    if account is None:
        return
    account.clear_cached_properties()
    from evennia_extensions.models import PlayerData  # noqa: PLC0415

    # ``Account.player_data`` creates a row on read; a loan party always has one.
    player_data = PlayerData.objects.filter(account=account).first()
    if player_data is not None:
        player_data.clear_cached_properties()


def _clear_loan_caches(loan: NPCLoan) -> None:
    """Drop the borrower's and the holder's cached playable characters and personas."""
    _clear_account_caches(loan.borrower)
    _clear_account_caches(_holder_account(loan.roster_entry))


def _unpuppet_sessions(entry: RosterEntry, *, keep: AccountDB | None) -> None:
    """Unpuppet every session on the NPC whose account is not ``keep``.

    The same shape as the unpuppet ``world.vitals.services`` runs on retirement.
    """
    character = entry.character_sheet.character
    for session in list(character.sessions.all()):
        account = session.account
        if account is None or (keep is not None and account.pk == keep.pk):
            continue
        account.unpuppet_object(session)


# -- making and answering loans -----------------------------------------------


def _settings_for(entry: RosterEntry) -> StoryNPCSettings | None:
    from world.roster.models import StoryNPCSettings  # noqa: PLC0415

    return StoryNPCSettings.objects.filter(roster_entry=entry).first()


def _require_lendable(entry: RosterEntry) -> StoryNPCSettings | None:
    from world.roster.services.activity import is_story_npc  # noqa: PLC0415

    if not is_story_npc(entry.character_sheet):
        msg = "Only a story NPC can be lent."
        raise NPCLendingError(msg)
    settings = _settings_for(entry)
    if settings is not None and settings.is_template:
        msg = "A template is copied, not lent."
        raise NPCLendingError(msg)
    if entry.current_tenure is None:
        msg = "Nobody holds that NPC to lend it."
        raise NPCLendingError(msg)
    return settings


@transaction.atomic
def offer_npc(*, entry: RosterEntry, guide: AccountDB, scene: Scene, by: AccountDB) -> NPCLoan:
    """Offer ``entry`` to the Guide ``guide`` for ``scene``.

    ``by`` must own the NPC (or be staff) and run the scene: staff, its GM or an
    owner (``can_create_encounter_for_scene``). A newer offer of the same NPC for
    the same scene replaces an older one still waiting.
    """
    from world.combat.permissions import can_create_encounter_for_scene  # noqa: PLC0415

    _require_lendable(entry)
    if not (_is_owner(entry, by) or _is_staff(by)):
        msg = "Only the NPC's owner can lend it."
        raise NPCLendingError(msg)
    # Whoever runs the scene, as the cast panel's own gate admits them: staff, the
    # scene's GM, or an owner (a GM who pressed Start Scene owns it, #4418 bug 9).
    if not can_create_encounter_for_scene(by, scene):
        msg = "Only the scene's GM can lend an NPC for it."
        raise NPCLendingError(msg)
    if not scene.is_active:
        msg = "That scene has ended."
        raise NPCLendingError(msg)
    if not _is_active_guide(guide):
        msg = "Only a Guide can be lent an NPC for a scene."
        raise NPCLendingError(msg)
    if _holds(entry, guide):
        msg = "They already play that NPC."
        raise NPCLendingError(msg)
    for older in NPCLoan.objects.filter(
        roster_entry=entry, scene=scene, status=NPCLoanStatus.OFFERED
    ):
        end_loan(older, by=None)
    loan = NPCLoan.objects.create(
        roster_entry=entry,
        borrower=guide,
        offered_by=by,
        scene=scene,
        status=NPCLoanStatus.OFFERED,
    )
    _clear_loan_caches(loan)
    _make_playable(entry)
    return loan


def _make_playable(entry: RosterEntry) -> None:
    """An NPC minted before #4418 still has Evennia's developer-only puppet lock."""
    from world.roster.services.staff_characters import ensure_playable_lock  # noqa: PLC0415

    ensure_playable_lock(entry.character_sheet.character)


def _may_borrow(settings: StoryNPCSettings, borrower: AccountDB) -> bool:
    if _is_staff(borrower) or _is_gm(borrower):
        return True
    return settings.borrow_audience == NPCBorrowAudience.GMS_AND_GUIDES and _is_active_guide(
        borrower
    )


@transaction.atomic
def request_borrow(*, entry: RosterEntry, borrower: AccountDB) -> NPCLoan:
    """Ask to borrow a listed NPC; active at once when its owner lends without asking."""
    settings = _require_lendable(entry)
    if settings is None or not settings.listed_on_npc_roster:
        msg = "That NPC isn't on the NPC roster."
        raise NPCLendingError(msg)
    if settings.lend_policy == NPCLendPolicy.NOT_LENT:
        msg = "That NPC isn't lent out."
        raise NPCLendingError(msg)
    if not _may_borrow(settings, borrower):
        msg = "That NPC is lent only to GMs."
        raise NPCLendingError(msg)
    if _is_owner(entry, borrower) or _holds(entry, borrower):
        msg = "You already hold that NPC."
        raise NPCLendingError(msg)
    if NPCLoan.objects.filter(
        roster_entry=entry,
        borrower=borrower,
        status__in=(NPCLoanStatus.REQUESTED, NPCLoanStatus.ACTIVE),
    ).exists():
        msg = "You have already asked for that NPC."
        raise NPCLendingError(msg)
    owner = entry.created_by_account or _holder_account(entry)
    loan = NPCLoan.objects.create(
        roster_entry=entry,
        borrower=borrower,
        offered_by=owner or borrower,
        status=NPCLoanStatus.REQUESTED,
    )
    if settings.lend_policy == NPCLendPolicy.WITHOUT_ASKING:
        _activate(loan)
    else:
        _clear_loan_caches(loan)
    return loan


JUST_LENT_MESSAGE = "That NPC was just lent to someone else."


def _lock_status(loan: NPCLoan) -> None:
    """Lock ``loan``'s row and bring its status and times up to date with the database.

    Read as values, never as an instance: the identity map would hand back the
    cached object as it was, and ``refresh_from_db()`` goes through the same map, so
    it would copy the stale fields back onto themselves. The values read here are
    assigned onto the cached ``loan``, so a concurrent answer or take-back that
    landed first is what the caller decides on, inside this transaction.
    """
    fresh = (
        NPCLoan.objects.select_for_update()
        .filter(pk=loan.pk)
        .values_list("status", "started_at", "ended_at")
        .first()
    )
    if fresh is None:
        msg = "That loan no longer exists."
        raise NPCLendingError(msg)
    loan.status, loan.started_at, loan.ended_at = fresh


def _clear_selection(account: AccountDB | None, entry: RosterEntry) -> None:
    """Drop ``account``'s saved selection of ``entry`` once they no longer play it."""
    if account is None:
        return
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415

    player_data = PlayerData.objects.filter(account=account).first()
    if player_data is not None and player_data.selected_entry_id == entry.pk:
        set_selected_entry(player_data, None)


def _activate(loan: NPCLoan) -> None:
    """Make ``loan`` the NPC's one ACTIVE loan; the previous borrower and the holder
    stop playing it.

    Runs inside the caller's transaction. The NPC's ACTIVE loans are locked before
    they are ended. The activation itself is written as a raw UPDATE in a savepoint,
    so the cached ``loan`` is only changed once the database has accepted it; a
    competing ACTIVE row the lock could not see becomes a refusal, and every loan
    this ended is dropped from the identity map because the refusal rolls it back.
    """
    others = list(
        NPCLoan.objects.select_for_update()
        .filter(roster_entry_id=loan.roster_entry_id, status=NPCLoanStatus.ACTIVE)
        .exclude(pk=loan.pk)
    )
    for other in others:
        end_loan(other, by=None)
    started_at = timezone.now()
    try:
        with transaction.atomic():
            NPCLoan.objects.filter(pk=loan.pk).update_with_reason(
                reason="activate an NPC loan; the cached instance is set once this lands",
                status=NPCLoanStatus.ACTIVE,
                started_at=started_at,
            )
    except IntegrityError:
        # ``loan`` was never changed in memory (the write did not land); the
        # others were ended by ``end_loan`` and that end is rolled back with this.
        for stale in others:
            NPCLoan.flush_cached_instance(stale, force=True)
        raise NPCLendingError(JUST_LENT_MESSAGE) from None
    loan.status = NPCLoanStatus.ACTIVE
    loan.started_at = started_at
    _clear_loan_caches(loan)
    _clear_selection(_holder_account(loan.roster_entry), loan.roster_entry)
    _make_playable(loan.roster_entry)
    _unpuppet_sessions(loan.roster_entry, keep=loan.borrower)


@transaction.atomic
def answer_loan(*, loan: NPCLoan, accept: bool, by: AccountDB) -> NPCLoan:
    """Accept or decline a waiting loan.

    An offer is answered by the Guide it was offered to; a request by the NPC's
    owner (or staff). The loan is locked and re-read first, so an answer racing
    another answer or a take-back sees the result of whichever landed first.
    """
    _lock_status(loan)
    if loan.status == NPCLoanStatus.OFFERED:
        if by.pk != loan.borrower_id:
            msg = "That offer wasn't made to you."
            raise NPCLendingError(msg)
        if accept and not _is_active_guide(by):
            msg = "Only a Guide can accept an NPC for a scene."
            raise NPCLendingError(msg)
        if accept and loan.scene is not None and not loan.scene.is_active:
            msg = "That scene has ended."
            raise NPCLendingError(msg)
    elif loan.status == NPCLoanStatus.REQUESTED:
        if not (_is_owner(loan.roster_entry, by) or _is_staff(by)):
            msg = "Only the NPC's owner can answer that request."
            raise NPCLendingError(msg)
    else:
        msg = "That loan has already been answered."
        raise NPCLendingError(msg)

    if accept:
        _activate(loan)
    else:
        loan.status = NPCLoanStatus.DECLINED
        loan.ended_at = timezone.now()
        loan.save(update_fields=["status", "ended_at"])
        _clear_loan_caches(loan)
    return loan


# -- ending loans ---------------------------------------------------------------


def may_end_loan(loan: NPCLoan, account: AccountDB) -> bool:
    """The owner, whoever made the offer, the borrower handing it back, or staff."""
    return (
        _is_staff(account)
        or _is_owner(loan.roster_entry, account)
        or account.pk in (loan.offered_by_id, loan.borrower_id)
    )


@transaction.atomic
def end_loan(loan: NPCLoan, *, by: AccountDB | None) -> None:
    """End ``loan``: the borrower stops playing the NPC and its holder plays it again.

    ``by`` is None for a system end (the scene finished, a newer loan replaced it).
    The borrower's saved selection of the NPC is cleared with it.
    """
    if by is not None and not may_end_loan(loan, by):
        msg = "That isn't your loan to end."
        raise NPCLendingError(msg)
    _lock_status(loan)
    if loan.status in (NPCLoanStatus.ENDED, NPCLoanStatus.DECLINED):
        return
    was_active = loan.status == NPCLoanStatus.ACTIVE
    loan.status = NPCLoanStatus.ENDED
    loan.ended_at = timezone.now()
    loan.save(update_fields=["status", "ended_at"])
    _clear_loan_caches(loan)
    if was_active:
        _clear_selection(loan.borrower, loan.roster_entry)
        _unpuppet_sessions(loan.roster_entry, keep=_holder_account(loan.roster_entry))


def guide_hand_off_counts(account: AccountDB, *, since: datetime) -> HandOffCounts:
    """How ``account``'s NPC hand-offs since ``since`` went (the Guide admin's summary).

    A loan ended at or after its scene finished was ended by the scene
    (``end_scene_loans`` runs after ``date_finished`` is written); one ended before
    that, or with no scene, was taken back early. One query.
    """
    early = (
        Q(scene__isnull=True)
        | Q(scene__date_finished__isnull=True)
        | Q(scene__date_finished__gt=F("ended_at"))
    )
    counts = NPCLoan.objects.filter(borrower=account).aggregate(
        accepted=Count("pk", filter=Q(started_at__gte=since)),
        declined=Count("pk", filter=Q(status=NPCLoanStatus.DECLINED, ended_at__gte=since)),
        taken_back_early=Count(
            "pk",
            filter=Q(status=NPCLoanStatus.ENDED, started_at__isnull=False, ended_at__gte=since)
            & early,
        ),
    )
    return HandOffCounts(**counts)


def end_scene_loans(scene: Scene) -> int:
    """End every loan made for ``scene`` that is still open; returns how many."""
    loans = list(
        NPCLoan.objects.filter(scene=scene, status__in=_OPEN_STATUSES).select_related(
            "roster_entry__character_sheet__character", "borrower"
        )
    )
    for loan in loans:
        end_loan(loan, by=None)
    return len(loans)
