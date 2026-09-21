"""Required-content sentinel: registry vocabulary and batching collector (#3444).

Some code paths hard-depend on a specific authored database row existing (a named
`ConditionTemplate`, a tuning config singleton, ...) rather than on the shape of a
table. Nothing enforces that dependency at the database layer, so when the row is
missing the failure surfaces far from its cause - a `DoesNotExist` deep in a check
resolver, or a silent no-op. This module is the registry of those dependencies and
the collector that probes each one, so an admin dashboard (a later task) can report
the gap directly instead of a staff member reconstructing it from a stack trace.

Add a row to `_declarations()` when you add a code path that hard-depends on a
specific authored row. Each row names its consumer (`file:line function()`) and
the consequence a player or staff member experiences when the row is absent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from django.apps import apps


class DependencyTier(StrEnum):
    """How severely a missing row degrades the game.

    `REQUIRED` rows are load-bearing for a code path a player or staff member
    can hit today; `TUNING` rows are config the game runs without, just with
    worse numbers (a fallback constant, an unconfigured knob).
    """

    REQUIRED = "required"
    TUNING = "tuning"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of resolving one `ContentProbe`."""

    present: bool
    missing: tuple[str, ...] = ()
    detail: str = ""


class ContentProbe:
    """Base class for a single row-presence check.

    A subclass declares what it checks (which rows, which model); `resolve()`
    performs the check and reports the result. `model_label()` is the seam
    that names which `arxii` model a probe checks, so the collector can tell
    which probes share a model without an `isinstance` check. Today the
    collector is `model_label()`'s only reader (no panel calls it - the panel
    renders `dependency.label` instead), and only under
    `participates_in_name_batch()`, the narrower seam that actually drives
    batching: only a `NamedRowsProbe` shares a single `values_list` query
    across declarations naming the same model - `AnyRowProbe` also overrides
    `model_label()` (it genuinely has a model, resolved via `apps.get_model`
    in its own `resolve()`) but must keep resolving its own `.exists()` query
    per declaration, so it must not be folded into that batch.
    """

    def model_label(self) -> str | None:
        """The `arxii` app model label this probe checks, or `None` if it isn't
        one the collector can batch (e.g. a `CustomProbe`)."""
        return None

    def participates_in_name_batch(self) -> bool:
        """Whether the collector should pool this probe's `model_label()` into
        the shared known-names query rather than let the probe resolve itself."""
        return False

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        """Resolve this probe against `known_names` (pre-fetched, exact-case row
        names for this probe's model - a `case_insensitive` probe casefolds both
        sides itself inside its own `resolve()`), or `None` when the probe
        fetches its own data (an `AnyRowProbe`'s `.exists()`, a
        `FilteredRowProbe`'s filtered `.exists()`, a `CustomProbe`'s callable)."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NamedRowsProbe(ContentProbe):
    """Checks that every one of `names` exists as a row on `label`.

    Matching is case-sensitive by default, matching the dominant consumer
    pattern in this registry: `CheckType`, `ChallengeTemplate`, `Property`,
    `RoomFeatureKind`, `Ritual`, `KudosSourceCategory`, `CapabilityType`, and
    `ModifierTarget` are all resolved by plain `.objects.get(name=...)`, which
    is case-sensitive - a probe that matched case-insensitively there could
    report present for a row the game's own lookup still can't find (#3444
    final review item 3).

    Set `case_insensitive=True` only for a declaration whose consumer resolves
    through a case-insensitive lookup - in this registry, that is exactly the
    `ConditionTemplate` declarations, whose consumers go through
    `ConditionTemplate.get_by_name` (`world/conditions/models.py:503-511`),
    which casefolds. One exception even among those: `berserk-condition`'s
    consumer, `world/species/moon_sensitivity.py:180`, uses `filter(name=...)`
    case-sensitively - `case_insensitive=True` is kept for it anyway since
    `get_by_name` is the dominant path for `ConditionTemplate` lookups, and
    this note exists so the next reader knows that exception was seen, not
    missed.
    """

    label: str
    names: tuple[str, ...]
    case_insensitive: bool = False

    def model_label(self) -> str | None:
        return self.label

    def participates_in_name_batch(self) -> bool:
        return True

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        known = known_names or frozenset()
        if self.case_insensitive:
            folded = frozenset(name.casefold() for name in known)
            missing = tuple(name for name in self.names if name.casefold() not in folded)
        else:
            missing = tuple(name for name in self.names if name not in known)
        if missing:
            detail = f"Missing {self.label} row(s): {', '.join(missing)}."
        else:
            detail = ""
        return ProbeResult(present=not missing, missing=missing, detail=detail)


@dataclass(frozen=True, slots=True)
class AnyRowProbe(ContentProbe):
    """Checks that `label` has at least one row - a singleton/config table that
    must be seeded at all, with no specific name to check."""

    label: str

    def model_label(self) -> str | None:
        return self.label

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        del known_names  # This probe fetches its own existence check.
        model = apps.get_model("arxii", self.label)
        exists = model.objects.exists()
        detail = "" if exists else f"No {self.label} rows exist."
        return ProbeResult(present=exists, detail=detail)


@dataclass(frozen=True, slots=True)
class CustomProbe(ContentProbe):
    """Delegates to an arbitrary callable for checks a name/existence probe
    can't express (a composite condition, a cross-model invariant)."""

    fn: Callable[[], ProbeResult]

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        del known_names  # This probe delegates entirely to `fn`.
        return self.fn()


@dataclass(frozen=True, slots=True)
class FilteredRowProbe(ContentProbe):
    """Checks that a row matching an exact compound filter exists on `label`.

    The generalized shape behind what used to be five near-identical
    `CustomProbe` callables (#3444 final review item 9): each checked one
    row's presence under a compound filter a name-only `NamedRowsProbe`
    can't express - a name filed under the wrong parent category, the wrong
    trait_type, the wrong key column. `filters` is a tuple of `(lookup,
    value)` pairs rather than a `dict` so the dataclass stays a plain,
    order-stable value object; it is passed straight through to
    `Model.objects.filter(**dict(filters))`, so any Django field lookup
    (`key__iexact`, `category__name`, ...) works.

    Model resolution goes through `apps.get_model("arxii", label)`, the same
    seam `AnyRowProbe` uses - this probe needs no `world.*` import at all,
    not even a function-level one, since it never touches a model attribute
    by name at declaration time.
    """

    label: str
    filters: tuple[tuple[str, object], ...]
    absent_detail: str

    def model_label(self) -> str | None:
        return self.label

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        del known_names  # This probe fetches its own existence check.
        model = apps.get_model("arxii", self.label)
        exists = model.objects.filter(**dict(self.filters)).exists()
        detail = "" if exists else self.absent_detail
        return ProbeResult(present=exists, detail=detail)


@dataclass(frozen=True, slots=True)
class ContentDependency:
    """One registry row: a code path's hard dependency on authored content.

    `admin_model` names the model whose admin page authors this dependency's rows,
    for a probe that cannot say so itself (a `CustomProbe`). Left `None`, the
    probe's own `model_label()` is used.
    """

    key: str
    label: str
    tier: DependencyTier
    consumer: str
    consequence: str
    probe: ContentProbe
    admin_model: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyRow:
    """A `ContentDependency` paired with its resolved `ProbeResult`."""

    dependency: ContentDependency
    result: ProbeResult

    @property
    def admin_url(self) -> str | None:
        """Admin changelist where staff author this dependency's rows (#3831), or None."""
        from web.admin.authoring.links import admin_changelist_url  # noqa: PLC0415

        model_label = self.dependency.admin_model or self.dependency.probe.model_label()
        return admin_changelist_url(model_label) if model_label else None


@dataclass(frozen=True, slots=True)
class RequiredContentSnapshot:
    """The collector's output: every dependency, sorted by tier and presence."""

    missing_required: list[DependencyRow]
    present_required: list[DependencyRow]
    missing_tuning: list[DependencyRow]
    present_tuning: list[DependencyRow]


def build_registry(dependencies: Iterable[ContentDependency]) -> tuple[ContentDependency, ...]:
    """Freeze `dependencies` into a tuple, rejecting a duplicate `key`.

    A duplicate key would silently merge two distinct dependencies under one
    report row, so this raises rather than dedupe or last-write-wins.
    """
    registry: list[ContentDependency] = []
    seen_keys: set[str] = set()
    for dependency in dependencies:
        if dependency.key in seen_keys:
            message = f"Duplicate content dependency key: {dependency.key!r}"
            raise ValueError(message)
        seen_keys.add(dependency.key)
        registry.append(dependency)
    return tuple(registry)


def _probe_typeclassed_accounts() -> ProbeResult:
    """No account row skipped Evennia's first-save setup (#3596, #3812).

    Two symptoms, both disqualifying: ``db_typeclass_path`` names the base
    ``AccountDB`` model (the row loads without the ``Account`` typeclass and
    every persona-aware view 500s - Sentry ARX2-8), or ``db_cmdset_storage``
    is empty (the row logs in and can run no command, not even ``help``). The
    second is what the old hand repair left behind: repointing the path with
    ``.update()`` runs no hook, so this probe used to pass a row that was still
    unusable. ``ArxAccountAdapter.new_user`` stops signup making such rows and
    the ``createsuperuser`` override heals the one it makes; the server heals
    every remaining row on start (``at_server_start``), so a hit here after a
    deploy is a row created bare since.
    """
    from evennia_extensions.account_setup import bare_account_rows  # noqa: PLC0415

    rows = tuple(bare_account_rows().values_list("username", flat=True))
    detail = (
        f"Account(s) that skipped first-save setup (typeclass path on the base "
        f"AccountDB model, or empty cmdset storage - the row can log in and run no "
        f"command): {', '.join(rows)}. The server heals these on start; to fix one "
        "now, run heal_account_setup(AccountDB.objects.get(username=...)) from "
        "evennia_extensions.account_setup in `arx manage shell`."
        if rows
        else ""
    )
    return ProbeResult(present=not rows, missing=rows, detail=detail)


def _probe_mfa_secrets_key() -> ProbeResult:
    """``MFA_SECRETS_KEY`` parses and still decrypts the oldest stored 2FA secret.

    Consumer: every 2FA sign-in and every recovery-code read
    (``ArxMFAAdapter.decrypt``, ADR-0267). A key rotated without re-encrypting,
    or a wrong key deployed, locks every enrolled player out at once; nothing
    else on the site notices until the first player fails to log in.
    """
    from allauth.mfa.models import Authenticator  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415

    from evennia_extensions.mfa_adapter import ArxMFAAdapter, fernet_from_setting  # noqa: PLC0415

    try:
        fernet_from_setting(settings.MFA_SECRETS_KEY)
    except ValueError as exc:
        return ProbeResult(present=False, missing=("MFA_SECRETS_KEY",), detail=str(exc))
    oldest = (
        Authenticator.objects.filter(type=Authenticator.Type.TOTP).order_by("created_at").first()
    )
    if oldest is None:
        return ProbeResult(present=True)
    try:
        ArxMFAAdapter().decrypt(oldest.data["secret"])
    except ValueError as exc:
        return ProbeResult(present=False, missing=("MFA_SECRETS_KEY",), detail=str(exc))
    return ProbeResult(present=True)


def _probe_path_gift_starter_pools() -> ProbeResult:
    """Every (path, gift) a tradition makes pickable has path starter techniques.

    Consumer: `world/magic/services/cg_catalog.py:28` `get_technique_options()`.
    A gift becomes pickable at character creation if EITHER the path's
    `PathGiftGrant.starter_techniques` or the tradition's
    `TraditionGiftGrant.special_techniques` is non-empty. Ruled on #3682: there
    will never be a gift a path offers nothing for, so an empty path pool is
    missing authored content rather than a case to branch on. This reports it
    instead of the code hiding it.

    Deliberately NOT reported: a `TraditionGiftGrant` carrying no specials. That
    is a legitimate authored state meaning "this tradition teaches this gift and
    adds no unique extras of its own", the gift still reaches the player through
    the path pool, and 39 of 69 authored rows are in it - folding them in would
    bury the real gaps.
    """
    from world.classes.models import Path  # noqa: PLC0415
    from world.magic.models import PathGiftGrant, TraditionGiftGrant  # noqa: PLC0415

    # Gifts a tradition can put in front of a player, i.e. those whose grant
    # actually carries specials. A tradition grant with an empty pool adds no
    # availability of its own and cannot create this gap.
    offered_gifts = set(
        TraditionGiftGrant.objects.filter(special_techniques__isnull=False)
        .values_list("gift_id", "gift__name")
        .distinct()
    )
    if not offered_gifts:
        return ProbeResult(present=True)

    stocked = set(
        PathGiftGrant.objects.filter(starter_techniques__isnull=False)
        .values_list("path_id", "gift_id")
        .distinct()
    )
    paths = list(Path.objects.values_list("id", "name"))

    missing = tuple(
        f"{path_name} / {gift_name}"
        for path_id, path_name in paths
        for gift_id, gift_name in sorted(offered_gifts, key=lambda row: row[1])
        if (path_id, gift_id) not in stocked
    )
    if not missing:
        return ProbeResult(present=True)
    detail = (
        f"{len(missing)} (path, gift) pair(s) are pickable through a tradition "
        "with no path starter techniques: the gift appears in character creation "
        "and delivers only that tradition's extras."
    )
    return ProbeResult(present=False, missing=missing, detail=detail)


def _probe_audere_majora_thresholds() -> ProbeResult:
    """`AudereMajoraThreshold` rows exist for every tier-crossing boundary level.

    Consumer: `world/magic/audere_majora.py:679` (the tier-crossing offer). A
    missing boundary level means a character who reaches that level never gets
    the Audere Majora crossing offer at all - the corruption path silently stops
    advancing for them.
    """
    from world.magic.audere_majora import AudereMajoraThreshold  # noqa: PLC0415

    expected_levels = (5, 10, 15, 20)
    existing_levels = set(
        AudereMajoraThreshold.objects.filter(boundary_level__in=expected_levels).values_list(
            "boundary_level", flat=True
        )
    )
    missing = tuple(str(level) for level in expected_levels if level not in existing_levels)
    if missing:
        detail = (
            f"Missing AudereMajoraThreshold row(s) for boundary level(s): {', '.join(missing)}."
        )
    else:
        detail = ""
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_soulfray_stage_pools() -> ProbeResult:
    """Every `ConditionStage` of the Soulfray template carries a `consequence_pool`.

    Consumer: the Soulfray corruption-severity progression
    (`world/magic/audere.py`, `world/conditions/services.py`). A stage without a
    pool means a character who progresses to that stage accumulates severity but
    the game has nothing to draw a consequence from - the corruption effect at
    that stage silently does nothing.

    Note: the FK from `ConditionStage` to `ConditionTemplate` is named `condition`
    (not `template`), so the filter below reads `condition__name__iexact`.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    stages = ConditionStage.objects.filter(condition__name__iexact=SOULFRAY_CONDITION_NAME)
    if not stages.exists():
        detail = f"No ConditionStage rows exist for the {SOULFRAY_CONDITION_NAME} template."
        return ProbeResult(present=False, detail=detail)
    unpooled = tuple(stages.filter(consequence_pool__isnull=True).values_list("name", flat=True))
    if unpooled:
        detail = f"Soulfray stage(s) with no consequence_pool: {', '.join(unpooled)}."
    else:
        detail = ""
    return ProbeResult(present=not unpooled, missing=unpooled, detail=detail)


def _probe_surrounded_condition_bundle() -> ProbeResult:
    """All three rows `_apply_surrounded_isolation` needs, not just the template.

    Consumer: `world/battles/resolution.py:1160-1190` (isolation entry). The guard
    there is `if pool is None or template is None or entry_stage is None: return
    False`, so a name-only probe on the `Surrounded` `ConditionTemplate` is a false
    green when either of the other two rows is absent - the template alone is not
    enough for isolation tagging to fire. This checks all three:

    - the `Surrounded` `ConditionTemplate`, resolved via `get_by_name` (case-
      insensitive), matching how the call site resolves it;
    - a `ConsequencePool` whose `name` is exactly `POOL_SURROUNDED_ENTRY`
      (`world/vitals/constants.py`) - the call site compares `p.name ==
      POOL_SURROUNDED_ENTRY` in Python, case-sensitive, so this probe is too;
    - a `ConditionStage` with `stage_order=1` whose `condition_id` is that
      template's pk.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionStage, ConditionTemplate  # noqa: PLC0415
    from world.vitals.constants import POOL_SURROUNDED_ENTRY  # noqa: PLC0415

    missing: list[str] = []

    try:
        template = ConditionTemplate.get_by_name(SURROUNDED_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        template = None
        missing.append(f"ConditionTemplate {SURROUNDED_CONDITION_NAME!r}")

    if not ConsequencePool.objects.filter(name=POOL_SURROUNDED_ENTRY).exists():
        missing.append(f"ConsequencePool {POOL_SURROUNDED_ENTRY!r}")

    if template is not None:
        has_entry_stage = ConditionStage.objects.filter(
            condition_id=template.pk, stage_order=1
        ).exists()
        if not has_entry_stage:
            missing.append(f"ConditionStage stage_order=1 for {SURROUNDED_CONDITION_NAME!r}")
    else:
        missing.append(f"ConditionStage stage_order=1 for {SURROUNDED_CONDITION_NAME!r}")

    if missing:
        detail = f"Missing row(s) for Surrounded isolation tagging: {', '.join(missing)}."
    else:
        detail = ""
    return ProbeResult(present=not missing, missing=tuple(missing), detail=detail)


def _probe_escalation_curves() -> ProbeResult:
    """Every `StakesLevel` has a `StakesEscalationModifier` row with a `default_curve`.

    Consumer: `world/combat/escalation.py` (`assign_default_escalation_curve`,
    `_stakes_intensity_step_bonus`). Both already fall back gracefully (no curve
    assigned, a zero intensity bonus) for a stakes level with no row or no
    `default_curve` - a high-stakes fight just needs a GM to set its curve by
    hand instead of escalating on its own. REQUIRED, not TUNING, though:
    `assign_default_escalation_curve` is a code path a player hits on every
    encounter creation, and a single uncovered stakes level (e.g. WORLD) is a
    real per-level gap, not a config the whole game runs fine without - partial
    coverage must report missing, not present, so this checks ALL levels, not
    "at least one."
    """
    from world.combat.constants import StakesLevel  # noqa: PLC0415
    from world.combat.models import StakesEscalationModifier  # noqa: PLC0415

    total_levels = len(StakesLevel.values)
    covered_levels = set(
        StakesEscalationModifier.objects.filter(default_curve__isnull=False).values_list(
            "stakes_level", flat=True
        )
    )
    missing = tuple(level for level in StakesLevel.values if level not in covered_levels)
    with_curve = len(covered_levels)
    detail = f"{with_curve} of {total_levels} stakes levels have a default escalation curve."
    if missing:
        detail += f" Missing: {', '.join(missing)}."
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_capability_bridges() -> ProbeResult:
    """Every evaluated capability lands in the Capabilities panel's zero bucket for a reason.

    Reuses `web.admin.tuning.capability_power_analytics`'s existing 24h-cached
    panel builder rather than re-running the DE evaluator - see that module's
    docstring for the caching contract this must not duplicate. Because it reads
    that cache, a bridge authored in the last 24h can still show red here until
    the cache refreshes - a false RED, not a false green, so the fix is this
    wording, not a second cache or a fresh evaluator run.

    `panel.zero_bucket` is not "no authored bridge" alone: a capability lands
    there when it either has no authored bridge at all OR is bridged but prices
    to zero DE (`_is_zero_value(report) or NO_AUTHORED_BRIDGE_FLAG in
    report.flags` in that module). The count below is honest about that - it
    says "prices to zero," which covers both causes, rather than claiming every
    one of them is missing a bridge.
    """
    from web.admin.tuning.capability_power_analytics import (  # noqa: PLC0415
        CapabilityPowerAnalyticsParams,
        build_capability_power_panel,
    )

    panel = build_capability_power_panel(CapabilityPowerAnalyticsParams())
    unbridged = len(panel.zero_bucket)
    detail = (
        f"{unbridged} capabilities price to zero combat-power (no authored bridge, or a "
        "bridge that evaluates to zero DE) - see the Capabilities tuning panel."
    )
    return ProbeResult(present=unbridged == 0, detail=detail)


def _probe_encounter_outcome_mappings() -> ProbeResult:
    """`EncounterOutcomeMapping` rows exist for every `EncounterOutcome` x `RiskLevel` pair.

    Consumer: `world/combat/beat_wiring.py classify_battle_outcome()`. VICTORY/DEFEAT
    grade a story beat; FLED/ABANDONED grade a scenario ENCOUNTER option's route
    instead (#3565) - either way a missing pair means the outcome never resolves
    (a fight linked to a story beat, or a scenario run's ENCOUNTER pick); the error
    log names the pair (#3559, #3565).
    """
    from world.combat.constants import EncounterOutcome, RiskLevel  # noqa: PLC0415
    from world.combat.models import EncounterOutcomeMapping  # noqa: PLC0415

    expected = {(outcome, risk) for outcome in EncounterOutcome.values for risk in RiskLevel.values}
    existing = set(EncounterOutcomeMapping.objects.values_list("outcome", "risk_level"))
    missing = tuple(f"{o}/{r}" for (o, r) in sorted(expected - existing))
    detail = f"Missing EncounterOutcomeMapping row(s): {', '.join(missing)}." if missing else ""
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_battle_outcome_mappings() -> ProbeResult:
    """`BattleOutcomeMapping` rows exist for every `BattleOutcome` except UNRESOLVED.

    Consumer: `world/battles/beat_wiring.py classify_battle_conclusion_outcome()`. A
    missing outcome means a battle linked to a story beat concludes and the beat
    never resolves; the error log names the outcome (#3559). UNRESOLVED is not a
    graded conclusion (`resolve_battle_beats` is only reached once a battle has
    concluded to one of the other four), so it is excluded from the expected set.
    """
    from world.battles.constants import BattleOutcome  # noqa: PLC0415
    from world.battles.models import BattleOutcomeMapping  # noqa: PLC0415

    expected = {outcome for outcome in BattleOutcome.values if outcome != BattleOutcome.UNRESOLVED}
    existing = set(BattleOutcomeMapping.objects.values_list("outcome", flat=True))
    missing = tuple(sorted(expected - existing))
    detail = f"Missing BattleOutcomeMapping row(s): {', '.join(missing)}." if missing else ""
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_companion_defeat_pool() -> ProbeResult:
    """The pool AND its entries - an empty pool draws nothing.

    Consumer: `world/companions/services.py:335 resolve_companion_defeat()`, whose
    guard is `if not consequences: return False`, so a bare pool row with no
    ConsequencePoolEntry is a silent no-op, not a working pool.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.companions.factories_combat import (  # noqa: PLC0415
        COMPANION_DEFEAT_POOL_NAME,
    )

    pool = ConsequencePool.objects.filter(name=COMPANION_DEFEAT_POOL_NAME).first()
    if pool is None:
        return ProbeResult(
            present=False,
            missing=(f"ConsequencePool {COMPANION_DEFEAT_POOL_NAME!r}",),
            detail=f"No {COMPANION_DEFEAT_POOL_NAME!r} ConsequencePool row.",
        )
    if not pool.entries.filter(is_excluded=False).exists():
        return ProbeResult(
            present=False,
            missing=(f"ConsequencePoolEntry rows for {COMPANION_DEFEAT_POOL_NAME!r}",),
            detail="The pool exists but has no entries, so every draw is a no-op.",
        )
    return ProbeResult(present=True)


def _beginnings_without_upbringing() -> ProbeResult:
    """Every active `Beginnings` row has at least one active `OriginTemplate`.

    Consumer: the Lineage stage / `get_lineage_errors` (#3617). A beginning with
    no Upbringing offers a player no options at all in Lineage and they cannot
    finish CG for that beginning.
    """
    from world.character_creation.models import Beginnings  # noqa: PLC0415

    missing = tuple(
        Beginnings.objects.filter(is_active=True)
        .exclude(origin_templates__is_active=True)
        .order_by("name")
        .values_list("name", flat=True)
        .distinct()
    )
    detail = "" if not missing else f"{len(missing)} active beginning(s) have no active Upbringing."
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_tradition_state_lines() -> ProbeResult:
    """Every `TraditionState` value has a `TraditionStateLine` row with a non-blank `entry_line`.

    Consumer: `web/admin/tradition_slate/live.py` (`state_line_display`,
    `preview_line`) and `world/character_creation/serializers.py`
    (`TraditionSerializer.get_state_line`). The three rows are shared by every
    Beginning (#3675), so a missing or blank one means the tradition step prints
    nothing at that state for every Beginning's slate line at once, not just one -
    this is why the tradition slate page's own GET no longer writes placeholder
    rows just to have three to show (#3675 demo-fidelity ruling): this sentinel is
    the dashboard's job, not a silent database write.
    """
    from world.character_creation.constants import TraditionState  # noqa: PLC0415
    from world.character_creation.models import TraditionStateLine  # noqa: PLC0415

    rows = {
        line.state: line
        for line in TraditionStateLine.objects.filter(state__in=TraditionState.values)
    }
    missing = tuple(
        state for state in TraditionState.values if state not in rows or not rows[state].entry_line
    )
    detail = (
        f"Missing or blank TraditionStateLine row(s) for state(s): {', '.join(missing)}."
        if missing
        else ""
    )
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_schooling_lines() -> ProbeResult:
    """Every rank 0-2 has a `SchoolingLine` row with a non-blank `name`.

    Consumer: `web/admin/tradition_slate/live.py` (`schooling_line_display`) and
    `world/character_creation/serializers.py` (`schooling_rows`). Like the state
    lines, these three rows are shared by every Beginning - a missing or blank one
    means the living-masters schooling set is incomplete everywhere at once.
    """
    from world.character_creation.models import SchoolingLine  # noqa: PLC0415

    expected_ranks = (0, 1, 2)
    rows = {line.rank: line for line in SchoolingLine.objects.filter(rank__in=expected_ranks)}
    missing = tuple(str(rank) for rank in expected_ranks if rank not in rows or not rows[rank].name)
    detail = (
        f"Missing or blank SchoolingLine row(s) for rank(s): {', '.join(missing)}."
        if missing
        else ""
    )
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _probe_risk_calibrations() -> ProbeResult:
    """Every `RenownRisk` above `NONE` has a `RiskCalibration` row.

    Consumer: `world/stories/services/stakes.py:398` (`validate_stakes_readiness`).
    `risk` is a unique field on `RiskCalibration`, so "at least one row" is not
    enough - a story beat risked at any uncovered level can never be marked
    ready, regardless of how many other levels are covered.
    """
    from world.societies.constants import RenownRisk  # noqa: PLC0415
    from world.stories.models import RiskCalibration  # noqa: PLC0415

    expected_levels = tuple(level for level in RenownRisk.values if level != RenownRisk.NONE)
    covered_levels = set(
        RiskCalibration.objects.filter(risk__in=expected_levels).values_list("risk", flat=True)
    )
    missing = tuple(level for level in expected_levels if level not in covered_levels)
    detail = (
        f"Missing RiskCalibration row(s) for risk level(s): {', '.join(missing)}."
        if missing
        else ""
    )
    return ProbeResult(present=not missing, missing=missing, detail=detail)


def _declarations() -> tuple[ContentDependency, ...]:
    """Every hard-coded row dependency the sentinel tracks.

    Every game-code name constant (`world.*`, `evennia_extensions.*`) is imported
    here, at function level, rather than at module import time - so this admin
    module never imports game code just by being imported itself, and a rename
    of one of these constants shows up as an import error the next time this
    function runs rather than as a silently stale string literal.
    """
    from evennia_extensions.seeds import DEFAULT_ROOM_SIZE_NAME  # noqa: PLC0415
    from world.areas.positioning.constants import (  # noqa: PLC0415
        AERIAL_PROPERTY_NAME,
        CATCH_THE_FALLER_NAME,
        PLUMMETING_CONDITION_NAME,
    )
    from world.clues.constants import SEARCH_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.combat.constants import (  # noqa: PLC0415
        CONCENTRATION_CHECK_TYPE_NAME,
        PENETRATION_CHECK_TYPE_NAME,
    )
    from world.combat.defend_content import SHIELDED_CONDITION_NAME  # noqa: PLC0415
    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.companions.content import BIND_ATTEMPT_CHECK_NAME  # noqa: PLC0415
    from world.companions.defeat_content import SAVAGED_CONDITION_NAME  # noqa: PLC0415
    from world.companions.mount_content import (  # noqa: PLC0415
        MOUNTED_CONDITION_NAME,
        UNHORSED_CONDITION_NAME,
    )
    from world.conditions.berserk_content import BERSERK_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.constants import (  # noqa: PLC0415
        CHARM_CONDITION_NAME,
        UNCONSCIOUS_CONDITION_NAME,
        FoundationalCapability,
    )
    from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.items.constants import (  # noqa: PLC0415
        ARMOR_SOAK_TARGET_NAME,
        FASHION_PRESENTATION_CHECK_TYPE_NAME,
        FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
    )
    from world.justice.constants import (  # noqa: PLC0415
        GATHER_EVIDENCE_CHECK_NAME,
        SCRUTINIZE_EVIDENCE_CHECK_NAME,
    )
    from world.magic.audere import (  # noqa: PLC0415
        AUDERE_CONDITION_NAME,
        AUDERE_MAJORA_CONDITION_NAME,
        SOULFRAY_CONDITION_NAME,
    )
    from world.magic.constants import ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.magic.seeds_checks import MAGICAL_ENDURANCE_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.magic.services.technique_training import (  # noqa: PLC0415
        TECHNIQUE_TRAINING_CHECK_TYPE_NAME,
    )
    from world.mechanics.succor_shared import SUCCOR_CHALLENGE_NAME  # noqa: PLC0415
    from world.room_features.seeds import SANCTUM_KIND_NAME  # noqa: PLC0415
    from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.traits.models import TraitType  # noqa: PLC0415

    return (
        # --- ConditionTemplate: single-feature conditions --------------------------------
        ContentDependency(
            key="audere-conditions",
            label="Audere and Audere Majora condition templates",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/magic/audere.py:261 offer_audere(); "
                "world/magic/audere_majora.py:679 (majora crossing)"
            ),
            consequence=(
                "Accepting an Audere or Audere Majora corruption offer raises "
                "ConditionTemplate.DoesNotExist and crashes the offer instead of "
                "applying the condition."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(
                    AUDERE_CONDITION_NAME,
                    AUDERE_MAJORA_CONDITION_NAME,
                    SOULFRAY_CONDITION_NAME,
                ),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="mount-combat-conditions",
            label="Mounted and Unhorsed condition templates",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/combat/services.py:3774 (mounted charge); "
                "world/combat/services.py:7901 (joust unhorsing)"
            ),
            consequence=(
                "Charging while mounted, or losing a joust badly enough to be "
                "unhorsed, raises ConditionTemplate.DoesNotExist and crashes the "
                "combat action for both participants."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(MOUNTED_CONDITION_NAME, UNHORSED_CONDITION_NAME),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="sent-flying-condition",
            label="Sent Flying condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:5443 _apply_sent_flying_marker()",
            consequence=(
                "A knockback attack that should send its target flying silently "
                "applies no marker - the target never gets a mid-air catch window "
                "and the fall never resolves at end of round."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(SENT_FLYING_CONDITION_NAME,),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="shielded-condition",
            label="Shielded condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/covenants/perks/evaluators.py:1180",
            consequence=(
                "A covenant perk gated on an ally being Shielded silently never "
                "triggers, even when the ally is actually defending."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(SHIELDED_CONDITION_NAME,),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="surrounded-condition",
            label="Surrounded isolation tagging (template, pool, entry stage)",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/battles/resolution.py:1160-1190 _apply_surrounded_isolation() - "
                "needs the Surrounded ConditionTemplate, the surrounded_entry "
                "ConsequencePool, and its stage_order=1 ConditionStage, not the "
                "template alone"
            ),
            consequence=(
                "A battle participant cut off from their allies never gets tagged "
                "Surrounded - the acute-peril stacking from being isolated silently "
                "never applies."
            ),
            probe=CustomProbe(fn=_probe_surrounded_condition_bundle),
        ),
        ContentDependency(
            key="unconscious-condition",
            label="Unconscious condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/vitals/services.py:1407 unconscious_instance()",
            consequence=(
                "Every unconsciousness check (dream access, intoxication blackout) "
                "silently reports the character as awake even when they should be "
                "out cold."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(UNCONSCIOUS_CONDITION_NAME,),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="charm-condition",
            label="Charm condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/companions/services.py:512 promote_summon_to_companion()",
            consequence=(
                "Promoting a charmed enemy to a permanent companion raises "
                "ConditionTemplate.DoesNotExist and crashes the promotion."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate", names=(CHARM_CONDITION_NAME,), case_insensitive=True
            ),
        ),
        ContentDependency(
            key="savaged-condition",
            label="Savaged condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/companions/services.py:398 _apply_savaged()",
            consequence=(
                "A companion drawn the stay_incapacitated outcome walks away "
                "unmarked, so that draw is indistinguishable from recovering "
                "and the pool's three tiers collapse to two."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(SAVAGED_CONDITION_NAME,),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="plummeting-condition",
            label="Plummeting condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/plummet.py:129 begin_plummet()",
            consequence=(
                "A character who starts falling raises ConditionTemplate.DoesNotExist "
                "instead of beginning to plummet, crashing movement resolution."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=(PLUMMETING_CONDITION_NAME,),
                case_insensitive=True,
            ),
        ),
        ContentDependency(
            key="berserk-condition",
            label="Berserk condition template",
            tier=DependencyTier.REQUIRED,
            consumer="world/species/moon_sensitivity.py:180 _apply_berserk()",
            consequence=(
                "A character losing control to moon-sensitivity fury logs a warning "
                "and never gets the Berserk condition applied - the forced rampage "
                "compulsion silently never fires."
            ),
            # case_insensitive=True for consistency with the other ConditionTemplate
            # declarations, even though this consumer itself (moon_sensitivity.py:180)
            # uses `filter(name=...)`, case-sensitively - see NamedRowsProbe's docstring.
            probe=NamedRowsProbe(
                label="ConditionTemplate", names=(BERSERK_CONDITION_NAME,), case_insensitive=True
            ),
        ),
        ContentDependency(
            key="soul-tether-status-conditions",
            label="Soul Tether Active and Tether Strain condition templates",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/magic/services/soul_tether.py:273 accept_soul_tether(); "
                "world/magic/services/soul_tether.py:1623 "
                "_get_or_create_tether_strain_instance() - literals, no constant"
            ),
            consequence=(
                "Forming a Soul Tether raises ConditionTemplate.DoesNotExist mid-"
                "transaction, so the bond never completes and the Sineater never "
                "accrues Tether Strain."
            ),
            probe=NamedRowsProbe(
                label="ConditionTemplate",
                names=("Soul Tether Active", "Tether Strain"),
                case_insensitive=True,
            ),
        ),
        # --- CheckType: single-feature checks ---------------------------------------------
        ContentDependency(
            key="penetration-check-type",
            label="Penetration check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:343 get_penetration_check_type()",
            consequence=(
                "Resolving a ward's penetration contest crashes with "
                "CheckType.DoesNotExist instead of rolling the check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(PENETRATION_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="concentration-check-type",
            label="Concentration check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:357 get_concentration_check_type()",
            consequence=(
                "Declaring a sustained action crashes with CheckType.DoesNotExist "
                "instead of rolling the Concentration check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(CONCENTRATION_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="fashion-presentation-check-type",
            label="Fashion Presentation check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/items/services/fashion_presentation.py:119",
            consequence=(
                "Presenting an outfit for a fashion check crashes with "
                "CheckType.DoesNotExist instead of rolling the presentation check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(FASHION_PRESENTATION_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="gather-evidence-check-type",
            label="Gather Evidence check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/justice/evidence.py:68 _gather_check_type()",
            consequence=(
                "Generating crime evidence from a legend entry crashes with "
                "CheckType.DoesNotExist instead of producing evidence for the deed."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(GATHER_EVIDENCE_CHECK_NAME,)),
        ),
        ContentDependency(
            key="scrutinize-evidence-check-type",
            label="Scrutinize Evidence check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/justice/case_file.py:111 examine_evidence()",
            consequence=(
                "Examining a piece of evidence crashes with CheckType.DoesNotExist "
                "instead of rolling the Scrutinize Evidence check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(SCRUTINIZE_EVIDENCE_CHECK_NAME,)),
        ),
        ContentDependency(
            key="bind-attempt-check-type",
            label="Bind Attempt check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/companions/services.py:496 promote_summon_to_companion()",
            consequence=(
                "Attempting to bind a summon or charmed enemy into a permanent "
                "companion crashes with CheckType.DoesNotExist instead of rolling "
                "the bind check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(BIND_ATTEMPT_CHECK_NAME,)),
        ),
        ContentDependency(
            key="identification-check-type",
            label="Identification check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/forms/services/identification.py:414 attempt_identification()",
            consequence=(
                "Attempting to recognize a masked or disguised character crashes "
                "with CheckType.DoesNotExist instead of rolling the check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(IDENTIFICATION_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="magical-endurance-check-type",
            label="Magical Endurance check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/soul_tether.py:1403",
            consequence=(
                "The Soul Tether system crashes with CheckType.DoesNotExist instead "
                "of rolling the Magical Endurance check it depends on."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(MAGICAL_ENDURANCE_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="technique-training-check-type",
            label="Technique Training check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/technique_training.py:69 resolve_training_check()",
            consequence=(
                "Training a technique crashes with CheckType.DoesNotExist instead "
                "of rolling the Technique Training check."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(TECHNIQUE_TRAINING_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="endure-hallowed-ground-check-type",
            label="Endure Hallowed Ground check type",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/magic/services/resonance_environment.py:583 "
                "_get_endure_hallowed_ground_check_type()"
            ),
            consequence=(
                "A character resisting hallowed ground's resonance pressure crashes "
                "with CheckType.DoesNotExist instead of rolling to endure it."
            ),
            probe=NamedRowsProbe(
                label="CheckType", names=(ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME,)
            ),
        ),
        ContentDependency(
            key="search-check-type",
            label="Search check type",
            tier=DependencyTier.REQUIRED,
            consumer="actions/definitions/investigation.py:69 SearchAction",
            consequence=(
                "Every player who searches a room gets the placeholder failure "
                '"You can\'t search right now." - the core search action never '
                "produces a result."
            ),
            probe=NamedRowsProbe(label="CheckType", names=(SEARCH_CHECK_TYPE_NAME,)),
        ),
        ContentDependency(
            key="tax-collection-check-type",
            label="Tax Collection check type",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/assets/content.py:95 ensure_asset_promotion_content() - literal, no constant"
            ),
            consequence=(
                "Seeding the Collect Income NPC service offer crashes with "
                "CheckType.DoesNotExist, so the asset-collection tax check is never "
                "wired up for players."
            ),
            probe=NamedRowsProbe(label="CheckType", names=("Tax Collection",)),
        ),
        # --- ChallengeTemplate ---------------------------------------------------------
        ContentDependency(
            key="interpose-challenge",
            label="Interpose challenge template",
            tier=DependencyTier.REQUIRED,
            consumer="world/scenes/sudden_harm.py:58 _bind_interpose_challenge()",
            consequence=(
                "Sudden harm that should offer allies a chance to interpose instead "
                "resolves immediately, with no window for anyone to step in."
            ),
            probe=NamedRowsProbe(label="ChallengeTemplate", names=(INTERPOSE_CHALLENGE_NAME,)),
        ),
        ContentDependency(
            key="succor-challenge",
            label="Succor challenge template",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:10512 _ensure_succor_challenges()",
            consequence=(
                "A declared Succor action (helping a struggling ally) never gets a "
                "challenge bound to it, so the assist silently produces no roll."
            ),
            probe=NamedRowsProbe(label="ChallengeTemplate", names=(SUCCOR_CHALLENGE_NAME,)),
        ),
        ContentDependency(
            key="catch-the-faller-challenge",
            label="Catch the Faller challenge template",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/plummet.py:70 _create_catch_challenge_for()",
            consequence=(
                "A falling character with a would-be catcher present crashes with "
                "ChallengeTemplate.DoesNotExist instead of opening the catch window."
            ),
            probe=NamedRowsProbe(label="ChallengeTemplate", names=(CATCH_THE_FALLER_NAME,)),
        ),
        # --- RoomFeatureKind, Property, KudosSourceCategory, Ritual ---------------------
        ContentDependency(
            key="sanctum-room-feature-kind",
            label="Sanctum room feature kind",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/sanctum_install.py:301 perform_sanctification()",
            consequence=(
                "Performing a sanctification ceremony crashes with "
                "RoomFeatureKind.DoesNotExist instead of installing the Sanctum room "
                "feature."
            ),
            probe=NamedRowsProbe(label="RoomFeatureKind", names=(SANCTUM_KIND_NAME,)),
        ),
        ContentDependency(
            key="aerial-property",
            label="Aerial property",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/services.py:919 _aerial_property()",
            consequence=(
                "Marking or clearing a flying character's aerial state crashes with "
                "Property.DoesNotExist instead of updating their position."
            ),
            probe=NamedRowsProbe(label="Property", names=(AERIAL_PROPERTY_NAME,)),
        ),
        ContentDependency(
            key="social-engagement-kudos-category",
            label="Social Engagement kudos category",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/scenes/action_services.py:193 _get_social_engagement_category(); "
                "world/progression/services/engagement.py:75 "
                "grant_social_engagement_kudos() - literal, no constant"
            ),
            consequence=(
                "Recording engagement kudos during a scene raises "
                "KudosSourceCategory.DoesNotExist and crashes the action; the weekly "
                "social-engagement kudos grant job logs a warning and silently "
                "grants nothing to anyone."
            ),
            probe=NamedRowsProbe(label="KudosSourceCategory", names=("social_engagement",)),
        ),
        ContentDependency(
            key="accept-soul-tether-ritual",
            label="Accept Soul Tether ritual",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/magic/services/soul_tether.py:218 accept_soul_tether() - "
                "literal, no constant"
            ),
            consequence=(
                "Forming a Soul Tether raises Ritual.DoesNotExist mid-transaction "
                "and the bond formation crashes."
            ),
            probe=NamedRowsProbe(label="Ritual", names=("accept_soul_tether",)),
        ),
        # --- CapabilityType --------------------------------------------------------------
        ContentDependency(
            key="movement-capability-type",
            label="Movement capability type",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/services.py:783 _can_move()",
            consequence=(
                "Checking whether a character can move raises "
                "CapabilityType.DoesNotExist and crashes movement resolution - "
                "documented in the call site itself as a fatal configuration error "
                "by design."
            ),
            probe=NamedRowsProbe(label="CapabilityType", names=(FoundationalCapability.MOVEMENT,)),
        ),
        # --- ModifierTarget: required (no numeric fallback) ------------------------------
        ContentDependency(
            key="fashion-presentation-modifier-target",
            label="Fashion Presentation modifier target",
            tier=DependencyTier.REQUIRED,
            consumer="world/items/constants.py:301 get_fashion_modifier_target()",
            consequence=(
                "Computing a fashion presentation modifier crashes with "
                "ModifierTarget.DoesNotExist - documented in the call site itself "
                "as a loud configuration error, not a silent fallback."
            ),
            probe=NamedRowsProbe(
                label="ModifierTarget", names=(FASHION_PRESENTATION_MODIFIER_TARGET_NAME,)
            ),
        ),
        # --- ModifierTarget: required, but guarded - a shipped feature goes silently
        # inert rather than crashing. Each is a real bonus/penalty term a character
        # should feel; absent the row, that term silently reads as 0/random instead
        # of raising, so a staff member reading the panel needs the consequence
        # string (not the tier) to know "no traceback, just missing" from "crash."
        ContentDependency(
            key="armor-soak-modifier-target",
            label="Armor Soak modifier target",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:11565 _resonant_armor_soak()",
            consequence=(
                "Armor soak from resonant/magical modifiers silently falls back to "
                "0 soak for every character - no traceback, the bonus just never "
                "applies."
            ),
            probe=NamedRowsProbe(label="ModifierTarget", names=(ARMOR_SOAK_TARGET_NAME,)),
        ),
        ContentDependency(
            key="consider-bias-direction-modifier-target",
            label="Consider bias-direction modifier target",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/consider.py:128 bias_direction()",
            consequence=(
                "The consider check's optimism/pessimism skew silently falls back "
                "to a random direction instead of the authored bias - no "
                "traceback, just a worse read every time."
            ),
            probe=NamedRowsProbe(label="ModifierTarget", names=("consider_bias_direction",)),
        ),
        # --- Compound-filter probes: name alone would be a false green -------------------
        ContentDependency(
            key="travel-speed-modifier-target",
            label="Travel Speed modifier target",
            tier=DependencyTier.REQUIRED,
            consumer="world/travel/services.py:138 compute_travel_time()",
            consequence=(
                "Per-character travel speed modifiers (weather, magic) silently "
                "fall back to 0 - no traceback, travel just never gets that "
                "adjustment."
            ),
            probe=FilteredRowProbe(
                label="ModifierTarget",
                filters=(("name", "travel_speed"), ("category__name", "travel")),
                absent_detail="No ModifierTarget 'travel_speed' row under category 'travel'.",
            ),
        ),
        ContentDependency(
            key="gossip-check-type",
            label="Gossip check type",
            tier=DependencyTier.REQUIRED,
            consumer="world/secrets/gossip.py:88 _gossip_check_type()",
            consequence=(
                "Planting, seeking, or suppressing gossip crashes with "
                "CheckType.DoesNotExist instead of rolling the Gossip check."
            ),
            probe=FilteredRowProbe(
                label="CheckType",
                filters=(("name", GOSSIP_CHECK_TYPE_NAME), ("category__name", "Social")),
                absent_detail=(
                    f"No CheckType {GOSSIP_CHECK_TYPE_NAME!r} row under category 'Social'."
                ),
            ),
        ),
        ContentDependency(
            key="gossip-specialization",
            label="Gossip specialization",
            tier=DependencyTier.REQUIRED,
            consumer="world/secrets/gossip.py:94 _gossip_specialization()",
            consequence=(
                "Every Gossip skill-gate check (can this character even attempt "
                "gossip actions) crashes with Specialization.DoesNotExist."
            ),
            probe=FilteredRowProbe(
                label="Specialization",
                filters=(("name", "Gossip"), ("parent_skill__trait__name", "Persuasion")),
                absent_detail=("No Specialization 'Gossip' row under skill trait 'Persuasion'."),
            ),
        ),
        ContentDependency(
            key="willpower-stat-trait",
            label="Willpower stat trait",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/anima.py:393 provision_player_anima_ritual()",
            consequence=(
                "Provisioning a player's anima ritual logs a warning and skips "
                "ritual creation entirely for that character when no explicit stat "
                "was chosen at CG."
            ),
            probe=FilteredRowProbe(
                label="Trait",
                filters=(("name", "willpower"), ("trait_type", TraitType.STAT)),
                absent_detail="No Trait 'willpower' row with trait_type=STAT.",
            ),
        ),
        ContentDependency(
            key="hostile-social-consent-category",
            label="Hostile social consent category",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/secrets/services.py:218 accusation_permitted() - literal, "
                "no constant. Looked up by `key`, not `name` "
                "(NaturalKeyConfig.fields = ['key']), so a name-only probe would "
                "check the wrong column"
            ),
            consequence=(
                "The hostile-consent gate silently allows every accusation, even "
                "against a tenure that has blocked hostile targeting - the safety "
                "gate never applies."
            ),
            probe=FilteredRowProbe(
                label="SocialConsentCategory",
                # key__iexact: natural-key text components match case-insensitively
                # (core/natural_keys.py) - an exact filter here would be a false RED
                # for a row the game's own get_by_natural_key() resolves fine.
                filters=(("key__iexact", "hostile"),),
                absent_detail="No SocialConsentCategory row with key='hostile'.",
            ),
        ),
        # --- CustomProbe: composite invariants a name/existence probe can't express ------
        ContentDependency(
            key="path-gift-starter-pools",
            label="Path starter technique pools",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/cg_catalog.py:28 get_technique_options()",
            consequence=(
                "The gift is offered at character creation on the strength of the "
                "tradition alone, and a player who picks it receives only that "
                "tradition's extras - the path contributes nothing it was meant to."
            ),
            probe=CustomProbe(fn=_probe_path_gift_starter_pools),
        ),
        ContentDependency(
            key="audere-majora-thresholds",
            label="Audere Majora tier-crossing thresholds",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/audere_majora.py:679 (tier-crossing offer)",
            consequence=(
                "A character who reaches a boundary level (5, 10, 15, or 20) with "
                "no authored threshold row for it never receives the Audere Majora "
                "crossing offer - the corruption path silently stops advancing."
            ),
            probe=CustomProbe(fn=_probe_audere_majora_thresholds),
            admin_model="AudereMajoraThreshold",
        ),
        ContentDependency(
            key="soulfray-stage-pools",
            label="Soulfray stage consequence pools",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/audere.py, world/conditions/services.py (Soulfray progression)",
            consequence=(
                "A Soulfray stage with no consequence_pool means a character who "
                "progresses to it accumulates severity but the game has nothing to "
                "draw a consequence from - that stage's corruption effect silently "
                "does nothing."
            ),
            probe=CustomProbe(fn=_probe_soulfray_stage_pools),
        ),
        ContentDependency(
            key="stakes-escalation-curves",
            label="Stakes escalation curves",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/combat/escalation.py (assign_default_escalation_curve, "
                "_stakes_intensity_step_bonus)"
            ),
            consequence=(
                "A high-stakes fight with no authored curve for its stakes level "
                "silently never auto-escalates - no traceback, a GM must notice "
                "and set its escalation curve by hand instead of it happening "
                "automatically."
            ),
            probe=CustomProbe(fn=_probe_escalation_curves),
            admin_model="StakesEscalationModifier",
        ),
        ContentDependency(
            key="encounter-outcome-mappings",
            label="Encounter outcome-tier mappings",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/beat_wiring.py:69 classify_battle_outcome()",
            consequence=(
                "An EncounterOutcome x RiskLevel pair with no authored "
                "EncounterOutcomeMapping row means the fight's outcome never "
                "resolves what it's grading: VICTORY/DEFEAT grade a story "
                "beat (concludes with the beat never resolved), FLED/ABANDONED "
                "grade a scenario ENCOUNTER option's route instead (#3565, "
                "concludes with the run left paused) - the error log names "
                "the pair, but nothing grades until a GM authors the missing "
                "row."
            ),
            probe=CustomProbe(fn=_probe_encounter_outcome_mappings),
            admin_model="EncounterOutcomeMapping",
        ),
        ContentDependency(
            key="battle-outcome-mappings",
            label="Battle outcome-tier mappings",
            tier=DependencyTier.REQUIRED,
            consumer="world/battles/beat_wiring.py:31 classify_battle_conclusion_outcome()",
            consequence=(
                "A resolved BattleOutcome (any value except UNRESOLVED) with no "
                "authored BattleOutcomeMapping row means a battle linked to a "
                "story beat concludes and the beat never resolves - the error "
                "log names the outcome, but nothing grades the beat until a GM "
                "authors the missing row."
            ),
            probe=CustomProbe(fn=_probe_battle_outcome_mappings),
        ),
        ContentDependency(
            key="companion-defeat-pool",
            label="Companion defeat consequence pool",
            tier=DependencyTier.REQUIRED,
            consumer="world/companions/services.py:335 resolve_companion_defeat()",
            consequence=(
                "A companion defeated at EXTREME or LETHAL risk is silently "
                "unharmed: it never dies, never comes out savaged, and the "
                "stakes its owner acknowledged mean nothing."
            ),
            probe=CustomProbe(fn=_probe_companion_defeat_pool),
        ),
        ContentDependency(
            key="capability-power-bridges",
            label="Capability combat-power bridges",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "web.admin.tuning.capability_power_analytics.build_capability_power_panel "
                "(Capabilities tuning panel)"
            ),
            consequence=(
                "Capabilities with no authored combat-power bridge silently fall "
                "into the zero bucket on the Capabilities tuning panel - they "
                "still function in play, but the shipped combat-power analytics "
                "feature reports nothing measurable for them, with no traceback."
            ),
            probe=CustomProbe(fn=_probe_capability_bridges),
        ),
        # --- TUNING tier: singleton config tables (dormant-by-design, not yet set) -------
        ContentDependency(
            key="capability-power-config",
            label="Capability power config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/capability_curve.py:31 get_capability_power_config()",
            consequence=(
                "Capability magnitude contributes nothing to the power curve - "
                "every capability-driven power calculation returns its unscaled "
                "base value."
            ),
            probe=AnyRowProbe(label="CapabilityPowerConfig"),
        ),
        ContentDependency(
            key="level-power-config",
            label="Level power config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/power_terms.py:87 get_level_power_config()",
            consequence=(
                "Character and technique level contribute zero bonus to magical "
                "power output - the level-scaling term of the power formula is "
                "silently disabled."
            ),
            probe=AnyRowProbe(label="LevelPowerConfig"),
        ),
        ContentDependency(
            key="aura-power-config",
            label="Aura power config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/power_terms.py:94 get_aura_power_config()",
            consequence=(
                "A caster's aura contributes zero bonus to magical power output - "
                "the aura-scaling term of the power formula is silently disabled."
            ),
            probe=AnyRowProbe(label="AuraPowerConfig"),
        ),
        ContentDependency(
            key="soulfray-config",
            label="Soulfray config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/anima.py:219 apply_anima_ritual_outcome()",
            consequence=(
                "Anima ritual outcomes cannot compute Soulfray severity "
                "accumulation or resilience checks - the ritual outcome silently "
                "omits the Soulfray term."
            ),
            probe=AnyRowProbe(label="SoulfrayConfig"),
        ),
        # --- REQUIRED singleton: no graceful fallback exists ------------------------------
        ContentDependency(
            key="audere-threshold",
            label="Audere offer threshold",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/audere.py:257 offer_audere()",
            consequence=(
                "Accepting an Audere offer silently declines every time regardless "
                "of eligibility - offer_audere() returns accepted=False with no "
                "error, so players believe the offer failed for no reason."
            ),
            probe=AnyRowProbe(label="AudereThreshold"),
        ),
        ContentDependency(
            key="typeclassed-accounts",
            label="Accounts load as the Account typeclass",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "web/api/mixins.py:63 get_available_characters (X-Character-ID auth); "
                "world/checks/views.py:135 played_character_sheet_ids; "
                "world/combat/views.py:1207 played_character_sheet_ids"
            ),
            consequence=(
                "An account whose typeclass path is the base AccountDB model has no typeclass "
                "attributes, so every persona-aware endpoint answers 500 for that "
                "player or staff member (Sentry ARX2-8: the first outside player's "
                "signup account); one with no cmdset storage logs in and can run no "
                "command at all (#3812: the staff account on production). Both heal "
                "on the next server start."
            ),
            probe=CustomProbe(fn=_probe_typeclassed_accounts),
        ),
        ContentDependency(
            key="mfa-secrets-key",
            label="2FA secrets key decrypts stored authenticators",
            tier=DependencyTier.REQUIRED,
            consumer="evennia_extensions/mfa_adapter.py ArxMFAAdapter.decrypt (every 2FA sign-in)",
            consequence=(
                "Every player with two-factor authentication on fails to sign in, and their "
                "recovery codes fail too, until MFA_SECRETS_KEY is restored or staff delete "
                "their authenticators in the admin (ADR-0267)."
            ),
            probe=CustomProbe(fn=_probe_mfa_secrets_key),
        ),
        ContentDependency(
            key="game-clock",
            label="Game clock (IC time anchor)",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/game_clock/views.py:55 ClockViewSet.list(); "
                "world/events/services.py:46 derive_ic_time_from_real(); "
                "world/conditions/services.py:698 _compute_ingame_time_expires()"
            ),
            consequence=(
                "GET /api/clock/ answers 503 NOT_CONFIGURED, the Hall's Time plate "
                "reads 'Time is currently frozen', and every IC-date reader (event "
                "scheduling, in-game-time condition expiry, journals) gets None and "
                "skips. Seed it once through Django admin (add is allowed only while "
                "no row exists) or POST /api/clock/adjust/ as staff."
            ),
            probe=AnyRowProbe(label="GameClock"),
        ),
        ContentDependency(
            key="legend-level-calibration",
            label="Legend level calibration (Rite of Honors)",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/societies/honors.py:343 honor_deed(); "
                "world/achievements/services.py:352 maybe_grant_deed_title()"
            ),
            consequence=(
                "honor_deed() and maybe_grant_deed_title() raise "
                "LegendLevelCalibration.DoesNotExist for the honorer's or the deed's "
                "level when it has no authored row - nobody can honor a deed and no "
                "deed can grant a title until the curve is filled in."
            ),
            probe=AnyRowProbe(label="LegendLevelCalibration"),
        ),
        ContentDependency(
            key="character_creation.beginnings_have_upbringing",
            label="Beginnings without an Upbringing",
            tier=DependencyTier.REQUIRED,
            consumer="LineageStage / get_lineage_errors (#3617)",
            consequence=(
                "A player who picks this beginning reaches Lineage with no "
                "options and cannot finish CG."
            ),
            probe=CustomProbe(fn=_beginnings_without_upbringing),
        ),
        ContentDependency(
            key="character_creation.tradition_state_lines",
            label="Tradition state lines",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "web/admin/tradition_slate/live.py state_line_display(), preview_line(); "
                "world/character_creation/serializers.py TraditionSerializer.get_state_line()"
            ),
            consequence=(
                "The tradition step prints nothing for every Beginning's slate line at "
                "the missing or blank state - the row is shared, not authored per "
                "Beginning, so the gap is silent everywhere at once."
            ),
            probe=CustomProbe(fn=_probe_tradition_state_lines),
            admin_model="TraditionStateLine",
        ),
        ContentDependency(
            key="character_creation.tradition_schooling_lines",
            label="Tradition schooling lines",
            tier=DependencyTier.REQUIRED,
            consumer="web/admin/tradition_slate/live.py schooling_line_display()",
            consequence=(
                "The living-masters schooling set is incomplete for every Beginning at "
                "once at the missing or blank rank."
            ),
            probe=CustomProbe(fn=_probe_schooling_lines),
            admin_model="SchoolingLine",
        ),
        # --- #3831: config tables staff set - REQUIRED (empty breaks or silently
        # disables a shipped mechanic) -----------------------------------------
        ContentDependency(
            key="damage-success-level-multipliers",
            label="Damage success-level multipliers",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/combat/services.py:785 CombatTechniqueResolver._apply_damage(); "
                "world/conditions/services.py get_damage_multiplier()"
            ),
            consequence=(
                "get_damage_multiplier returns 0 for every success level, so no technique deals "
                "damage in combat and every attack prices at 0 DE on the Techniques tuning panel. "
                "The curve the combat tests use: min_success_level 2 at 1.00 (Full), 1 at 0.50 "
                "(Partial)."
            ),
            probe=AnyRowProbe(label="DamageSuccessLevelMultiplier"),
        ),
        ContentDependency(
            key="point-conversion-ranges-stat",
            label="Stat point-conversion ranges",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/checks/services.py:916 _weighted_trait_points(); "
                "web/admin/tuning/technique_analytics.py starting_stats_roller_points()"
            ),
            consequence=(
                "PointConversionRange.calculate_points returns 0 for every stat, so every "
                "check that weights a STAT trait rolls with 0 points from it, and the "
                "Techniques tuning panel's starting-kit report prices every kit at the "
                "level-one floor alone, with no contribution from the character's stats."
            ),
            probe=AnyRowProbe(label="PointConversionRange"),
        ),
        ContentDependency(
            key="fury-tiers",
            label="Fury tiers",
            tier=DependencyTier.REQUIRED,
            consumer="actions/player_interface.py:565 _fury_tier_options()",
            consequence=(
                "The combat declaration offers no Fury tier, so no player can commit Fury or risk "
                "Berserk."
            ),
            probe=AnyRowProbe(label="FuryTier"),
        ),
        ContentDependency(
            key="flee-config",
            label="Flee rules",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:422 get_flee_config()",
            consequence=(
                "get_flee_config raises FleeConfig.DoesNotExist, so any attempt to flee combat "
                "errors."
            ),
            probe=AnyRowProbe(label="FleeConfig"),
        ),
        ContentDependency(
            key="class-stage-health-rates",
            label="Class health growth per level",
            tier=DependencyTier.REQUIRED,
            consumer="world/vitals/services.py derive_base_max_health()",
            consequence=(
                "The class term of max health sums to 0, so a character's health never grows with "
                "level."
            ),
            probe=AnyRowProbe(label="ClassStageHealthRate"),
        ),
        ContentDependency(
            key="treatment-templates",
            label="Treatments",
            tier=DependencyTier.REQUIRED,
            consumer="world/conditions/services.py:4205 perform_treatment()",
            consequence="No treatment exists to perform, so no condition or wound can be treated.",
            probe=AnyRowProbe(label="TreatmentTemplate"),
        ),
        ContentDependency(
            key="building-kinds",
            label="Building kinds",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/buildings/services.py:139 issue_permit(); world/buildings/services.py:251 "
                "validate_permit_site()"
            ),
            consequence="No permit can name a building kind, so nothing can be built.",
            probe=AnyRowProbe(label="BuildingKind"),
        ),
        ContentDependency(
            key="rampart-element-profiles",
            label="Rampart elements",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/services.py:208 raise_rampart()",
            consequence="raise_rampart needs an element profile, so no rampart can be raised.",
            probe=AnyRowProbe(label="RampartElementProfile"),
        ),
        ContentDependency(
            key="mentor-bond-config",
            label="Mentor bond rules",
            tier=DependencyTier.REQUIRED,
            consumer="world/covenants/services.py:2226 get_mentor_bond_config()",
            consequence=(
                "get_mentor_bond_config raises MentorBondConfig.DoesNotExist, so Mentor's Vow "
                "bond scaling errors."
            ),
            probe=AnyRowProbe(label="MentorBondConfig"),
        ),
        ContentDependency(
            key="crafting-recipes",
            label="Crafting recipes",
            tier=DependencyTier.REQUIRED,
            consumer="world/items/crafting/services.py:196 _resolve_recipe_for_quote()",
            consequence=(
                "Every crafting quote raises CraftingNotConfigured, so no item can be crafted."
            ),
            probe=AnyRowProbe(label="CraftingRecipe"),
        ),
        ContentDependency(
            key="npc-roles",
            label="NPC roles",
            tier=DependencyTier.REQUIRED,
            consumer="world/npc_services/views.py:214 (starting an NPC interaction)",
            consequence="No functionary can be placed and no NPC interaction menu can open.",
            probe=AnyRowProbe(label="NPCRole"),
        ),
        ContentDependency(
            key="npc-service-offers",
            label="NPC service offers",
            tier=DependencyTier.REQUIRED,
            consumer="world/npc_services/services.py:453 available_offers()",
            consequence=(
                "Every NPC interaction opens to an empty menu, so permits, missions, loans, "
                "training, court grants and styling are unreachable."
            ),
            probe=AnyRowProbe(label="NPCServiceOffer"),
        ),
        ContentDependency(
            key="predator-kinds",
            label="Predator kinds",
            tier=DependencyTier.REQUIRED,
            consumer="world/predators/services.py:228 _maybe_spawn_band()",
            consequence=(
                "The weekly menace tick returns before spawning, so no predator band ever appears."
            ),
            probe=AnyRowProbe(label="PredatorKind"),
        ),
        ContentDependency(
            key="wedlock-union-kind",
            label="A union kind that confers wedlock",
            tier=DependencyTier.REQUIRED,
            consumer="world/societies/houses/pact_services.py:238 solemnize_wedding()",
            consequence=(
                'solemnize_wedding refuses every wedding with "No law of marriage exists to wed '
                'under."'
            ),
            probe=FilteredRowProbe(
                label="UnionKind",
                filters=(("confers_wedlock", True),),
                absent_detail="No UnionKind with confers_wedlock set exists.",
            ),
        ),
        ContentDependency(
            key="claimable-titles",
            label="Claimable titles for house founding",
            tier=DependencyTier.REQUIRED,
            consumer="world/societies/houses/creator.py:51 claimable_titles()",
            consequence=(
                "Character creation's house-founding step has no title to claim, so no new landed "
                "house can be founded."
            ),
            probe=FilteredRowProbe(
                label="Title",
                filters=(("is_claimable", True),),
                absent_detail="No claimable Title exists.",
            ),
        ),
        ContentDependency(
            key="mission-givers",
            label="Mission givers",
            tier=DependencyTier.REQUIRED,
            consumer="world/missions/services/boards.py:49 postings_for_giver()",
            consequence=(
                "No mission board exists, so players can never discover or take a mission."
            ),
            probe=AnyRowProbe(label="MissionGiver"),
        ),
        ContentDependency(
            key="mission-templates",
            label="Mission templates",
            tier=DependencyTier.REQUIRED,
            consumer="world/missions/services/boards.py:49 postings_for_giver()",
            consequence=(
                "Every mission board shows zero postings. Missions are authored in the Mission "
                "Studio; the admin page is a table view and fallback editor."
            ),
            probe=AnyRowProbe(label="MissionTemplate"),
        ),
        ContentDependency(
            key="default-room-size-tier",
            label="Default room size tier",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/buildings/room_services.py:170 dig_room(); world/buildings/services.py:530 "
                "create_entry_room()"
            ),
            consequence=(
                "A default-sized room resolves no size tier and costs 0 space-budget units, so "
                "the building space budget never limits construction."
            ),
            probe=NamedRowsProbe(label="RoomSizeTier", names=(DEFAULT_ROOM_SIZE_NAME,)),
        ),
        ContentDependency(
            key="risk-calibrations",
            label="Stakes risk calibrations",
            tier=DependencyTier.REQUIRED,
            consumer="world/stories/services/stakes.py:398 validate_stakes_readiness()",
            consequence=(
                "A risked story beat at a risk level with no calibration row can never be marked "
                "ready, so its stakes never settle."
            ),
            probe=CustomProbe(fn=_probe_risk_calibrations),
            admin_model="RiskCalibration",
        ),
        ContentDependency(
            key="covenant-level-thresholds",
            label="Covenant level thresholds",
            tier=DependencyTier.REQUIRED,
            consumer="world/covenants/services.py:1461 recompute_covenant_level()",
            consequence=(
                "recompute_covenant_level finds no threshold, so every covenant stays at level 1."
            ),
            probe=AnyRowProbe(label="CovenantLevelThreshold"),
        ),
        ContentDependency(
            key="gang-turf-reputation-awards",
            label="Gang turf reputation awards",
            tier=DependencyTier.REQUIRED,
            consumer="world/societies/gang_turf.py:72 _tier_to_reputation_delta()",
            consequence="A finished gang-turf project grants no reputation and moves no turf.",
            probe=AnyRowProbe(label="GangTurfReputationAward"),
        ),
        ContentDependency(
            key="war-funding-tier-bonuses",
            label="War funding tier bonuses",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/battles/war_funding_services.py:150 complete_war_funding(); "
                "world/battles/war_funding_services.py:200 get_war_funding_bonus()"
            ),
            consequence=(
                "A finished war-funding drive grants no training XP and no strength, morale or "
                "quality bonus."
            ),
            probe=AnyRowProbe(label="WarFundingTierBonus"),
        ),
        ContentDependency(
            key="readiness-thresholds",
            label="War readiness thresholds",
            tier=DependencyTier.REQUIRED,
            consumer="world/battles/war_funding_services.py:215 get_war_funding_bonus()",
            consequence="Readiness a covenant builds never converts into a unit quality step.",
            probe=AnyRowProbe(label="ReadinessThreshold"),
        ),
        ContentDependency(
            key="city-defense-integrity-bonuses",
            label="City defense integrity bonuses",
            tier=DependencyTier.REQUIRED,
            consumer=(
                "world/battles/city_defense_services.py:134 get_city_defense_integrity_bonus()"
            ),
            consequence=(
                "A finished city-defense project gives the defending side no fortification bonus."
            ),
            probe=AnyRowProbe(label="CityDefenseIntegrityBonus"),
        ),
        # --- #3831: config tables staff set - TUNING (game runs on defaults or a
        # feature stays dormant) --------------------------------------------------
        ContentDependency(
            key="tier-thresholds",
            label="Building polish tier thresholds",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/buildings/room_services.py:526 _check_template_prerequisites() (commission "
                "gate)"
            ),
            consequence=(
                "A polish project's tier prerequisites are an empty many-to-many, so "
                "commissioning it never checks the building's polish tier at all."
            ),
            probe=AnyRowProbe(label="TierThreshold"),
        ),
        ContentDependency(
            key="captivity-config",
            label="Captivity config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/captivity/models.py:209 CaptivityConfig.load()",
            consequence=(
                "Captivity runs on the model's own field defaults rather than an authored row - "
                "staff have nothing to tune."
            ),
            probe=AnyRowProbe(label="CaptivityConfig"),
        ),
        ContentDependency(
            key="cg-point-budget",
            label="CG point budget",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/character_creation/models.py:1793 "
                "CharacterDraft.calculate_cg_points_remaining() "
                "(CGPointBudget.get_active_budget()); world/character_creation/services.py:1483 "
                "_convert_remaining_cg_points_to_xp() "
                "(CGPointBudget.get_active_conversion_rate())"
            ),
            consequence=(
                "Character creation falls back to a 100-point budget and converts unspent points "
                "to XP at a flat 2-to-1 rate, with no active row to tune either number."
            ),
            probe=AnyRowProbe(label="CGPointBudget"),
        ),
        ContentDependency(
            key="check-type-specializations",
            label="Check type specializations",
            tier=DependencyTier.TUNING,
            consumer="world/checks/services.py:989 _calculate_specialization_points()",
            consequence=(
                "No check ever adds a specialization bonus - the third leg of stat + skill + "
                "specialization is silently just stat + skill."
            ),
            probe=AnyRowProbe(label="CheckTypeSpecialization"),
        ),
        ContentDependency(
            key="character-classes",
            label="Character classes",
            tier=DependencyTier.TUNING,
            consumer="world/classes/services.py:26 ensure_default_character_class()",
            consequence=(
                "Only the placeholder Adventurer class exists - character creation offers no "
                "other class to pick."
            ),
            probe=AnyRowProbe(label="CharacterClass"),
        ),
        ContentDependency(
            key="property-grant-profiles",
            label="Property grant profiles",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/property_grant_services.py:48 grant_property_house()",
            consequence=(
                "A Beginning configured to grant a starting house has no profile to grant it "
                "from, so the character receives nothing."
            ),
            probe=AnyRowProbe(label="PropertyGrantProfile"),
        ),
        ContentDependency(
            key="building-listings",
            label="Building listings for sale",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/services.py:962 purchase_building()",
            consequence="No building is ever listed for sale, so no player can buy one for coin.",
            probe=AnyRowProbe(label="BuildingListing"),
        ),
        ContentDependency(
            key="polish-categories",
            label="Polish categories",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/polish_services.py:52 derive_tier_label()",
            consequence=(
                "The polish system has no categories to track, so a building's polish never "
                "derives a tier label in any dimension."
            ),
            probe=AnyRowProbe(label="PolishCategory"),
        ),
        ContentDependency(
            key="project-templates",
            label="Interior design project templates",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/views.py:325 DecorationTemplateViewSet.get_queryset()",
            consequence=(
                "The interior-design catalog a player browses to commission a polish project is "
                "empty, so no project can be commissioned."
            ),
            probe=AnyRowProbe(label="ProjectTemplate"),
        ),
        ContentDependency(
            key="project-template-polish-increments",
            label="Project template polish increments",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/buildings/polish_services.py:68 apply_project_completion(); "
                "world/buildings/room_services.py:622 complete_interior_design()"
            ),
            consequence=(
                "A commissioned project template with no increment rows applies zero polish to "
                "the building or room it targets - the project completes and grants nothing."
            ),
            probe=AnyRowProbe(label="ProjectTemplatePolishIncrement"),
        ),
        ContentDependency(
            key="decoration-kinds",
            label="Decoration kinds",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/services.py:850 place_decoration()",
            consequence="No decoration kind exists to place, so no player can decorate a room.",
            probe=AnyRowProbe(label="DecorationKind"),
        ),
        ContentDependency(
            key="companion-ability-function-tags",
            label="Companion ability function tags",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/sphinx.py:148 _companion_supply()",
            consequence=(
                "A companion's abilities never count toward the Sphinx's kit coverage check, "
                "regardless of what the companion actually brings."
            ),
            probe=AnyRowProbe(label="CompanionAbilityFunctionTag"),
        ),
        ContentDependency(
            key="condition-stage-on-entry",
            label="Condition stage on-entry associations",
            tier=DependencyTier.TUNING,
            consumer="world/conditions/services.py:3138 apply_stage_entry_aftermath()",
            consequence=(
                "Advancing a character into a condition stage never applies that stage's on-entry "
                "condition - the loop has nothing to iterate."
            ),
            probe=AnyRowProbe(label="ConditionStageOnEntry"),
        ),
        ContentDependency(
            key="penetration-outcome-factors",
            label="Penetration outcome factors",
            tier=DependencyTier.TUNING,
            consumer="world/conditions/services.py:4348 get_penetration_factor()",
            consequence=(
                "Penetration always resolves at full power for every success level - the per- "
                "level scaling factor is never applied."
            ),
            probe=AnyRowProbe(label="PenetrationOutcomeFactor"),
        ),
        ContentDependency(
            key="flee-tier-modifiers",
            label="Flee tier modifiers",
            tier=DependencyTier.TUNING,
            consumer="world/combat/services.py:8192 _resolve_flee()",
            consequence=(
                "Flee difficulty ignores the opponent's tier entirely - fleeing is exactly as "
                "hard against a boss as against a minion."
            ),
            probe=AnyRowProbe(label="FleeTierModifier"),
        ),
        ContentDependency(
            key="encounter-aftermath-rules",
            label="Encounter aftermath rules",
            tier=DependencyTier.TUNING,
            consumer="world/combat/services.py:9479 _apply_aftermath_rules()",
            consequence=(
                "A finished encounter produces no aftermath for its outcome and risk level - the "
                "lookup finds nothing to apply."
            ),
            probe=AnyRowProbe(label="EncounterAftermathRule"),
        ),
        ContentDependency(
            key="position-blueprints",
            label="Position blueprints",
            tier=DependencyTier.TUNING,
            consumer="world/areas/positioning/services.py:354 instantiate_blueprint()",
            consequence=(
                "GMs have no tactical map template to clone onto an encounter - every battlefield "
                "has to be laid out by hand."
            ),
            probe=AnyRowProbe(label="PositionBlueprint"),
        ),
        ContentDependency(
            key="rampart-element-resistances",
            label="Rampart element resistances",
            tier=DependencyTier.TUNING,
            consumer="world/combat/services.py:12262 _rampart_resist()",
            consequence=(
                "A Rampart's element resists nothing against any damage type - every intercepted "
                "strike lands as if the Rampart were unaligned."
            ),
            probe=AnyRowProbe(label="RampartElementResistance"),
        ),
        ContentDependency(
            key="action-enhancements",
            label="Action enhancements",
            tier=DependencyTier.TUNING,
            consumer="actions/base.py:338 Action.run()",
            consequence=(
                "No enhancement adds an effect to any action - the enhancement pipeline runs on "
                "every action call with nothing authored to apply."
            ),
            probe=AnyRowProbe(label="ActionEnhancement"),
        ),
        ContentDependency(
            key="court-grant-config",
            label="Court grant config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/services.py:2239 get_court_grant_config()",
            consequence=(
                "Court grant negotiation runs entirely on the model's field defaults - staff have "
                "no authored row to tune it through."
            ),
            probe=AnyRowProbe(label="CourtGrantConfig"),
        ),
        ContentDependency(
            key="dream-peril-config",
            label="Dream peril config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/dreams/peril.py:38 resolve_dream_peril_collapse()",
            consequence=(
                "A dream collapse always resolves at the safest outcome - the peril curve staff "
                "would tune has no authored row behind it."
            ),
            probe=AnyRowProbe(label="DreamPerilConfig"),
        ),
        ContentDependency(
            key="gear-archetype-compatibility",
            label="Gear archetype compatibility",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/services.py:1015 is_gear_compatible()",
            consequence=(
                "A covenant role's stats and its gear archetype's stats never stack - "
                "compatibility never authored means never compatible."
            ),
            probe=AnyRowProbe(label="GearArchetypeCompatibility"),
        ),
        ContentDependency(
            key="covenant-rite-role-packages",
            label="Covenant rite role packages",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/covenants/services.py:2200 perform_covenant_rite() "
                "(CovenantRite.package_for())"
            ),
            consequence=(
                "A rite participant's role and the covenant's level never change which condition "
                "package they receive - every participant falls back to the rite's single "
                "granted_condition."
            ),
            probe=AnyRowProbe(label="CovenantRiteRolePackage"),
        ),
        ContentDependency(
            key="covenant-role-gift-grants",
            label="Covenant role gift grants",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/services.py:854 _grant_role_gifts_and_techniques()",
            consequence=(
                "Engaging a covenant role grants no gifts or techniques - the role carries no "
                "authored gift package to hand out."
            ),
            probe=AnyRowProbe(label="CovenantRoleGiftGrant"),
        ),
        ContentDependency(
            key="insight-table-entries",
            label="Insight table entries",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/insight.py:31 maybe_produce_insight()",
            consequence=(
                "The Insight rider never fires - there is no authored entry for it to draw."
            ),
            probe=AnyRowProbe(label="InsightTableEntry"),
        ),
        ContentDependency(
            key="vow-stat-scaling",
            label="Vow stat scaling",
            tier=DependencyTier.TUNING,
            consumer="world/mechanics/services.py:1021 vow_stat_scaling_bonus()",
            consequence=(
                "A vow's thread level grants zero stat scaling bonus - the scaling term of the "
                "formula is silently disabled."
            ),
            probe=AnyRowProbe(label="VowStatScaling"),
        ),
        ContentDependency(
            key="professions",
            label="Professions",
            tier=DependencyTier.TUNING,
            consumer="world/currency/services.py:1533 run_weekly_employment()",
            consequence=(
                "No profession exists for a character to take, so the weekly employment tick has "
                "nothing to pay anyone for."
            ),
            probe=AnyRowProbe(label="Profession"),
        ),
        ContentDependency(
            key="crafting-material-requirements",
            label="Crafting material requirements",
            tier=DependencyTier.TUNING,
            consumer="world/items/crafting/services.py:202 build_crafting_quote()",
            consequence=(
                "A crafting recipe requires no materials at all - a quote for it lists an empty "
                "ingredient list regardless of what the recipe is supposed to consume."
            ),
            probe=AnyRowProbe(label="CraftingMaterialRequirement"),
        ),
        ContentDependency(
            key="crafting-skill-caps",
            label="Crafting skill caps",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/items/crafting/services.py:202 build_crafting_quote() "
                "(CraftingSkillCap.for_skill())"
            ),
            consequence=(
                "Crafted quality is never capped by the crafter's skill - the skill ceiling on a "
                "recipe's output silently does not apply."
            ),
            probe=AnyRowProbe(label="CraftingSkillCap"),
        ),
        ContentDependency(
            key="crafting-recipe-consequences",
            label="Crafting recipe consequences",
            tier=DependencyTier.TUNING,
            consumer="world/items/crafting/services.py:849 run_crafting_recipe()",
            consequence=(
                "A crafting attempt has no authored risk outcomes to draw from - the weighted- "
                "consequence pool for the roll's tier is empty."
            ),
            probe=AnyRowProbe(label="CraftingRecipeConsequence"),
        ),
        ContentDependency(
            key="crafting-recipe-modifiers",
            label="Crafting recipe modifiers",
            tier=DependencyTier.TUNING,
            consumer="world/items/handlers.py:70 CharacterEquipmentHandler._equipped()",
            consequence=(
                "A crafted item grants no stat modifiers from its recipe, regardless of what the "
                "recipe is meant to confer."
            ),
            probe=AnyRowProbe(label="CraftingRecipeModifier"),
        ),
        ContentDependency(
            key="mantle-level-definitions",
            label="Mantle level definitions",
            tier=DependencyTier.TUNING,
            consumer="world/items/services/mantle.py:57 record_mantle_clearances()",
            consequence=(
                "A mantle's attunement ladder never advances - there is no authored level for a "
                "character's clearance to walk up to."
            ),
            probe=AnyRowProbe(label="MantleLevelDefinition"),
        ),
        ContentDependency(
            key="sentence-ladder-rungs",
            label="Sentence ladder rungs",
            tier=DependencyTier.TUNING,
            consumer="world/justice/pipeline.py:537 _ladder_kind()",
            consequence=(
                "Sentencing falls back to the default band with no per-society escalation - a "
                "society's own sentencing culture never applies."
            ),
            probe=AnyRowProbe(label="SentenceLadderRung"),
        ),
        ContentDependency(
            key="fury-config",
            label="Fury config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/fury.py:34 _config() (get_fury_config())",
            consequence=(
                "Fury runs entirely on the model's field defaults - staff have no authored row to "
                "tune its check trait or thresholds through."
            ),
            probe=AnyRowProbe(label="FuryConfig"),
        ),
        ContentDependency(
            key="aura-affinity-thresholds",
            label="Aura affinity thresholds",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/aura.py:106 fire_aura_threshold_crossings()",
            consequence=(
                "No aura-crossing achievement ever fires, no matter how far a character's "
                "affinity drifts - there is no authored threshold to cross."
            ),
            probe=AnyRowProbe(label="AuraAffinityThreshold"),
        ),
        ContentDependency(
            key="technique-budget-config",
            label="Technique budget config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/technique_builder.py:42 get_technique_budget_config()",
            consequence=(
                "The technique builder prices every technique against the model's field defaults "
                "rather than an authored budget."
            ),
            probe=AnyRowProbe(label="TechniqueBudgetConfig"),
        ),
        ContentDependency(
            key="technique-tier-budget",
            label="Technique tier budget",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/technique_builder.py:51 get_technique_tier_budget()",
            consequence=(
                "A technique tier's own budget is lazily created at its field defaults on first "
                "use - staff have not tuned any tier's budget."
            ),
            probe=AnyRowProbe(label="TechniqueTierBudget"),
        ),
        ContentDependency(
            key="anima-config",
            label="Anima config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/anima.py:59 recompute_max_anima()",
            consequence=(
                "Max anima is computed entirely from the model's field defaults - staff have no "
                "authored row to tune the formula through."
            ),
            probe=AnyRowProbe(label="AnimaConfig"),
        ),
        ContentDependency(
            key="corruption-config",
            label="Corruption config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/corruption.py:60 get_corruption_config()",
            consequence=(
                "Corruption accrual runs on the model's field defaults rather than an authored "
                "row - staff have nothing to tune."
            ),
            probe=AnyRowProbe(label="CorruptionConfig"),
        ),
        ContentDependency(
            key="resonance-tiers",
            label="Resonance tiers",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/touchstone.py:19 touchstone_cast_bonus()",
            consequence=(
                "An equipped touchstone's tier contributes zero cast bonus - the tier-scaled term "
                "of the formula multiplies by nothing."
            ),
            probe=AnyRowProbe(label="ResonanceTier"),
        ),
        ContentDependency(
            key="resonance-alignment-boon-tiers",
            label="Resonance alignment boon tiers",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/magic/services/resonance_environment.py:556 clear_resonance_alignment()"
            ),
            consequence=(
                "An aligned resonance environment grants no boon at any tier - there is no "
                "authored row for a character's alignment to qualify against."
            ),
            probe=AnyRowProbe(label="ResonanceAlignmentBoonTier"),
        ),
        ContentDependency(
            key="beginnings-ritual-grants",
            label="Beginnings ritual grants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/ritual_knowledge.py:33 reconcile_ritual_knowledge()",
            consequence=(
                "A character's Beginning grants no ritual knowledge - that source of the "
                "reconciliation contributes nothing."
            ),
            probe=AnyRowProbe(label="BeginningsRitualGrant"),
        ),
        ContentDependency(
            key="path-ritual-grants",
            label="Path ritual grants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/ritual_knowledge.py:33 reconcile_ritual_knowledge()",
            consequence=(
                "A character's Path grants no ritual knowledge - that source of the "
                "reconciliation contributes nothing."
            ),
            probe=AnyRowProbe(label="PathRitualGrant"),
        ),
        ContentDependency(
            key="distinction-ritual-grants",
            label="Distinction ritual grants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/ritual_knowledge.py:33 reconcile_ritual_knowledge()",
            consequence=(
                "A character's Distinctions grant no ritual knowledge - that source of the "
                "reconciliation contributes nothing."
            ),
            probe=AnyRowProbe(label="DistinctionRitualGrant"),
        ),
        ContentDependency(
            key="tradition-ritual-grants",
            label="Tradition ritual grants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/ritual_knowledge.py:33 reconcile_ritual_knowledge()",
            consequence=(
                "A character's Tradition grants no ritual knowledge - that source of the "
                "reconciliation contributes nothing."
            ),
            probe=AnyRowProbe(label="TraditionRitualGrant"),
        ),
        ContentDependency(
            key="codex-entry-ritual-grants",
            label="Codex entry ritual grants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/services/ritual_knowledge.py:33 reconcile_ritual_knowledge()",
            consequence=(
                "A character's researched Codex entries grant no ritual knowledge - that source "
                "of the reconciliation contributes nothing."
            ),
            probe=AnyRowProbe(label="CodexEntryRitualGrant"),
        ),
        ContentDependency(
            key="distinction-resonance-grants",
            label="Distinction resonance grants",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/magic/services/distinction_resonance.py:66 "
                "reconcile_distinction_resonance_grants()"
            ),
            consequence=(
                "A Distinction seeds no resonance for its holder - the character never gets "
                "claimed into the resonance the distinction is meant to open."
            ),
            probe=AnyRowProbe(label="DistinctionResonanceGrant"),
        ),
        ContentDependency(
            key="technique-variants",
            label="Technique variants",
            tier=DependencyTier.TUNING,
            consumer="world/magic/specialization/services.py:341 resolve_specialized_variant()",
            consequence=(
                "No resonance-specialized variant exists for any technique - specialization never "
                "changes which version of a technique a character casts."
            ),
            probe=AnyRowProbe(label="TechniqueVariant"),
        ),
        ContentDependency(
            key="aesthetic-axis-config",
            label="Aesthetic axis config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/mechanics/services.py:103 get_aesthetic_config()",
            consequence=(
                "Aesthetic axes run entirely on the model's field defaults - staff have no "
                "authored row to tune them through."
            ),
            probe=AnyRowProbe(label="AestheticAxisConfig"),
        ),
        ContentDependency(
            key="mission-categories",
            label="Mission categories",
            tier=DependencyTier.TUNING,
            consumer="world/missions/views.py:500 MissionCategoryViewSet",
            consequence="The mission category picker a player browses is empty.",
            probe=AnyRowProbe(label="MissionCategory"),
        ),
        ContentDependency(
            key="mission-assist-patterns",
            label="Mission assist patterns",
            tier=DependencyTier.TUNING,
            consumer="world/missions/services/support.py:130 _pattern_support_moves()",
            consequence=(
                "A group mission offers no generic assist moves - the pattern catalog a support "
                "character draws from is empty."
            ),
            probe=AnyRowProbe(label="MissionAssistPattern"),
        ),
        ContentDependency(
            key="mission-node-support-options",
            label="Mission node support options",
            tier=DependencyTier.TUNING,
            consumer="world/missions/services/support.py:102 _gem_support_moves()",
            consequence=(
                "No mission node offers an authored support move - a would-be helper has nothing "
                "gem-specific to contribute."
            ),
            probe=AnyRowProbe(label="MissionNodeSupportOption"),
        ),
        ContentDependency(
            key="mission-offer-details",
            label="Mission offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/services.py:369 _mission_gates_pass()",
            consequence=(
                "No NPC ever offers a mission - a MISSION-kind offer with no details row fails "
                "closed before it can be shown."
            ),
            probe=AnyRowProbe(label="MissionOfferDetails"),
        ),
        ContentDependency(
            key="permit-offer-details",
            label="Permit offer details",
            tier=DependencyTier.TUNING,
            consumer="world/buildings/services.py:120 issue_permit()",
            consequence=(
                "No NPC issues a building permit - the offer has no permit details row to act on."
            ),
            probe=AnyRowProbe(label="PermitOfferDetails"),
        ),
        ContentDependency(
            key="loan-offer-details",
            label="Loan offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/effects.py:263 grant_loan()",
            consequence="No NPC offers a loan - the offer has no loan details row to act on.",
            probe=AnyRowProbe(label="LoanOfferDetails"),
        ),
        ContentDependency(
            key="train-offer-details",
            label="Train offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/effects.py:527 run_train_offer()",
            consequence=(
                "No NPC trains a technique - the offer has no training details row to act on."
            ),
            probe=AnyRowProbe(label="TrainOfferDetails"),
        ),
        ContentDependency(
            key="court-grant-offer-details",
            label="Court grant offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/effects.py:309 raise_court_grant()",
            consequence=(
                "A court grant petition never resolves - the offer has no court grant details row "
                "to act on."
            ),
            probe=AnyRowProbe(label="CourtGrantOfferDetails"),
        ),
        ContentDependency(
            key="styling-offer-details",
            label="Styling offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/effects.py:801 run_styling_offer()",
            consequence=(
                "No NPC restyles a character - the offer has no styling details row to act on."
            ),
            probe=AnyRowProbe(label="StylingOfferDetails"),
        ),
        ContentDependency(
            key="profile-recording-offer-details",
            label="Profile recording offer details",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/effects.py:891 run_profile_recording_offer()",
            consequence=(
                "The Archive sitting never runs - the offer has no profile-recording details row "
                "to act on."
            ),
            probe=AnyRowProbe(label="ProfileRecordingOfferDetails"),
        ),
        ContentDependency(
            key="name-cultures",
            label="Name cultures",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/instantiation.py:31 name_culture_for_room()",
            consequence=(
                "Every newly-instantiated NPC is named Sojourner, the hardcoded fallback, since "
                "no authored culture exists at any area or globally."
            ),
            probe=AnyRowProbe(label="NameCulture"),
        ),
        ContentDependency(
            key="name-culture-entries",
            label="Name culture entries",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/instantiation.py:60 _weighted_value()",
            consequence=(
                "An authored name culture yields no name parts to draw from - a culture with no "
                "entries produces an empty surname or given name."
            ),
            probe=AnyRowProbe(label="NameCultureEntry"),
        ),
        ContentDependency(
            key="personality-traits",
            label="Personality traits",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/personality.py:27 assign_random_personality()",
            consequence=(
                "A newly-instantiated NPC gets no likes or dislikes - there is no authored trait "
                "for the assignment to draw."
            ),
            probe=AnyRowProbe(label="PersonalityTrait"),
        ),
        ContentDependency(
            key="staffing-profiles",
            label="Staffing profiles",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/staffing.py:30 _profile_for()",
            consequence=(
                "A building never auto-staffs on activation - no building kind has an authored "
                "baseline crew."
            ),
            probe=AnyRowProbe(label="StaffingProfile"),
        ),
        ContentDependency(
            key="staffing-profile-lines",
            label="Staffing profile lines",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/staffing.py:37 ensure_staffing_for_building()",
            consequence=(
                "A building kind's staffing profile staffs nothing - the profile exists but names "
                "no role to place."
            ),
            probe=AnyRowProbe(label="StaffingProfileLine"),
        ),
        ContentDependency(
            key="regard-event-config",
            label="Regard event config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/npc_services/regard.py:41 get_regard_event_config()",
            consequence=(
                "NPC regard events run entirely on the model's field defaults - staff have no "
                "authored row to tune the story-vital threshold through."
            ),
            probe=AnyRowProbe(label="RegardEventConfig"),
        ),
        ContentDependency(
            key="durance-training-sites",
            label="Durance training sites",
            tier=DependencyTier.TUNING,
            consumer="world/progression/services/advancement.py:392 convene_durance_at_site()",
            consequence=(
                "No training site is active in the room, so a Durance rite can only be convened "
                "by an officiant directly - the site-based convene path finds nothing to "
                "officiate through."
            ),
            probe=AnyRowProbe(label="DuranceTrainingSite"),
        ),
        ContentDependency(
            key="legend-requirements",
            label="Legend requirements",
            tier=DependencyTier.TUNING,
            consumer="world/progression/services/spends.py:112 _check_requirements()",
            consequence=(
                "No class unlock is gated on Legend - the requirement type is wired into the "
                "check but no row uses it."
            ),
            probe=AnyRowProbe(label="LegendRequirement"),
        ),
        ContentDependency(
            key="edict-kinds",
            label="Edict kinds",
            tier=DependencyTier.TUNING,
            consumer="world/societies/proclamations.py:163 enact_edict()",
            consequence="No edict kind exists, so no edict can be enacted at all.",
            probe=AnyRowProbe(label="EdictKind"),
        ),
        ContentDependency(
            key="domain-crisis-types",
            label="Domain crisis types",
            tier=DependencyTier.TUNING,
            consumer="world/societies/houses/crisis_services.py:84 pick_crisis_type()",
            consequence=(
                "No domain crisis type exists, so a domain never spawns a crisis to resolve."
            ),
            probe=AnyRowProbe(label="DomainCrisisType"),
        ),
        ContentDependency(
            key="domain-crisis-type-options",
            label="Domain crisis type options",
            tier=DependencyTier.TUNING,
            consumer="world/societies/houses/crisis_services.py:184 pay_cost_for()",
            consequence=(
                "A spawned crisis offers no resolution path - the option list a player would pay "
                "a cost against is empty."
            ),
            probe=AnyRowProbe(label="DomainCrisisTypeOption"),
        ),
        ContentDependency(
            key="stature-bands",
            label="Stature bands",
            tier=DependencyTier.TUNING,
            consumer="world/societies/houses/stature_services.py:679 band_for_percentile()",
            consequence=(
                "Every house gets the same neutral predation odds and no stature headline - there "
                "is no authored band for its percentile to land in."
            ),
            probe=AnyRowProbe(label="StatureBand"),
        ),
        ContentDependency(
            key="prestige-rank-bands",
            label="Prestige rank bands",
            tier=DependencyTier.TUNING,
            consumer="world/societies/houses/stature_services.py:775 prestige_rank_band()",
            consequence=(
                "A house's prestige rank never drifts its prosperity - there is no authored band "
                "for its rank to land in."
            ),
            probe=AnyRowProbe(label="PrestigeRankBand"),
        ),
        ContentDependency(
            key="pact-kinds",
            label="Pact kinds",
            tier=DependencyTier.TUNING,
            consumer="world/societies/houses/pact_services.py:64 propose_org_pact()",
            consequence="No pact kind exists, so no organization pact can be proposed.",
            probe=AnyRowProbe(label="PactKind"),
        ),
        ContentDependency(
            key="philosophical-archetypes",
            label="Philosophical archetypes",
            tier=DependencyTier.TUNING,
            consumer="world/societies/scandal.py:67 scandalous_societies()",
            consequence=(
                "Scandal reactions ignore philosophy entirely - with no archetype authored, a "
                "deed's philosophical tags never read as scandal to any society."
            ),
            probe=AnyRowProbe(label="PhilosophicalArchetype"),
        ),
        ContentDependency(
            key="stance-archetypes",
            label="Stance archetypes",
            tier=DependencyTier.TUNING,
            consumer="world/societies/proclamations.py:63 apply_stance_reception()",
            consequence=(
                "No stance exists to proclaim - a persona has nothing to align a proclamation to."
            ),
            probe=AnyRowProbe(label="StanceArchetype"),
        ),
        ContentDependency(
            key="propaganda-campaign-tiers",
            label="Propaganda campaign tiers",
            tier=DependencyTier.TUNING,
            consumer="world/societies/propaganda.py:58 launch_propaganda_campaign()",
            consequence="No propaganda campaign can be launched at any tier.",
            probe=AnyRowProbe(label="PropagandaCampaignTier"),
        ),
        ContentDependency(
            key="ranking-displays",
            label="Ranking displays",
            tier=DependencyTier.TUNING,
            consumer="world/societies/ranking_services.py:280 render_ranking_display()",
            consequence=(
                "No leaderboard appears in the world - there is no authored display to render."
            ),
            probe=AnyRowProbe(label="RankingDisplay"),
        ),
        ContentDependency(
            key="legend-settlement-config",
            label="Legend settlement config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/societies/models.py:1927 LegendSettlementConfig.get_active_config()",
            consequence=(
                "Legend settlement runs entirely on the model's field defaults - staff have no "
                "authored row to tune it through."
            ),
            probe=AnyRowProbe(label="LegendSettlementConfig"),
        ),
        ContentDependency(
            key="renown-magnitude-awards",
            label="Renown magnitude awards",
            tier=DependencyTier.TUNING,
            consumer="world/societies/renown.py:413 _magnitude_awards()",
            consequence=(
                "Renown falls back to the built-in magnitude constants rather than a staff- "
                "editable row - the table exists precisely so staff can retune these without a "
                "deploy, and an empty one means they can't."
            ),
            probe=AnyRowProbe(label="RenownMagnitudeAward"),
        ),
        ContentDependency(
            key="scene-round-defaults-config",
            label="Scene round defaults config singleton",
            tier=DependencyTier.TUNING,
            consumer="world/scenes/models.py:1743 get_scene_round_defaults_config()",
            consequence=(
                "Scene rounds run entirely on the model's field defaults - staff have no authored "
                "row to tune them through."
            ),
            probe=AnyRowProbe(label="SceneRoundDefaultsConfig"),
        ),
        ContentDependency(
            key="weather-transitions",
            label="Weather transitions",
            tier=DependencyTier.TUNING,
            consumer="world/weather/services.py:203 _pick_next_weather()",
            consequence=(
                "Weather rolls draw from the flat global pool for every region - an authored "
                "transition table never narrows the roll to what makes sense for that region's "
                "climate."
            ),
            probe=AnyRowProbe(label="WeatherTransition"),
        ),
        ContentDependency(
            key="weather-type-shelters",
            label="Weather type shelters",
            tier=DependencyTier.TUNING,
            consumer="world/weather/services.py:165 apply_weather_exposure()",
            consequence=(
                "Weather gives no hazard shelter of any kind - a sheltered location is exposed "
                "exactly as much as an open one."
            ),
            probe=AnyRowProbe(label="WeatherTypeShelter"),
        ),
    )


def _name_batch_label(probe: ContentProbe) -> str | None:
    """The model label whose row names this probe wants batch-fetched, or None.

    `AnyRowProbe`, `FilteredRowProbe` and `CustomProbe` all resolve themselves and
    never read `known_names`, so they return None here even when they do name a
    model label.
    """
    if not probe.participates_in_name_batch():
        return None
    return probe.model_label()


def _batch_known_names(dependencies: Sequence[ContentDependency]) -> dict[str, frozenset[str]]:
    """One `values_list("name", flat=True)` per distinct model label, never one per probe.

    The names are returned in their authored case. A shared model label can carry
    both case-sensitive and case-insensitive declarations, so casefolding is left
    to each probe's `resolve()`.
    """
    named_labels = {
        label for dep in dependencies if (label := _name_batch_label(dep.probe)) is not None
    }
    return {
        label: frozenset(apps.get_model("arxii", label).objects.values_list("name", flat=True))
        for label in named_labels
    }


def collect_required_content() -> RequiredContentSnapshot:
    """Resolve every declared `ContentDependency` into a `RequiredContentSnapshot`.

    `_batch_known_names` does the name batching (one query per distinct model
    label, never one per declaration) and passes the exact-case result to each
    such probe's `resolve()`, which casefolds on its own when
    `case_insensitive=True`. The names are not lowercased here: a shared model
    label can carry both case-sensitive and case-insensitive declarations (e.g.
    `ConditionTemplate` is all case-insensitive today, but nothing stops a future
    case-sensitive declaration on the same model), so the exact case must survive
    to `resolve()` for it to decide.
    """
    dependencies = build_registry(_declarations())
    known_names_by_label = _batch_known_names(dependencies)

    missing_required: list[DependencyRow] = []
    present_required: list[DependencyRow] = []
    missing_tuning: list[DependencyRow] = []
    present_tuning: list[DependencyRow] = []

    for dependency in dependencies:
        label = _name_batch_label(dependency.probe)
        known_names = known_names_by_label[label] if label is not None else None
        row = DependencyRow(dependency=dependency, result=dependency.probe.resolve(known_names))
        if dependency.tier == DependencyTier.REQUIRED:
            (present_required if row.result.present else missing_required).append(row)
        else:
            (present_tuning if row.result.present else missing_tuning).append(row)

    return RequiredContentSnapshot(
        missing_required=missing_required,
        present_required=present_required,
        missing_tuning=missing_tuning,
        present_tuning=present_tuning,
    )
