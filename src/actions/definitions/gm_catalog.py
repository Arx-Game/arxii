"""GM scenario catalog: per-type situation find + suggestion inbox (#2127, ADR-0110).

Governing invariant (extends #2118's ``gm_adjudication.py`` "discovery, never
invention" shape to the rest of the catalog): ``FindSituationAction`` is
strictly read-only -- it never selects, composes, or writes a live
``consequence_pool`` FK anywhere, and ``ConsequencePoolGuide`` rows it surfaces
are advisory text only (Decision 7). ``SubmitCatalogSuggestionAction`` never
auto-creates a live catalog row -- it only ever creates a ``CatalogSuggestion``
that lands in the staff inbox for a human decision (Decision 7/8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_model_by_pk_or_name
from world.gm.constants import (
    PROPOSAL_KIND_MIN_LEVEL,
    CatalogSuggestionProposalKind,
    GMLevel,
    gm_level_index,
)
from world.scenes.action_constants import DifficultyChoice
from world.societies.constants import RenownRisk

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.gm.models import SituationKind
    from world.mechanics.models import SituationTemplate

_FIND_RESULT_LIMIT = 15
_DESCRIPTION_SNIPPET_LEN = 80


def _description_snippet(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _DESCRIPTION_SNIPPET_LEN:
        return text
    return text[: _DESCRIPTION_SNIPPET_LEN - 1].rstrip() + "..."


def _format_template_row(template: SituationTemplate) -> str:
    snippet = _description_snippet(template.description_template)
    row = f"[{template.pk}] {template.name}"
    return f"{row} -- {snippet}" if snippet else row


def _search_situation_templates(query: str, *, limit: int = _FIND_RESULT_LIMIT) -> list:
    from django.db.models import Q  # noqa: PLC0415

    from world.mechanics.models import SituationTemplate  # noqa: PLC0415

    qs = SituationTemplate.objects.all()
    query = query.strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description_template__icontains=query))
    return list(qs.order_by("name")[:limit])


def _actor_breadth_index(actor: ObjectDB) -> int:
    """Return the actor's GM-level index for breadth gating, staff = maximum breadth.

    Mirrors ``MinimumGMLevelPrerequisite.is_met``'s staff-bypass + level lookup,
    but returns an index for filtering rather than a pass/fail against one
    floor -- ``FindSituationAction`` filters an entire kind list, not a single gate.
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415
    from world.gm.constants import GM_LEVEL_ORDER  # noqa: PLC0415
    from world.gm.models import GMProfile  # noqa: PLC0415

    if is_staff_observer(actor):
        return len(GM_LEVEL_ORDER) - 1

    try:
        account = actor.active_account
    except AttributeError:
        account = None
    if account is None:
        return 0

    try:
        level = account.gm_profile.level
    except GMProfile.DoesNotExist:
        return 0
    return gm_level_index(level)


def _search_situation_kinds(query: str, actor_level_index: int) -> list[SituationKind]:
    """Return SituationKinds matching *query* within the actor's breadth.

    Filtered server-side on ``SituationKind.minimum_gm_level`` (Decision 9) --
    a kind above the actor's tier never appears in results, even if the name
    matches exactly (the leak-analysis contract: never a client-side hide).
    """
    from world.gm.models import SituationKind  # noqa: PLC0415

    kinds = SituationKind.objects.cached_all()
    query = query.strip().lower()
    if query:
        kinds = [k for k in kinds if query in k.name.lower()]
    kinds = [k for k in kinds if gm_level_index(k.minimum_gm_level) <= actor_level_index]
    return sorted(kinds, key=lambda k: k.name)


def _format_kind_guidance(kind: SituationKind, risk: str | None) -> list[str]:
    lines = [f"Kind: {kind.name} (min tier: {GMLevel(kind.minimum_gm_level).label})"]
    if kind.description:
        lines.append(f"  {kind.description}")
    lines.extend(_format_check_fits(kind))
    lines.extend(_format_difficulty_guides(kind, risk))
    lines.extend(_format_pool_guides(kind))
    return lines


def _format_check_fits(kind: SituationKind) -> list[str]:
    """Format the ``Checks that fit`` section for a SituationKind."""
    fits = list(kind.check_fits.select_related("check_type").order_by("check_type__name"))
    if not fits:
        return []
    lines = ["  Checks that fit:"]
    for fit in fits:
        row = f"    [{fit.check_type.pk}] {fit.check_type.name}"
        lines.append(f"{row} -- {fit.fit_notes}" if fit.fit_notes else row)
    return lines


def _format_difficulty_guides(kind: SituationKind, risk: str | None) -> list[str]:
    """Format the ``Difficulty guide`` section, optionally filtered by *risk*."""
    guides = kind.difficulty_guides.all()
    if risk:
        guides = guides.filter(risk=risk)
    guides = list(guides.order_by("risk"))
    if not guides:
        return []
    lines = ["  Difficulty guide:"]
    for guide in guides:
        band_label = DifficultyChoice(guide.recommended_difficulty).label
        risk_label = RenownRisk(guide.risk).label
        row = f"    {risk_label} -> {band_label}"
        lines.append(f"{row} -- {guide.guidance_text}" if guide.guidance_text else row)
    return lines


def _format_pool_guides(kind: SituationKind) -> list[str]:
    """Format the advisory consequence-pool guidance section."""
    pools = list(kind.pool_guides.select_related("pool").order_by("-is_default", "pool__name"))
    if not pools:
        return []
    lines = ["  Consequence pool guidance (advisory only -- never auto-applied):"]
    for pool_guide in pools:
        tag = " [default]" if pool_guide.is_default else ""
        row = f"    {pool_guide.pool.name}{tag}"
        criteria = pool_guide.selection_criteria
        lines.append(f"{row} -- {criteria}" if criteria else row)
    return lines


def _format_kind_results(
    kinds: list[SituationKind],
    risk: str | None,
    existing_lines: list[str],
    query: str,
) -> list[str]:
    """Format the SituationKind results (or the no-match fallback) for the catalog.

    Separates blank-line separators between sections from the per-kind guidance.
    """
    if not kinds:
        if not query:
            return []
        lines = list(existing_lines)
        if lines:
            lines.append("")
        lines.append(f"No situation kind matched {query!r} at your GM tier.")
        # Return only the appended lines (the caller already has existing_lines).
        return lines[len(existing_lines) :]
    lines: list[str] = []
    for kind in kinds:
        if lines or existing_lines:
            lines.append("")
        lines.extend(_format_kind_guidance(kind, risk))
    return lines


@dataclass
class FindSituationAction(Action):
    """STARTING-tier GM action: search situations by name or SituationKind (#2127).

    Extends #2118's ``gm check find`` shape to situations: search
    ``SituationTemplate`` by name/description, and (independently, by the same
    search term) any ``SituationKind`` whose name matches -- surfacing its
    proven-fit ``CheckType``s, authored ``SituationDifficultyGuide`` rows, and
    advisory ``ConsequencePoolGuide`` text. Read-only: no field or kwarg on this
    Action writes a `SituationTemplate`, `SituationKind`, or `consequence_pool`
    FK anywhere.

    Gated ``MinimumGMLevelPrerequisite(GMLevel.STARTING)`` -- lower than
    ``SetSituationAction``'s JUNIOR floor, since browsing mutates nothing.
    Kind results are additionally filtered server-side on
    ``SituationKind.minimum_gm_level`` against the actor's own GM level
    (Decision 9 breadth gating; staff see everything).
    """

    key: str = "gm_find_situation"
    name: str = "Find Situation"
    icon: str = "search"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        query = str(kwargs.get("query") or "").strip()
        risk = kwargs.get("risk")
        if risk is not None and risk not in RenownRisk.values:
            return ActionResult(
                success=False,
                message="Pick a risk tier: " + ", ".join(RenownRisk.values) + ".",
            )

        actor_level_index = _actor_breadth_index(actor)
        templates = _search_situation_templates(query)
        kinds = _search_situation_kinds(query, actor_level_index)

        lines: list[str] = []
        if templates:
            header = f"Situations matching {query!r}:" if query else "Situation catalog:"
            lines.append(header)
            lines.extend(_format_template_row(t) for t in templates)
        elif query:
            lines.append(f"No situation templates matched {query!r}.")

        lines.extend(_format_kind_results(kinds, risk, lines, query))

        if not lines:
            lines.append("The catalog is empty.")

        return ActionResult(success=True, message="\n".join(lines))


def _actor_can_propose(actor: ObjectDB, proposal_kind: str) -> tuple[bool, str]:
    """Return ``(allowed, refusal_reason)`` for *actor* proposing *proposal_kind*.

    Staff always bypass (User story 8 -- the unconditional bypass preserved on
    every new gate). A GM with no profile is refused, matching
    ``MinimumGMLevelPrerequisite``'s own missing-profile handling.
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415
    from world.gm.models import GMProfile  # noqa: PLC0415

    if is_staff_observer(actor):
        return True, ""

    required = PROPOSAL_KIND_MIN_LEVEL.get(proposal_kind, GMLevel.STARTING)
    try:
        account = actor.active_account
    except AttributeError:
        account = None
    if account is None:
        return False, "GM trust required."

    try:
        level = account.gm_profile.level
    except GMProfile.DoesNotExist:
        return False, "GM trust required."

    if gm_level_index(level) < gm_level_index(required):
        required_display = GMLevel(required).label
        return False, f"Suggesting a {proposal_kind} needs {required_display} trust or higher."
    return True, ""


@dataclass
class SubmitCatalogSuggestionAction(Action):
    """STARTING-tier GM action: submit a CatalogSuggestion to the staff inbox (#2127).

    Creates a ``CatalogSuggestion`` row via ``world.gm.services
    .submit_catalog_suggestion`` -- never a live catalog row. Gated
    ``MinimumGMLevelPrerequisite(GMLevel.STARTING)`` plus a ``proposal_kind``
    check against the actor's own GM level (Decision 9: STARTING/JUNIOR may
    propose NEW_SITUATION/CHECK_FIT/OTHER only; GM+ additionally
    DIFFICULTY_GUIDE; EXPERIENCED+ additionally POOL_GUIDE -- the single most
    guarded proposal kind, since it touches consequence-pool selection).
    """

    key: str = "gm_submit_catalog_suggestion"
    name: str = "Submit Catalog Suggestion"
    icon: str = "lightbulb"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.gm.services import submit_catalog_suggestion  # noqa: PLC0415

        proposal_kind = str(kwargs.get("proposal_kind") or "").strip().lower()
        if proposal_kind not in CatalogSuggestionProposalKind.values:
            return ActionResult(
                success=False,
                message=(
                    "proposal_kind must be one of: "
                    + ", ".join(CatalogSuggestionProposalKind.values)
                    + "."
                ),
            )

        proposal_text = str(kwargs.get("proposal_text") or "").strip()
        if not proposal_text:
            return ActionResult(success=False, message="A suggestion needs some text.")

        allowed, reason = _actor_can_propose(actor, proposal_kind)
        if not allowed:
            return ActionResult(success=False, message=reason)

        situation_kind = None
        situation_kind_ref = str(kwargs.get("situation_kind_ref") or "").strip()
        if situation_kind_ref:
            from world.gm.models import SituationKind  # noqa: PLC0415

            try:
                situation_kind = resolve_model_by_pk_or_name(
                    SituationKind,
                    situation_kind_ref,
                    not_found_msg=f"No situation kind named {situation_kind_ref!r}.",
                )
            except CommandError as err:
                return ActionResult(success=False, message=str(err))

        # The actual puppeting account (mirrors deeds.py's _resolve_account) --
        # deliberately not the roster-tenure-derived active_account, since a
        # suggestion is OOC authoring by whoever is at the keyboard right now,
        # not tied to which PC they happen to be playing (mirrors
        # GMApplication.account, set directly from the submitting request.user).
        account = actor.account
        if account is None:
            return ActionResult(success=False, message="No account to submit as.")

        submit_catalog_suggestion(
            account,
            proposal_kind=proposal_kind,
            proposal_text=proposal_text,
            situation_kind=situation_kind,
        )
        return ActionResult(success=True, message="Suggestion submitted to staff for review.")
