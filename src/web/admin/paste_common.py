"""The generic half of an additions-only table paste (#5001).

Every paste on the Import Data hub shares this shape (ruled 2026-09-08 for the first
one, the Distinction Builder's "Add from a table", #3709): staff paste pipe-separated
rows, the view resolves every name against rows that already exist and previews each
row as ``create``, ``skip`` or ``error``; nothing is written until every row reads
create or skip, and a digest of the preview guards the confirm. A paste never updates,
never deletes and never creates a row it only refers to. Each paste keeps its own
columns, parser, digest payload and create step; what they share lives here.

Credit (owner ruling 2026-11-07): whatever a paste creates is credited to the operator,
and a superuser with no contributor yet is linked to one named after the account on the
spot, instead of being sent to the Authoring Workbench first.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import hashlib
import hmac
import json

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest
from evennia.accounts.models import AccountDB

from web.admin.authoring.contributors import current_contributor, link_contributor
from world.contributors.models import ContentContributor

STATUS_CREATE = "create"
STATUS_SKIP = "skip"
STATUS_ERROR = "error"
ACTION_CHECK = "check"
ACTION_CREATE = "create"


@dataclass(kw_only=True)
class PasteRow:
    """One pasted line as the preview shows it; each paste's row type extends this."""

    line_no: int
    status: str = STATUS_CREATE
    notes: list[str] = field(default_factory=list)

    def fail(self, note: str) -> None:
        self.status = STATUS_ERROR
        self.notes.append(note)

    def skip(self, note: str) -> None:
        self.status = STATUS_SKIP
        self.notes.append(note)


def one(qs: QuerySet, what: str) -> tuple[object | None, str]:
    """Exactly one row, or the reason there is not."""
    rows = list(qs[:2])
    if not rows:
        return None, f"unknown {what}"
    if len(rows) > 1:
        return None, f"ambiguous {what}"
    return rows[0], ""


def counts(rows: Sequence[PasteRow]) -> dict[str, int]:
    return {
        STATUS_CREATE: sum(r.status == STATUS_CREATE for r in rows),
        STATUS_SKIP: sum(r.status == STATUS_SKIP for r in rows),
        STATUS_ERROR: sum(r.status == STATUS_ERROR for r in rows),
    }


def digest_of(payload: object) -> str:
    """A digest of exactly what a preview showed; the confirm compares it."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def paste_contributor(user: AccountDB) -> ContentContributor:
    """The operator's contributor, linked on the spot when a superuser has none.

    Raises ``ValueError`` with a user-facing message when the account's name is already
    another account's contributor; the paste shows it and writes nothing.
    """
    contributor = current_contributor(user)
    if contributor is not None:
        return contributor
    return link_contributor(user, name=user.username)


@dataclass
class Checked:
    """A paste POST read once: the text, its rows, their counts and the preview's digest."""

    text: str
    rows: list
    counts: dict[str, int]
    digest: str
    action: str

    @property
    def context(self) -> dict[str, object]:
        return {"text": self.text, "rows": self.rows, "digest": self.digest, "counts": self.counts}


def check_post(
    request: HttpRequest,
    parse: Callable[[str], list],
    digest: Callable[[list], str],
) -> Checked:
    """Parse the posted table the way the preview did; the view renders or writes from it."""
    text = request.POST.get("text", "")
    rows = parse(text)
    return Checked(
        text=text,
        rows=rows,
        counts=counts(rows),
        digest=digest(rows),
        action=request.POST.get("action", ACTION_CHECK),
    )


_STALE = "The table or the database changed since the preview; check it again."
_ERROR_ROWS = "Fix every row that reads error; nothing was created."
_NOTHING = "Nothing to create."


def refusal(request: HttpRequest, checked: Checked) -> tuple[int, str] | None:
    """Why a create POST writes nothing, as a message level and text, or None to go ahead.

    A stale digest (the text or the database changed since the preview), any error row,
    or nothing left to create.
    """
    if not hmac.compare_digest(checked.digest, request.POST.get("digest", "")):
        return messages.ERROR, _STALE
    if checked.counts[STATUS_ERROR]:
        return messages.ERROR, _ERROR_ROWS
    if not checked.counts[STATUS_CREATE]:
        return messages.INFO, _NOTHING
    return None
