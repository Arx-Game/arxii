"""Alt-guard helpers for resolving the acting CharacterSheet from an API request.

These helpers enforce the project convention: when an account has multiple active
tenures, the caller must explicitly identify which character is acting.  This
prevents implicit first-sheet selection, which would hide an authoring decision
that belongs to the caller.

Moved here from ``views.py`` so that serializers can import them without creating
a circular dependency (serializers → views → serializers).
"""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from world.character_sheets.models import CharacterSheet

# Error messages — module constants keep tests stable and satisfy STRING_LITERAL.
_ERR_NO_ACTIVE_SHEET = "No active character sheet for this account."
_ERR_ENDORSER_SHEET_REQUIRED = (
    "endorser_sheet_id is required when account has multiple active tenures."
)
_ERR_ENDORSER_SHEET_INVALID = "Requested endorser_sheet_id is not among your active tenures."
_ERR_ACTOR_SHEET_REQUIRED = "{key} is required when account has multiple active tenures."
_ERR_ACTOR_SHEET_INVALID = "Requested {key} is not among your active tenures."


def _resolve_actor_sheet(
    request: Request,
    body_key: str,
    *,
    from_query: bool = False,
) -> CharacterSheet:
    """Return the CharacterSheet to use as the acting character for an incoming request.

    Mirrors ``_resolve_endorser_sheet`` but accepts both POST body and GET query-param
    sourcing via the ``from_query`` flag.  This is the shared alt-guard helper used by
    any endpoint where the requesting account must pick a character to act as.

    ``body_key`` names the request field that carries the explicit sheet PK:
    - ``from_query=False`` (default) → reads from ``request.data`` (POST body)
    - ``from_query=True`` → reads from ``request.query_params`` (GET endpoint)

    Rules:
    - No active tenures → raise ``PermissionDenied``.
    - Single active tenure → return that sheet.
    - Multiple tenures without explicit key → raise ``ValidationError``.
    - Multiple tenures with valid key → return that sheet.
    """
    account = request.user
    sheets = list(
        CharacterSheet.objects.filter(
            roster_entry__tenures__player_data__account=account,
            roster_entry__tenures__end_date__isnull=True,
        )
    )
    if not sheets:
        raise PermissionDenied(_ERR_NO_ACTIVE_SHEET)
    if len(sheets) == 1:
        return sheets[0]
    # Multiple active tenures — explicit sheet required.
    source = request.query_params if from_query else request.data
    requested_pk = source.get(body_key)  # noqa: STRING_LITERAL — parameterised body/query key
    if requested_pk is None:
        raise serializers.ValidationError(
            {body_key: _ERR_ACTOR_SHEET_REQUIRED.format(key=body_key)}
        )
    try:
        return next(s for s in sheets if s.pk == int(requested_pk))
    except (StopIteration, ValueError) as exc:
        raise PermissionDenied(_ERR_ACTOR_SHEET_INVALID.format(key=body_key)) from exc


def _resolve_endorser_sheet(request: Request) -> CharacterSheet:
    """Return the CharacterSheet to use as endorser for an incoming request.

    Single active tenure → return that sheet.
    Multiple active tenures → require explicit ``endorser_sheet_id`` in the POST
    body (alt system guard — no implicit first-sheet selection per project
    conventions).
    No active tenures → raise PermissionDenied.

    Delegates to ``_resolve_actor_sheet`` with ``body_key="endorser_sheet_id"``.
    Kept as a named wrapper for callers using the old name.
    """
    return _resolve_actor_sheet(request, body_key="endorser_sheet_id")  # noqa: STRING_LITERAL — body key name
