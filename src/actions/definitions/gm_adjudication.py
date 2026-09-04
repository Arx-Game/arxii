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
from actions.definitions.gm_shift import resolve_band_shift
from actions.prerequisites import IsSceneGMPrerequisite, MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_model_by_pk_or_name
from world.gm.constants import GMLevel
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionTemplate


_CATALOG_HINT = "No such check -- try `gm check find <term>`."

# GMAwardAction.award_type values.
_AWARD_TYPE_XP = "xp"
_AWARD_TYPE_DEVELOPMENT = "development"
_AWARD_TYPE_FAVOR_TOKEN = "favor_token"  # noqa: S105 -- award-kind literal, not a secret
_AWARD_TYPE_STAT = "stat"
_AWARD_TYPE_TECHNIQUE = "technique"
_AWARD_TYPES = (
    _AWARD_TYPE_XP,
    _AWARD_TYPE_DEVELOPMENT,
    _AWARD_TYPE_FAVOR_TOKEN,
    _AWARD_TYPE_STAT,
    _AWARD_TYPE_TECHNIQUE,
)

# Failure message repeated across every action here that requires a resolved
# target character — extracted to satisfy the duplicated-literal SonarCloud
# smell (python:S1192).
MSG_TARGET_REQUIRED = "A target character is required."


def _resolve_gm_profile(actor: ObjectDB) -> Any | None:
    """Return the acting GM's ``GMProfile``, or ``None`` (staff with no profile, #3071).

    Mirrors ``_resolve_granting_tenure``'s none-safety shape — a staff account may
    reach a JUNIOR-gated GM action via the staff bypass on ``MinimumGMLevelPrerequisite``
    with no ``GMProfile`` of their own at all; callers that want to stamp provenance
    treat ``None`` as "no attributable GM profile," not a refusal.
    """
    from typeclasses.characters import Character  # noqa: PLC0415
    from world.gm.models import GMProfile  # noqa: PLC0415

    if not isinstance(actor, Character):
        return None
    account = actor.active_account
    if account is None:
        return None
    try:
        return account.gm_profile
    except GMProfile.DoesNotExist:
        return None


def _resolve_gm_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the ``target`` kwarg to an ``ObjectDB`` character (#3070).

    Telnet always passes an already-resolved ``ObjectDB``. The web REST dispatch
    path (``dispatch_player_action`` -> ``_dispatch_registry``) does no ObjectDB
    resolution of its own -- ``objectdb_target_kwargs`` only helps the *websocket*
    inputfunc, and only for wire keys ending in ``_id`` (see ``actions/CLAUDE.md``).
    Resolve a plain int pk here too, mirroring ``identification._resolve_identify_target``.
    Unlike that resolver, no persona indirection is needed: a ``CharacterSheet``'s pk
    equals its ``ObjectDB``'s pk (shared-pk O2O), so the web GM panel sends the
    target character's id directly -- the same id the scene payload's
    ``personas[].character_sheet`` field already carries.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    target = kwargs.get("target")
    if target is None or isinstance(target, ObjectDB):
        return target
    return ObjectDB.objects.filter(pk=target).first()


# Catalog resolve/find/band-validation core lives in ``world.checks.catalog_invocation``
# (#3295) -- extracted from this action so every catalog-check invocation surface
# (this SENIOR ad-hoc action, a player's scene self-check, a GM's call-for-check)
# resolves against the same shared code. Imported lazily inside methods below to
# match this module's existing lazy-import style.


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

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.SENIOR)`` — the ad-hoc check
    is a staff/senior stopgap for impromptu moments no authored situation covers.
    Player GMs below SENIOR trust should use ``SetSituationAction``
    (``setsituation``), where checks emerge from authored situations with pre-set
    outcomes (ADR-0110).

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
        return [MinimumGMLevelPrerequisite(GMLevel.SENIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        if kwargs.get("target") is None:
            return self._find(kwargs)
        target = _resolve_gm_target(kwargs)
        if target is None:
            return ActionResult(success=False, message="No such target.")
        return self._invoke(target, kwargs)

    def _find(self, kwargs: dict[str, Any]) -> ActionResult:
        from world.checks.catalog_invocation import (  # noqa: PLC0415
            render_catalog_listing,
            search_catalog,
        )

        query = str(kwargs.get("query") or "")
        matches = search_catalog(query)
        return ActionResult(success=True, message=render_catalog_listing(query, matches))

    def _invoke(self, target: ObjectDB, kwargs: dict[str, Any]) -> ActionResult:
        from world.checks.catalog_invocation import (  # noqa: PLC0415
            resolve_band,
            resolve_check_type_ref,
        )
        from world.checks.services import perform_check  # noqa: PLC0415

        resolved = resolve_check_type_ref(
            kwargs.get("check_type_ref"), not_found_hint=_CATALOG_HINT
        )
        if isinstance(resolved, ActionResult):
            return resolved
        check_type = resolved

        band_result = resolve_band(kwargs.get("difficulty"))
        if isinstance(band_result, ActionResult):
            return band_result
        difficulty = band_result

        edge_reason = str(kwargs.get("edge_reason") or "").strip()
        setback_reason = str(kwargs.get("setback_reason") or "").strip()

        shift_result = resolve_band_shift(difficulty, edge_reason, setback_reason)
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

    A third ``award_type="favor_token"`` (#2428) mints a Golden Hare -- a
    deed-backed favor token -- from an authored ``Organization`` via
    ``world.currency.services.mint_favor_token``. Same JUNIOR trust bar as
    XP/development: this is pure GM fiat, not gated on the GM's own standing
    in the issuing org (the GM adjudication toolkit never checks that -- see
    the module-level RATIFIED invariant). ``description`` is required and
    becomes the token's ``provenance_note`` -- the deed the Hare is redeemable
    against, never left to a generic default.

    Two more kinds (#3055 slice 1c) write the acquisition-provenance ledger
    introduced for GM story rewards, so a stat/technique that came from GM
    fiat is distinguishable from one earned through organic advancement at
    the beta reset:

    - ``award_type="stat"`` raises an authored ``Trait`` (must be
      ``TraitType.STAT``) by exactly one display dot via
      ``world.progression.services.awards.award_stat_raise``, writing a
      ``CharacterTraitChange`` with ``source=TraitChangeSource.GM_GRANT`` and
      ``granting_tenure`` set to the GM's own current tenure (``None`` for a
      staff-piloted GM with no tenure -- the grant still succeeds).
    - ``award_type="technique"`` mints a ``Technique`` the target's owned
      gift doesn't yet have, via the shared
      ``world.magic.services.technique_acquisition.learn_technique`` seam,
      passing ``origin=AcquisitionOrigin.GM_GRANT`` and
      ``source=AccessChangeSource.GM_AWARD`` (the announce lead-in) with
      ``ap_cost=0`` for an immediate mint.

    Same JUNIOR trust bar as the other three kinds -- pure GM fiat, no check
    against the GM's own standing in either system.
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
        target = _resolve_gm_target(kwargs)
        if target is None:
            return ActionResult(success=False, message=MSG_TARGET_REQUIRED)

        award_type = str(kwargs.get("award_type") or "").strip().lower()
        description = str(kwargs.get("description") or "").strip()

        if award_type == _AWARD_TYPE_XP:
            return self._award_xp(actor, target, kwargs.get("amount"), description)
        if award_type == _AWARD_TYPE_DEVELOPMENT:
            return self._award_development(actor, target, kwargs, description)
        if award_type == _AWARD_TYPE_FAVOR_TOKEN:
            return self._award_favor_token(target, kwargs, description)
        if award_type == _AWARD_TYPE_STAT:
            return self._award_stat(actor, target, kwargs)
        if award_type == _AWARD_TYPE_TECHNIQUE:
            return self._award_technique(target, kwargs)
        return ActionResult(
            success=False,
            message="award_type must be one of: " + ", ".join(_AWARD_TYPES) + ".",
        )

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

    def _award_favor_token(
        self,
        target: ObjectDB,
        kwargs: dict[str, Any],
        description: str,
    ) -> ActionResult:
        from world.currency.services import mint_favor_token  # noqa: PLC0415
        from world.societies.models import Organization  # noqa: PLC0415

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=f"{target.key} has no character sheet.")

        org_ref = str(kwargs.get("org_ref") or "").strip()
        if not org_ref:
            return ActionResult(
                success=False, message="An organization is required to mint a Golden Hare."
            )

        try:
            org = resolve_model_by_pk_or_name(
                Organization,
                org_ref,
                not_found_msg=f"No organization named {org_ref!r}.",
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        if not description:
            return ActionResult(
                success=False,
                message="A description of the deed is required to mint a Golden Hare.",
            )

        # Truncate to FavorTokenDetails.provenance_note's max_length before create —
        # mirrors deliver_mission_money's `[:200]` convention (world.currency.services)
        # rather than letting an over-length description hit the DB-level varchar(200)
        # constraint as a raw DataError (#2428 whole-branch fix).
        mint_favor_token(org, sheet, provenance_note=description[:200])

        return ActionResult(
            success=True,
            message=f"Minted a Golden Hare from {org.name} for {target.key}.",
        )

    def _award_stat(
        self,
        actor: ObjectDB,
        target: ObjectDB,
        kwargs: dict[str, Any],
    ) -> ActionResult:
        from world.progression.services.awards import award_stat_raise  # noqa: PLC0415
        from world.traits.models import Trait, display_trait_value  # noqa: PLC0415

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=f"{target.key} has no character sheet.")

        trait_ref = str(kwargs.get("trait_ref") or "").strip()
        if not trait_ref:
            return ActionResult(success=False, message="A stat trait is required.")

        try:
            trait = resolve_model_by_pk_or_name(
                Trait,
                trait_ref,
                not_found_msg=f"No trait named {trait_ref!r}.",
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        granting_tenure = _resolve_granting_tenure(actor)

        try:
            change = award_stat_raise(sheet, trait, granting_tenure=granting_tenure)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        new_dots = display_trait_value(trait.trait_type, change.new_value)
        return ActionResult(
            success=True,
            message=f"Raised {trait.name} to {new_dots} for {target.key}.",
        )

    def _award_technique(
        self,
        target: ObjectDB,
        kwargs: dict[str, Any],
    ) -> ActionResult:
        from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
        from world.magic.constants import AcquisitionOrigin  # noqa: PLC0415
        from world.magic.exceptions import GiftNotOwned, TechniqueCapExceeded  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415
        from world.magic.services.technique_acquisition import learn_technique  # noqa: PLC0415

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=f"{target.key} has no character sheet.")

        technique_ref = str(kwargs.get("technique_ref") or "").strip()
        if not technique_ref:
            return ActionResult(success=False, message="A technique is required.")

        try:
            technique = resolve_model_by_pk_or_name(
                Technique,
                technique_ref,
                not_found_msg=f"No technique named {technique_ref!r}.",
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            learn_technique(
                sheet,
                technique,
                source=AccessChangeSource.GM_AWARD,
                ap_cost=0,
                origin=AcquisitionOrigin.GM_GRANT,
            )
        except GiftNotOwned:
            return ActionResult(
                success=False,
                message=f"{target.key} does not hold the {technique.gift.name} gift.",
            )
        except TechniqueCapExceeded as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message=f"Granted {technique.name} to {target.key}.",
        )


def _resolve_granting_tenure(actor: ObjectDB) -> Any:
    """Return the acting GM's current ``RosterTenure``, or ``None`` (#3055 slice 1c).

    A staff-piloted GM (no roster tenure at all) still gets to make the grant --
    ``granting_tenure`` is nullable exactly for that case. None-safe at every hop:
    ``character_sheet`` may be missing (non-Character actor), ``roster_entry_or_none``
    may be ``None`` (no roster entry), and ``current_tenure`` may be ``None`` (the
    entry exists but has no live tenure).
    """
    from typeclasses.characters import Character  # noqa: PLC0415

    if not isinstance(actor, Character):
        return None
    sheet = actor.character_sheet
    if sheet is None:
        return None
    entry = sheet.roster_entry_or_none
    if entry is None:
        return None
    return entry.current_tenure


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

    target = _resolve_gm_target(kwargs)
    if target is None:
        return ActionResult(success=False, message=MSG_TARGET_REQUIRED)

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


def _narrate_gm_condition(
    actor: ObjectDB, target: ObjectDB, template: ConditionTemplate, note: str
) -> None:
    """Broadcast the GM's note as a Narrator OUTCOME line (#3554).

    Only called when a note was given: a note-less apply stays silent and the GM
    narrates with the composer if they want to. The target is named by the face they
    are presenting (#981), never ``target.key``, when they have one. A condition
    others cannot see routes the line to the target alone. The direct text send is
    the telnet companion; ``record_interaction`` reaches only web clients. A
    sheetless target (a prop, an unsheeted NPC) is named by its key; a hidden
    condition on one records nothing, since there is no bearer to tell.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        get_active_scene,
        record_interaction,
    )
    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = target.character_sheet
    target_persona = active_persona_for_sheet(sheet) if sheet is not None else None
    if target_persona is None and not template.is_visible_to_others:
        return  # a hidden condition on a sheetless object has no bearer to tell

    label = target_persona.name if target_persona is not None else target.key
    narration = f"{label} is now {template.name}. {note}"
    record_interaction(
        character=actor,
        content=narration,
        mode=InteractionMode.OUTCOME,
        scene=get_active_scene(actor.location),
        persona=get_or_create_narrator_persona(),
        receivers=None if template.is_visible_to_others else [target_persona],
    )
    room = actor.location if template.is_visible_to_others else None
    if room is not None:
        room.msg_contents(narration)
    else:
        target.msg(narration)


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
    ``source_description`` and, when given, broadcast as a Narrator OUTCOME line,
    #3554) -- it never becomes a mechanical effect. Gated on
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

        if note:
            _narrate_gm_condition(actor, target, template, note)

        return ActionResult(success=True, message=f"{target.key} is now {template.name}.")


def _resolve_active_condition_instance(kwargs: dict[str, Any]) -> tuple[Any, Any] | ActionResult:
    """Return ``(target, instance)`` for ``gm_remove_condition``/``gm_list_conditions``.

    Stricter than ``_resolve_condition_target``'s bare catalog lookup (which
    ``GMApplyConditionAction`` uses -- applying doesn't presuppose an existing
    instance): this resolves against the target's own ACTIVE ``ConditionInstance``s
    via ``get_active_conditions`` and refuses when the target doesn't currently
    carry the named condition, rather than silently no-opping like
    ``remove_condition_by_name`` (the flow-layer ``CALL_SERVICE_FUNCTION`` target).
    The kwarg is named ``condition`` (not ``condition_ref``, unlike its sibling
    catalog-name kwargs elsewhere in this module) precisely to signal this
    narrower active-instance-only resolution.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    target = _resolve_gm_target(kwargs)
    if target is None:
        return ActionResult(success=False, message=MSG_TARGET_REQUIRED)

    condition_ref = str(kwargs.get("condition") or "").strip()
    if not condition_ref:
        return ActionResult(success=False, message="A condition name is required.")

    try:
        template = ConditionTemplate.get_by_name(condition_ref)
    except ConditionTemplate.DoesNotExist:
        return ActionResult(success=False, message=f"No condition named {condition_ref!r}.")

    instance = get_active_conditions(target, condition=template).first()
    if instance is None:
        return ActionResult(
            success=False,
            message=f"{target.key} does not have {template.name} active.",
        )

    return target, instance


@dataclass
class GMRemoveConditionAction(Action):
    """JUNIOR-tier GM action: remove an active ``ConditionTemplate`` by fiat (#3431).

    The referee off-switch ``GMApplyConditionAction`` never got:
    ``remove_condition``/``clear_all_conditions`` (``world/conditions/services.py``)
    were previously called only by expiry, treatment, and internal flows. Catalog-
    bounded to the target's own active instances -- see
    ``_resolve_active_condition_instance``. ``reason`` is required and echoed in
    the result message; unlike ``GMApplyConditionAction``'s ``note`` (persisted as
    ``source_description``), ``remove_condition`` has no note field of its own to
    carry it into, so this is audit-visible only in the returned message, not a
    stored field (matches the apply action's "echoed in the result" shape, Decision
    2). Gated on ``IsSceneGMPrerequisite`` + ``MinimumGMLevelPrerequisite(GMLevel.
    JUNIOR)`` -- mirrors ``GMApplyConditionAction`` exactly (same trust bar to
    switch a fiat condition off as to switch one on).
    """

    key: str = "gm_remove_condition"
    name: str = "Remove Condition"
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
        from world.conditions.services import remove_condition  # noqa: PLC0415

        reason = str(kwargs.get("reason") or "").strip()
        if not reason:
            return ActionResult(
                success=False, message="A reason is required to remove a condition."
            )

        resolved = _resolve_active_condition_instance(kwargs)
        if isinstance(resolved, ActionResult):
            return resolved
        target, instance = resolved
        template = instance.condition

        removed = remove_condition(target, template)
        if not removed:
            # Race: the instance resolved above vanished before this call (e.g. it
            # expired mid-request). Fail loud rather than reporting a false success.
            return ActionResult(
                success=False,
                message=f"{target.key} does not have {template.name} active.",
            )
        return ActionResult(
            success=True,
            message=f"{template.name} removed from {target.key} ({reason}).",
        )


@dataclass
class GMListConditionsAction(Action):
    """JUNIOR-tier GM action: list a target's active conditions (#3431).

    Feeds ``GMRemoveConditionAction``'s web picker -- no existing read path serves
    this: ``CharacterConditionsViewSet`` is self-only, and its ``observed`` action
    filters to ``is_visible_to_others=True``, which would hide a GM's own
    fiat-applied hidden condition from the GM who applied it. Mirrors
    ``ListRoomTrapsAction``'s shape (``actions/definitions/traps.py``): result data
    is the payload, the rendered message a human-readable fallback. Same gates as
    ``GMRemoveConditionAction`` -- listing is no more sensitive than removing.
    """

    key: str = "gm_list_conditions"
    name: str = "List Conditions"
    icon: str = "list"
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
        from world.conditions.services import get_active_conditions  # noqa: PLC0415

        target = _resolve_gm_target(kwargs)
        if target is None:
            return ActionResult(success=False, message=MSG_TARGET_REQUIRED)

        rows = [
            {
                "id": instance.pk,
                "name": instance.condition.name,
                "severity": instance.severity,
                "rounds_remaining": instance.rounds_remaining,
                "expires_at": instance.expires_at.isoformat() if instance.expires_at else None,
            }
            for instance in get_active_conditions(target)
        ]
        if not rows:
            return ActionResult(
                success=True,
                message=f"{target.key} has no active conditions.",
                data={"conditions": []},
            )
        lines = [f"[{row['id']}] {row['name']} (severity {row['severity']})" for row in rows]
        return ActionResult(success=True, message="\n".join(lines), data={"conditions": rows})


@dataclass
class SummonPlayerAction(Action):
    """Consent-prompted GM summon: invite a player to the GM's scene room (#3071).

    Ruled (2026-08-08, #3071): a GM may move a party mid-session, but only WITH
    consent, and only into a scene the GM actually runs — this action does not
    move anyone by itself. It creates (or replaces) a ``GMSummonOffer`` naming
    the invoking GM and their current room; the *target* must separately accept
    via ``AcceptGMSummonAction``/``DeclineGMSummonAction``
    (``actions/definitions/gm_summon_offers.py``) before anyone moves.

    Gated the same way ``GMAwardAction``/``GMApplyConditionAction`` are —
    ``IsSceneGMPrerequisite`` (the actor must be running an active scene at their
    own location; the "for tracking" shape the ruling asked for — a summon is
    always anchored to a live scene, never a bare room) + JUNIOR GM trust, staff
    bypass preserved.

    Leak analysis (per the approved spec): the consent prompt names the GM
    (``actor.key``) and the scene title only — never room contents/other
    occupants — so a decline reveals nothing further.
    """

    key: str = "summon_player"
    name: str = "Summon Player"
    icon: str = "compass"
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
        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.gm.services import offer_gm_summon  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        target = _resolve_gm_target(kwargs)
        if target is None:
            return ActionResult(success=False, message=MSG_TARGET_REQUIRED)
        target_sheet = target.character_sheet
        if target_sheet is None:
            return ActionResult(success=False, message=f"{target.key} has no character sheet.")
        if target_sheet.pk == actor.pk:
            return ActionResult(success=False, message="You cannot summon yourself.")

        if actor.location is None:
            return ActionResult(success=False, message="You are not in a room.")

        gm_profile = _resolve_gm_profile(actor)
        room = get_room_profile(actor.location)
        scene = get_active_scene(actor.location)

        offer_gm_summon(gm_profile, target_sheet, room=room, scene=scene, gm_display_name=actor.key)

        return ActionResult(
            success=True,
            message=f"You invite {target.key} to your scene. They must accept to be moved.",
        )
