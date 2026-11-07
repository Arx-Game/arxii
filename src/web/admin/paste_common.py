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

from collections.abc import Sequence
import hashlib
import json
from typing import Protocol

from django.db.models import QuerySet
from evennia.accounts.models import AccountDB

from web.admin.authoring.contributors import current_contributor, link_contributor
from world.contributors.models import ContentContributor

STATUS_CREATE = "create"
STATUS_SKIP = "skip"
STATUS_ERROR = "error"
ACTION_CHECK = "check"
ACTION_CREATE = "create"


class HasStatus(Protocol):
    status: str


def one(qs: QuerySet, what: str) -> tuple[object | None, str]:
    """Exactly one row, or the reason there is not."""
    rows = list(qs[:2])
    if not rows:
        return None, f"unknown {what}"
    if len(rows) > 1:
        return None, f"ambiguous {what}"
    return rows[0], ""


def counts(rows: Sequence[HasStatus]) -> dict[str, int]:
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
