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

Not decided here, and so not built: who deletes the alpha characters that fall into none of
the three kinds, and what the wipe should do about the tables in
``world.beta_reset.classification.UNDECIDED_AWAITING_RULING``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet

from world.beta_reset.classification import UNDECIDED_AWAITING_RULING
from world.beta_reset.constants import CutoverPolicy
from world.beta_reset.exceptions import CarryOverError
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
from world.roster.models import Roster, RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.services.activity import end_all_tenures_to_available

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
        if self.reserve_to_account_id is not None:
            parts.append("reserve to the account that held it")
        parts.append(self.progress.summary())
        return ": ".join([parts[0], "; ".join(parts[1:])])


@dataclass(frozen=True)
class CutoverPlan:
    """Every policy step the cutover would run, in order."""

    steps: tuple[CutoverStep, ...]
    carry_over_already_covered: tuple[str, ...]

    def count(self, policy: CutoverPolicy) -> int:
        return sum(1 for step in self.steps if step.policy == policy)


@dataclass(frozen=True)
class CutoverReport:
    """The result of ``run_beta_cutover``, dry-run or real."""

    executed: bool
    plan: CutoverPlan
    wipe: WipeReport
    undecided_models: int


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


def _step(
    policy: CutoverPolicy,
    sheet: CharacterSheet,
    entry: RosterEntry | None,
    tenures: list[RosterTenure],
    *,
    reserve_to: AccountDB | None = None,
) -> CutoverStep:
    open_tenures = [tenure for tenure in tenures if tenure.is_current]
    holder = open_tenures[0].player_data.account.username if open_tenures else None
    return CutoverStep(
        policy=policy,
        sheet=sheet,
        name=sheet.character.db_key,
        entry=entry,
        open_tenures=len(open_tenures),
        holder=holder,
        reserve_to_account_id=None if reserve_to is None else reserve_to.pk,
        progress=plan_progress_reset(sheet),
    )


def _carry_over_step(
    sheet: CharacterSheet, entry: RosterEntry | None, tenures: list[RosterTenure]
) -> CutoverStep | None:
    """The step for one ``--carry-over`` character, or None when policy already covers it."""
    name = sheet.character.db_key
    if entry is None:
        return _step(CutoverPolicy.CARRY_OVER, sheet, None, [])
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
        entry,
        tenures,
        reserve_to=tenures[0].player_data.account,
    )


def plan_cutover(*, carry_over_sheet_ids: Iterable[int] = ()) -> CutoverPlan:
    """Read-only: what each policy step would do. Raises ``CarryOverError`` on a bad name."""
    entries = _entries(RosterEntry.objects.exclude(roster__roster_type=RosterType.NPC))
    wanted = list(dict.fromkeys(carry_over_sheet_ids))
    carry_entries = {
        entry.character_sheet_id: entry
        for entry in _entries(RosterEntry.objects.filter(character_sheet_id__in=wanted))
    }
    tenures = _tenures_by_entry([*entries, *carry_entries.values()])

    steps: list[CutoverStep] = []
    for entry in entries:
        if entry.creation_provenance in (CreationProvenance.STAFF, CreationProvenance.GM_TABLE):
            policy = CutoverPolicy.ROSTER_CHARACTER
        elif entry.created_by_account_id is not None:
            policy = CutoverPolicy.RESERVED_OC
        else:
            continue
        steps.append(_step(policy, entry.character_sheet, entry, tenures[entry.pk]))

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
        step = _carry_over_step(sheet, entry, [] if entry is None else tenures[entry.pk])
        if step is None:
            covered.append(sheet.character.db_key)
        else:
            steps.append(step)
    return CutoverPlan(steps=tuple(steps), carry_over_already_covered=tuple(covered))


def execute_cutover(plan: CutoverPlan) -> None:
    """Run every policy step. Caller supplies the guards and the transaction."""
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
        reset_character_progress(step.sheet)


def run_beta_cutover(
    *,
    execute: bool = False,
    confirm: str | None = None,
    backup_verified_at: datetime | None = None,
    carry_over_sheet_ids: Iterable[int] = (),
) -> CutoverReport:
    """Dry-run (default) or execute the policy steps and then the wipe.

    ``execute=False`` touches nothing and runs no guard. ``execute=True`` runs the four
    guards before anything is read for writing, then the policy steps and the wipe in one
    transaction, so a failure part-way leaves the database as it was.
    """
    undecided = len(UNDECIDED_AWAITING_RULING)
    if not execute:
        plan = plan_cutover(carry_over_sheet_ids=carry_over_sheet_ids)
        return CutoverReport(False, plan, preview_pristine_world_wipe(), undecided)

    check_beta_reset_enabled()
    check_release_latch()
    check_confirmation_phrase(confirm)
    check_backup_verified(backup_verified_at)

    plan = plan_cutover(carry_over_sheet_ids=carry_over_sheet_ids)
    with transaction.atomic():
        execute_cutover(plan)
        wipe = wipe_pristine_world(
            execute=True, confirm=confirm, backup_verified_at=backup_verified_at
        )
    return CutoverReport(True, plan, wipe, undecided)
