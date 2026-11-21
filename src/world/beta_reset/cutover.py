"""The beta cutover policy layer (#3055 PR 3).

``world.beta_reset.services.wipe_pristine_world`` strips play-state tables world-wide. This
module decides what happens to the characters that are kept, then runs the wipe, through the
same four guards (hardcoded constant, release latch, typed phrase, fresh-backup precheck).
Management command only; there is no admin surface.

Three kinds of kept character, each given the same treatment: every roster tenure ends, the
entry returns to the Available shelf when someone held it, and the character's play progress
is reset from the provenance ledger (``world.beta_reset.progress``).

- **Roster characters**: staff-authored and GM-table entries. Beta players claim them fresh.
- **Reserved original characters**: a player's own creation (``creation_provenance`` PLAYER
  with a ``created_by_account``). It survives progress-wiped and only that account may apply
  for it again (``world.roster.services.activity.is_reserved_against``). The two existing
  roster fields carry the reservation, so there is no schema change.
- **Carried-over characters**: a tester's character named with ``--carry-over``. An original
  character with no recorded author is reserved to the account that held it; a character
  with no roster entry is progress-reset in place.

The policy steps run BEFORE the wipe, because the progress reset reads the play-time ledger
rows the wipe deletes. Both run in one transaction. Alpha accounts, and their kudos, blocks
and friendships, are never touched.

The wipe deletes what ``SCOPE_TABLE`` names and nothing else. No step deletes an alpha
character that is none of the three kinds.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, transaction
from django.db.models import ProtectedError, QuerySet

from world.beta_reset.constants import CutoverPolicy
from world.beta_reset.exceptions import (
    BetaResetError,
    CarryOverError,
    CutoverFailedError,
    IncompleteLedgerError,
    WipeBlockedError,
)
from world.beta_reset.progress import (
    ProgressResetPlan,
    plan_progress_reset,
    reset_character_progress,
)
from world.beta_reset.services import (
    WipeReport,
    check_backup_verified,
    check_beta_reset_enabled,
    check_confirmation_phrase,
    check_release_latch,
    preview_pristine_world_wipe,
    wipe_pristine_world,
)
from world.character_sheets.models import CharacterSheet
from world.magic.models import Thread
from world.roster.models import Roster, RosterApplication, RosterEntry, RosterTenure
from world.roster.models.choices import ApplicationStatus, CreationProvenance, RosterType
from world.roster.services.activity import end_all_tenures_to_available, reserving_account_id

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB


@dataclass(frozen=True)
class CutoverStep:
    """What the cutover does to one kept character."""

    policy: CutoverPolicy
    sheet: CharacterSheet
    name: str
    entry: RosterEntry | None
    open_tenures: int
    holder: str | None
    reserve_to_account_id: int | None
    reserved_to: str | None
    rival_applications: int
    progress: ProgressResetPlan

    def describe(self) -> str:
        parts = [f"[{self.policy.label}] {self.name}"]
        if self.entry is not None:
            if self.open_tenures:
                held = f" held by {self.holder}" if self.holder else ""
                parts.append(
                    f"end {self.open_tenures} tenure(s){held} and return to the Available roster"
                )
            else:
                parts.append("no open tenure; stays on its shelf")
        else:
            parts.append("no roster entry")
        if self.reserved_to is not None:
            recorded = (
                " (set now from the account that held it)"
                if (self.reserve_to_account_id is not None)
                else ""
            )
            parts.append(f"reserved to {self.reserved_to}{recorded}")
        if self.rival_applications:
            parts.append(
                f"{self.rival_applications} pending application(s) from other accounts "
                "stay pending and can no longer be approved"
            )
        parts.append(self.progress.summary())
        parts.extend(f"LEDGER WARNING: {problem}" for problem in self.progress.problems)
        return ": ".join([parts[0], "; ".join(parts[1:])])


@dataclass(frozen=True)
class CutoverPlan:
    """Every policy step the cutover would run, in order."""

    steps: tuple[CutoverStep, ...]
    carry_over_already_covered: tuple[str, ...]

    def count(self, policy: CutoverPolicy) -> int:
        return sum(1 for step in self.steps if step.policy == policy)

    def ledger_findings(self) -> dict[str, list[str]]:
        """Every kept character whose ledger is not whole, with what is wrong."""
        return {
            step.name: list(step.progress.problems) for step in self.steps if step.progress.problems
        }


@dataclass(frozen=True)
class CutoverReport:
    """The result of ``run_beta_cutover``, dry-run or real."""

    executed: bool
    plan: CutoverPlan
    wipe: WipeReport


def _entries(queryset: QuerySet[RosterEntry]) -> list[RosterEntry]:
    """``queryset`` evaluated with the character and shelf each entry needs."""
    return list(
        queryset.select_related(
            "character_sheet__character", "created_by_account", "roster"
        ).order_by("pk")
    )


def _tenures_by_entry(entries: Iterable[RosterEntry]) -> dict[int, list[RosterTenure]]:
    """Every tenure of ``entries`` with its holder's account, newest first, in one query."""
    grouped: dict[int, list[RosterTenure]] = defaultdict(list)
    tenures = RosterTenure.objects.filter(roster_entry__in=list(entries)).select_related(
        "player_data__account"
    )
    for tenure in tenures:
        grouped[tenure.roster_entry_id].append(tenure)
    return grouped


@dataclass(frozen=True)
class _EntryContext:
    """What the plan has loaded about one roster entry, so a step needs no more queries."""

    entry: RosterEntry | None
    tenures: list[RosterTenure]
    applicants: list[int]


_NO_ENTRY = _EntryContext(entry=None, tenures=[], applicants=[])


def _step(
    policy: CutoverPolicy,
    sheet: CharacterSheet,
    context: _EntryContext,
    *,
    reserve_to: AccountDB | None = None,
) -> CutoverStep:
    entry = context.entry
    open_tenures = [tenure for tenure in context.tenures if tenure.is_current]
    holder = open_tenures[0].player_data.account.username if open_tenures else None
    reserved_id = reserve_to.pk if reserve_to is not None else None
    reserved_to = reserve_to.username if reserve_to is not None else None
    if reserve_to is None and entry is not None and reserving_account_id(entry) is not None:
        reserved_id = entry.created_by_account_id
        reserved_to = entry.created_by_account.username if entry.created_by_account else None
    rivals = (
        0
        if reserved_id is None
        else sum(1 for account_id in context.applicants if account_id != reserved_id)
    )
    return CutoverStep(
        policy=policy,
        sheet=sheet,
        name=sheet.character.db_key,
        entry=entry,
        open_tenures=len(open_tenures),
        holder=holder,
        reserve_to_account_id=None if reserve_to is None else reserve_to.pk,
        reserved_to=reserved_to,
        rival_applications=rivals,
        progress=plan_progress_reset(sheet),
    )


def _carry_over_step(
    sheet: CharacterSheet,
    entry: RosterEntry | None,
    tenures: list[RosterTenure],
    applicants: list[int],
) -> CutoverStep | None:
    """The step for one ``--carry-over`` character, or None when policy already covers it."""
    name = sheet.character.db_key
    if entry is None:
        return _step(CutoverPolicy.CARRY_OVER, sheet, _NO_ENTRY)
    if entry.roster.roster_type == RosterType.NPC:
        msg = f"{name} sits on the NPC shelf; a story NPC is not carried over."
        raise CarryOverError(msg)
    if entry.creation_provenance != CreationProvenance.PLAYER:
        msg = f"{name} is a roster character; the roster cutover already returns it."
        raise CarryOverError(msg)
    if entry.created_by_account_id is not None:
        return None
    # An original character with no recorded author: reserve it to whoever held it last,
    # or it would be open to every account.
    if not tenures:
        msg = f"{name} has no recorded author and no past holder, so it cannot be reserved."
        raise CarryOverError(msg)
    return _step(
        CutoverPolicy.CARRY_OVER,
        sheet,
        _EntryContext(entry, tenures, applicants),
        reserve_to=tenures[0].player_data.account,
    )


def _pending_applicants(sheet_ids: Iterable[int]) -> dict[int, list[int]]:
    """For each character sheet, the account of every pending application for it."""
    grouped: dict[int, list[int]] = defaultdict(list)
    pending = RosterApplication.objects.filter(
        character_id__in=list(sheet_ids), status=ApplicationStatus.PENDING
    ).values_list("character_id", "player_data_id")
    for sheet_id, account_id in pending:
        grouped[sheet_id].append(account_id)
    return grouped


def plan_cutover(*, carry_over_sheet_ids: Iterable[int] = ()) -> CutoverPlan:
    """Read-only: what each policy step would do. Raises ``CarryOverError`` on a bad name."""
    entries = _entries(RosterEntry.objects.exclude(roster__roster_type=RosterType.NPC))
    wanted = list(dict.fromkeys(carry_over_sheet_ids))
    carry_entries = {
        entry.character_sheet_id: entry
        for entry in _entries(RosterEntry.objects.filter(character_sheet_id__in=wanted))
    }
    tenures = _tenures_by_entry([*entries, *carry_entries.values()])
    applicants = _pending_applicants([*(entry.character_sheet_id for entry in entries), *wanted])

    steps: list[CutoverStep] = []
    for entry in entries:
        if entry.creation_provenance in (CreationProvenance.STAFF, CreationProvenance.GM_TABLE):
            policy = CutoverPolicy.ROSTER_CHARACTER
        elif entry.created_by_account_id is not None:
            policy = CutoverPolicy.RESERVED_OC
        else:
            continue
        context = _EntryContext(entry, tenures[entry.pk], applicants[entry.character_sheet_id])
        steps.append(_step(policy, entry.character_sheet, context))

    covered: list[str] = []
    sheets = {
        sheet.pk: sheet
        for sheet in CharacterSheet.objects.filter(pk__in=wanted).select_related("character")
    }
    for sheet_id in wanted:
        sheet = sheets.get(sheet_id)
        if sheet is None:
            msg = f"--carry-over {sheet_id}: no character sheet has that id."
            raise CarryOverError(msg)
        entry = carry_entries.get(sheet_id)
        step = _carry_over_step(
            sheet, entry, [] if entry is None else tenures[entry.pk], applicants[sheet_id]
        )
        if step is None:
            covered.append(sheet.character.db_key)
        else:
            steps.append(step)
    return CutoverPlan(steps=tuple(steps), carry_over_already_covered=tuple(covered))


def execute_cutover(plan: CutoverPlan, *, allow_incomplete_ledger: bool = False) -> None:
    """Run every policy step.

    Checks the enabled constant and the release latch itself, so no direct call runs after
    release; the typed phrase and the backup precheck stay on ``run_beta_cutover``. The caller
    supplies the transaction. Refuses before touching anything when a kept character's ledger
    is incomplete and ``allow_incomplete_ledger`` is False.
    """
    check_beta_reset_enabled()
    check_release_latch()
    findings = plan.ledger_findings()
    if findings and not allow_incomplete_ledger:
        raise IncompleteLedgerError(findings)
    entry_steps = [step for step in plan.steps if step.entry is not None]
    if entry_steps:
        # Resolved once, and only when there is an entry to move, so an empty plan needs no
        # seeded shelves. An unseeded Available shelf with entries to move is a deployment
        # error and fails loudly here, before any progress is reset.
        available = Roster.objects.get(roster_type=RosterType.AVAILABLE)
        for step in entry_steps:
            entry = step.entry
            if entry is None:
                continue
            if step.reserve_to_account_id is not None:
                entry.created_by_account_id = step.reserve_to_account_id
                entry.save(update_fields=["created_by_account"])
            end_all_tenures_to_available(entry, available)
    for step in plan.steps:
        reset_character_progress(step.sheet, allow_incomplete_ledger=allow_incomplete_ledger)


def _refresh_after_wipe(plan: CutoverPlan, capstone_thread_owner_ids: set[int]) -> None:
    """Make this process agree with what the wipe just deleted.

    The wipe removes capstone-anchored threads and their level unlocks, which a character's
    thread handler caches and which feed max health. So the handler is dropped for every
    character that owned one, and max health is recomputed for each kept character AFTER the
    wipe, not before it.
    """
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    kept = {step.sheet.pk: step.sheet for step in plan.steps}
    owners = CharacterSheet.objects.filter(
        pk__in=capstone_thread_owner_ids | set(kept)
    ).select_related("character")
    for sheet in owners:
        sheet.character.threads.invalidate()
    for sheet in kept.values():
        recompute_max_health_with_threads(sheet)


def run_beta_cutover(
    *,
    execute: bool = False,
    confirm: str | None = None,
    backup_verified_at: datetime | None = None,
    carry_over_sheet_ids: Iterable[int] = (),
    allow_incomplete_ledger: bool = False,
) -> CutoverReport:
    """Dry-run (default) or execute the policy steps and then the wipe.

    ``execute=False`` touches nothing and runs no guard. ``execute=True`` runs the four
    guards before anything is read for writing, then the policy steps and the wipe in one
    transaction, so a failure part-way leaves the database as it was. A ``ProtectedError``
    (or any other database error) is turned into a ``BetaResetError`` that names what blocked
    it, after the rollback.
    """
    if not execute:
        plan = plan_cutover(carry_over_sheet_ids=carry_over_sheet_ids)
        return CutoverReport(False, plan, preview_pristine_world_wipe())

    check_beta_reset_enabled()
    check_release_latch()
    check_confirmation_phrase(confirm)
    check_backup_verified(backup_verified_at)

    plan = plan_cutover(carry_over_sheet_ids=carry_over_sheet_ids)
    findings = plan.ledger_findings()
    if findings and not allow_incomplete_ledger:
        raise IncompleteLedgerError(findings)
    try:
        with transaction.atomic():
            execute_cutover(plan, allow_incomplete_ledger=allow_incomplete_ledger)
            owners = set(
                Thread.objects.filter(target_capstone__isnull=False).values_list(
                    "owner_id", flat=True
                )
            )
            wipe = wipe_pristine_world(
                execute=True, confirm=confirm, backup_verified_at=backup_verified_at
            )
            _refresh_after_wipe(plan, owners)
    except ProtectedError as exc:
        blocking = sorted({type(row).__name__ for row in exc.protected_objects})
        raise WipeBlockedError(blocking, str(exc.args[0])) from exc
    except BetaResetError:
        raise
    except (DatabaseError, ObjectDoesNotExist) as exc:
        raise CutoverFailedError(exc) from exc
    return CutoverReport(True, plan, wipe)
