"""Shared catalog-check invocation core (#2118, #3295).

Every surface that lets someone roll a check -- the SENIOR GM ad-hoc
``InvokeCatalogCheckAction``, a player's own ``SceneSelfCheckAction``, or a
GM's ``CallForCheckAction`` -- resolves against this one module. No caller may
bypass it to compose a freeform stat/skill/difficulty combination; see the
RATIFIED invariant on ``actions.definitions.gm_adjudication``: every check
anyone rolls is an authored ``CheckType`` from the catalog, at a
``DifficultyChoice`` band -- never an integer, never an invented pairing.

This module never selects, composes, or fires a ``ConsequenceOutcome``/
consequence pool -- it only resolves catalog references and bands. Firing
``perform_check`` and interpreting its result is each caller's own job.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from actions.types import ActionResult
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_model_by_pk_or_name
from world.scenes.action_constants import DifficultyChoice

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType

#: Default catalog-miss hint. Callers with their own discovery command should
#: pass their own ``not_found_hint`` to ``resolve_check_type_ref`` instead.
DEFAULT_CATALOG_HINT = "No such check -- try `check find <term>`."
FIND_RESULT_LIMIT = 15
DESCRIPTION_SNIPPET_LEN = 80


def catalog_queryset(*, owner_sheet: CharacterSheet | None = None) -> QuerySet[CheckType]:
    """Active ``CheckType`` catalog rows, excluding other characters' synthesized checks.

    A staff/lore-authored row (``owner_sheet`` NULL) is always visible. A
    per-character synthesized row (one per ``CharacterSheet``, minted by
    ``world.magic.seeds_checks.ensure_character_magic_check_type``) is visible
    only to its own owner -- pass the invoking character's sheet as
    ``owner_sheet`` to include it. Omit it (the GM catalog browse, or any
    caller not scoped to one character) to see staff-authored rows only,
    mirroring ``CheckTypeViewSet``'s existing scope.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    qs = CheckType.objects.filter(is_active=True).select_related("category")
    if owner_sheet is None:
        return qs.filter(owner_sheet__isnull=True)
    return qs.filter(Q(owner_sheet__isnull=True) | Q(owner_sheet=owner_sheet))


def check_type_summary(check_type: CheckType) -> str:
    """Return the "stat+skill" trait pairing summary for a catalog listing row."""
    names = [
        ctt.trait.name for ctt in check_type.traits.select_related("trait").order_by("-weight")
    ]
    return " + ".join(names) if names else "(no traits configured)"


def description_snippet(check_type: CheckType) -> str:
    text = (check_type.description or "").strip()
    if len(text) <= DESCRIPTION_SNIPPET_LEN:
        return text
    return text[: DESCRIPTION_SNIPPET_LEN - 1].rstrip() + "..."


def format_catalog_row(check_type: CheckType) -> str:
    return (
        f"[{check_type.pk}] {check_type.name} ({check_type_summary(check_type)})"
        f" -- {description_snippet(check_type)}"
    )


def search_catalog(
    query: str,
    *,
    owner_sheet: CharacterSheet | None = None,
    limit: int = FIND_RESULT_LIMIT,
) -> list[CheckType]:
    """Search the authored, active ``CheckType`` catalog by name, trait, or description.

    A bare or empty query lists the catalog head so finding the right check is
    always the paved path, never invention (#2118 Decision 4).
    """
    qs = catalog_queryset(owner_sheet=owner_sheet)
    query = query.strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(traits__trait__name__icontains=query)
        ).distinct()
    return list(qs.order_by("category__display_order", "display_order", "name")[:limit])


def render_catalog_listing(query: str, matches: list[CheckType]) -> str:
    """Render a ``search_catalog`` result as a find/list-mode message."""
    if not matches:
        return f"No checks matched {query!r}." if query.strip() else "The catalog is empty."
    header = f"Checks matching {query.strip()!r}:" if query.strip() else "Check catalog:"
    lines = [header, *(format_catalog_row(ct) for ct in matches)]
    return "\n".join(lines)


def resolve_check_type_ref(
    check_type_ref: str,
    *,
    owner_sheet: CharacterSheet | None = None,
    not_found_hint: str = DEFAULT_CATALOG_HINT,
) -> CheckType | ActionResult:
    """Resolve *check_type_ref* (pk-or-name) against the shared catalog, or refuse.

    Returns the resolved ``CheckType``, or a failing ``ActionResult`` a caller
    can return directly.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type_ref = str(check_type_ref or "").strip()
    if not check_type_ref:
        return ActionResult(success=False, message=not_found_hint)

    try:
        return resolve_model_by_pk_or_name(
            CheckType,
            check_type_ref,
            qs=catalog_queryset(owner_sheet=owner_sheet),
            not_found_msg=not_found_hint,
        )
    except CommandError as err:
        return ActionResult(success=False, message=str(err))


def resolve_band(difficulty: object) -> str | ActionResult:
    """Validate *difficulty* against ``DifficultyChoice`` -- no integers anywhere."""
    if difficulty not in DifficultyChoice.values:
        return ActionResult(
            success=False,
            message="Pick a difficulty band: " + ", ".join(DifficultyChoice.values) + ".",
        )
    return difficulty
