"""GM adjudication toolkit: catalog check invocation, GM awards, condition application (#2118).

Governing invariant (RATIFIED -- Tehom, 2026-07-09): **GMs can never invent checks
or consequence pools on whim.** Every code path in this module resolves against an
authored catalog row (``CheckType``, a ``DifficultyChoice`` band, a ``Trait``, or a
``ConditionTemplate``) -- there is no integer difficulty parameter, no free-form
stat/skill passthrough, and no ``ConsequenceOutcome``/consequence-pool reference
anywhere here. ``InvokeCatalogCheckAction`` fires ``perform_check`` and returns a
graded, number-free result to the invoking GM only; it never selects, composes, or
fires a consequence pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.base import Action
from actions.prerequisites import IsSceneGMPrerequisite, MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_model_by_pk_or_name
from world.gm.constants import GMLevel
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType

# Ascending TRIVIAL..HARROWING order -- DIFFICULTY_VALUES is authored in this order
# and dicts preserve insertion order, so this is the single source of truth for
# "one band up/down" shifts (Decision 3: at most one band, never an integer offset).
_DIFFICULTY_ORDER: tuple[str, ...] = tuple(DIFFICULTY_VALUES.keys())

_CATALOG_HINT = "No such check -- try `gm check find <term>`."
_FIND_RESULT_LIMIT = 15
_DESCRIPTION_SNIPPET_LEN = 80

# GMAwardAction.award_type values.
_AWARD_TYPE_XP = "xp"
_AWARD_TYPE_DEVELOPMENT = "development"


def _check_type_summary(check_type: CheckType) -> str:
    """Return the "stat+skill" trait pairing summary for a catalog listing row."""
    names = [
        ctt.trait.name for ctt in check_type.traits.select_related("trait").order_by("-weight")
    ]
    return " + ".join(names) if names else "(no traits configured)"


def _description_snippet(check_type: CheckType) -> str:
    text = (check_type.description or "").strip()
    if len(text) <= _DESCRIPTION_SNIPPET_LEN:
        return text
    return text[: _DESCRIPTION_SNIPPET_LEN - 1].rstrip() + "..."


def _format_catalog_row(check_type: CheckType) -> str:
    return (
        f"[{check_type.pk}] {check_type.name} ({_check_type_summary(check_type)})"
        f" -- {_description_snippet(check_type)}"
    )


def _search_catalog(query: str) -> list[CheckType]:
    """Search the authored, active CheckType catalog by name, trait, or description.

    The discovery road (Decision 4): a bare search or empty query lists the catalog
    head so finding the right check is always the paved path, never invention.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.checks.models import CheckType  # noqa: PLC0415

    qs = CheckType.objects.filter(is_active=True).select_related("category")
    query = query.strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(traits__trait__name__icontains=query)
        ).distinct()
    return list(
        qs.order_by("category__display_order", "display_order", "name")[:_FIND_RESULT_LIMIT]
    )


def _shift_band(band: str, *, easier: bool) -> str | None:
    """Shift *band* exactly one step toward TRIVIAL (easier) or HARROWING (harder).

    Returns ``None`` when the shift would go out of bounds -- callers must refuse
    rather than clamp (Decision 3).
    """
    index = _DIFFICULTY_ORDER.index(band)
    new_index = index - 1 if easier else index + 1
    if new_index < 0 or new_index >= len(_DIFFICULTY_ORDER):
        return None
    return _DIFFICULTY_ORDER[new_index]


def _resolve_shift(
    difficulty: str, edge_reason: str, setback_reason: str
) -> tuple[str, str] | ActionResult:
    """Return ``(effective_band, shift_note)`` for *difficulty*, or a failure result.

    Extracted from ``InvokeCatalogCheckAction._invoke`` to keep its own
    return-statement count low (PLR0911) -- mirrors the
    ``_resolve_add_opponent_inputs`` pattern in ``gm_combat.py``.
    """
    if edge_reason and setback_reason:
        return ActionResult(success=False, message="Shift with edge or setback, not both.")
    if edge_reason:
        shifted = _shift_band(difficulty, easier=True)
        if shifted is None:
            return ActionResult(success=False, message="Already at the easiest band.")
        return shifted, f" [edge -> {DifficultyChoice(shifted).label}: {edge_reason}]"
    if setback_reason:
        shifted = _shift_band(difficulty, easier=False)
        if shifted is None:
            return ActionResult(success=False, message="Already at the hardest band.")
        return shifted, f" [setback -> {DifficultyChoice(shifted).label}: {setback_reason}]"
    return difficulty, ""


@dataclass
class InvokeCatalogCheckAction(Action):
    """Invoke an authored ``CheckType`` at a ``DifficultyChoice`` band, or search it (#2118).

    Catalog-only per the RATIFIED invariant above. The only inputs are a
    ``check_type_ref`` (pk-or-name, resolved against the shared catalog only --
    unresolvable refuses with a hint back to ``find``), a ``difficulty`` band
    (validated against ``DifficultyChoice`` -- no integers accepted anywhere), and
    an optional ``edge_reason``/``setback_reason`` (mutually exclusive) shifting the
    band by exactly one step, echoed into the result. Fires ``perform_check`` as-is
    -- it never selects, composes, or fires a ``ConsequenceOutcome``/consequence
    pool, and no parameter on this action could.

    Two modes, discriminated by the ``target`` kwarg:
    - No ``target``: discovery/find mode. Optional ``query`` searches the catalog
      by name, stat+skill trait, or description snippet; omitted lists the head of
      the catalog. The paved road to finding the right check (Decision 4).
    - ``target`` set: invoke mode, described above.

    The result is graded and number-free (``CheckResult.outcome_name`` only --
    never raw points/roll/success_level) and goes to the invoking GM only; no
    audit model records it (Decision 6) -- the GM narrates via pose.
    """

    key: str = "gm_invoke_check"
    name: str = "Invoke Catalog Check"
    icon: str = "dice"
    category: str = "gm"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return self._find(kwargs)
        return self._invoke(target, kwargs)

    def _find(self, kwargs: dict[str, Any]) -> ActionResult:
        query = str(kwargs.get("query") or "")
        matches = _search_catalog(query)
        if not matches:
            message = f"No checks matched {query!r}." if query.strip() else "The catalog is empty."
            return ActionResult(success=True, message=message)
        header = f"Checks matching {query.strip()!r}:" if query.strip() else "Check catalog:"
        lines = [header, *(_format_catalog_row(ct) for ct in matches)]
        return ActionResult(success=True, message="\n".join(lines))

    def _invoke(self, target: ObjectDB, kwargs: dict[str, Any]) -> ActionResult:
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.checks.services import perform_check  # noqa: PLC0415

        check_type_ref = str(kwargs.get("check_type_ref") or "").strip()
        if not check_type_ref:
            return ActionResult(success=False, message=_CATALOG_HINT)

        try:
            check_type = resolve_model_by_pk_or_name(
                CheckType,
                check_type_ref,
                qs=CheckType.objects.filter(is_active=True),
                not_found_msg=_CATALOG_HINT,
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        difficulty = kwargs.get("difficulty")
        if difficulty not in DifficultyChoice.values:
            return ActionResult(
                success=False,
                message="Pick a difficulty band: " + ", ".join(DifficultyChoice.values) + ".",
            )

        edge_reason = str(kwargs.get("edge_reason") or "").strip()
        setback_reason = str(kwargs.get("setback_reason") or "").strip()

        shift_result = _resolve_shift(difficulty, edge_reason, setback_reason)
        if isinstance(shift_result, ActionResult):
            return shift_result
        effective_band, shift_note = shift_result

        result = perform_check(
            target,
            check_type,
            target_difficulty=DIFFICULTY_VALUES[effective_band],
        )
        band_label = DifficultyChoice(difficulty).label
        message = (
            f"{target.key}: {check_type.name} ({band_label}){shift_note} -> {result.outcome_name}"
        )
        return ActionResult(success=True, message=message)


@dataclass
class GMAwardAction(Action):
    """JUNIOR-tier GM action: award XP or development points to a participant (#2118).

    Wraps ``award_xp``/``award_development_points``
    (``world/progression/services/awards.py``) with ``ProgressionReason.GM_AWARD``
    and ``gm=actor.active_account`` -- the first production caller of the
    pre-existing ``gm=`` kwarg + ``GM_AWARD`` reason. Gated on
    ``IsSceneGMPrerequisite`` + ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff
    bypass preserved) -- pure fiat, the same trust bar as
    ``GrantItemAction``/``SetSituationAction``.
    """

    key: str = "gm_award_progression"
    name: str = "GM Award"
    icon: str = "star"
    category: str = "gm"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite(), MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="A target character is required.")

        award_type = str(kwargs.get("award_type") or "").strip().lower()
        description = str(kwargs.get("description") or "").strip()

        if award_type == _AWARD_TYPE_XP:
            return self._award_xp(actor, target, kwargs.get("amount"), description)
        if award_type == _AWARD_TYPE_DEVELOPMENT:
            return self._award_development(actor, target, kwargs, description)
        return ActionResult(success=False, message="award_type must be 'xp' or 'development'.")

    def _award_xp(
        self,
        actor: ObjectDB,
        target: ObjectDB,
        amount: Any,
        description: str,
    ) -> ActionResult:
        from typeclasses.characters import Character  # noqa: PLC0415
        from world.progression.services.awards import award_xp  # noqa: PLC0415
        from world.progression.types import ProgressionReason  # noqa: PLC0415

        # active_account is a Character-only property; target is typed ObjectDB.
        account = target.active_account if isinstance(target, Character) else None
        if account is None:
            return ActionResult(success=False, message=f"{target.key} has no controlling account.")

        amount_int = _coerce_positive_int(amount)
        if amount_int is None:
            return ActionResult(success=False, message="amount must be a positive whole number.")

        from typeclasses.characters import Character  # noqa: PLC0415

        gm_account = actor.active_account if isinstance(actor, Character) else None
        try:
            award_xp(
                account,
                amount_int,
                reason=ProgressionReason.GM_AWARD,
                description=description,
                gm=gm_account,
            )
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(success=True, message=f"Awarded {amount_int} XP to {target.key}.")

    def _award_development(
        self,
        actor: ObjectDB,
        target: ObjectDB,
        kwargs: dict[str, Any],
        description: str,
    ) -> ActionResult:
        from world.progression.services.awards import award_development_points  # noqa: PLC0415
        from world.progression.types import DevelopmentSource, ProgressionReason  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=f"{target.key} has no character sheet.")

        trait_ref = str(kwargs.get("trait_ref") or "").strip()
        if not trait_ref:
            return ActionResult(
                success=False, message="A trait is required for development points."
            )

        try:
            trait = resolve_model_by_pk_or_name(
                Trait,
                trait_ref,
                not_found_msg=f"No trait named {trait_ref!r}.",
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        amount_int = _coerce_positive_int(kwargs.get("amount"))
        if amount_int is None:
            return ActionResult(success=False, message="amount must be a positive whole number.")

        from typeclasses.characters import Character  # noqa: PLC0415

        gm_account = actor.active_account if isinstance(actor, Character) else None
        try:
            award_development_points(
                sheet,
                trait,
                DevelopmentSource.OTHER,
                amount_int,
                reason=ProgressionReason.GM_AWARD,
                description=description,
                gm=gm_account,
            )
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message=f"Awarded {amount_int} development point(s) in {trait.name} to {target.key}.",
        )


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or ``None`` if it isn't one.

    Fails loud (returns None -> caller refuses) rather than silently coercing a
    negative/zero amount to something valid.
    """
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _resolve_condition_target(kwargs: dict[str, Any]) -> tuple[Any, Any] | ActionResult:
    """Return ``(target, template)`` or a failure ``ActionResult``.

    Extracted from ``GMApplyConditionAction.execute`` to keep its own
    return-statement count low (PLR0911) -- mirrors the
    ``_resolve_add_opponent_inputs`` pattern in ``gm_combat.py``.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    target = kwargs.get("target")
    if target is None:
        return ActionResult(success=False, message="A target character is required.")

    condition_ref = str(kwargs.get("condition_ref") or "").strip()
    if not condition_ref:
        return ActionResult(success=False, message="A condition name is required.")

    try:
        template = ConditionTemplate.get_by_name(condition_ref)
    except ConditionTemplate.DoesNotExist:
        return ActionResult(success=False, message=f"No condition named {condition_ref!r}.")

    return target, template


def _resolve_condition_bounds(kwargs: dict[str, Any]) -> tuple[int, int | None] | ActionResult:
    """Return ``(severity, duration_rounds)`` overrides, or a failure ``ActionResult``.

    Fails loud on a non-positive override rather than silently clamping one
    (Decision 5); an absent kwarg falls back to ``apply_condition``'s own
    authored default (severity 1; ``template.default_duration_value``).
    """
    severity = 1
    severity_raw = kwargs.get("severity")
    if severity_raw is not None:
        coerced = _coerce_positive_int(severity_raw)
        if coerced is None:
            return ActionResult(success=False, message="severity must be a positive whole number.")
        severity = coerced

    duration_rounds = None
    duration_raw = kwargs.get("duration_rounds")
    if duration_raw is not None:
        coerced = _coerce_positive_int(duration_raw)
        if coerced is None:
            return ActionResult(
                success=False, message="duration_rounds must be a positive whole number."
            )
        duration_rounds = coerced

    return severity, duration_rounds


@dataclass
class GMApplyConditionAction(Action):
    """JUNIOR-tier GM action: apply an authored ``ConditionTemplate`` by fiat (#2118).

    Catalog-bounded like the check verb: only an authored ``ConditionTemplate``
    (resolved via ``ConditionTemplate.get_by_name`` -- exact name, matching the
    hot-path lookup every other production caller uses) may be applied; there is
    no free-form mechanical effect. ``severity``/``duration_rounds`` are optional
    overrides of ``apply_condition``'s own authored defaults (severity 1;
    ``template.default_duration_value``); the model defines no upper bound on
    either field, so Decision 5 is honored by failing loud on a non-positive
    value rather than silently clamping one. ``note`` is narration only (stored as
    ``source_description``) -- it never becomes a mechanical effect. Gated on
    ``IsSceneGMPrerequisite`` + ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)``.
    """

    key: str = "gm_apply_condition"
    name: str = "Apply Condition"
    icon: str = "sparkles"
    category: str = "gm"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite(), MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.conditions.services import apply_condition  # noqa: PLC0415

        resolved = _resolve_condition_target(kwargs)
        if isinstance(resolved, ActionResult):
            return resolved
        target, template = resolved

        bounds = _resolve_condition_bounds(kwargs)
        if isinstance(bounds, ActionResult):
            return bounds
        severity, duration_rounds = bounds

        note = str(kwargs.get("note") or "").strip()

        result = apply_condition(
            target,
            template,
            severity=severity,
            duration_rounds=duration_rounds,
            source_character=actor,
            source_description=note,
        )
        if not result.success:
            return ActionResult(
                success=False,
                message=f"{template.name} was not applied ({result.message}).",
            )

        return ActionResult(success=True, message=f"{target.key} is now {template.name}.")
