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
    """One registry row: a code path's hard dependency on authored content."""

    key: str
    label: str
    tier: DependencyTier
    consumer: str
    consequence: str
    probe: ContentProbe


@dataclass(frozen=True, slots=True)
class DependencyRow:
    """A `ContentDependency` paired with its resolved `ProbeResult`."""

    dependency: ContentDependency
    result: ProbeResult


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
    """No account row has ``db_typeclass_path`` = the base ``AccountDB`` model.

    Consumer: every view that reads typeclass state off ``request.user``
    (``get_available_characters`` behind the ``X-Character-ID`` header,
    ``played_character_sheet_ids`` in checks and combat, ``puppet``). Django's
    ``ArxAccountAdapter.new_user`` stops signup making such rows; Django's
    ``create_superuser`` still does, and rows from before the adapter fix stay
    on ``AccountDB`` until repointed by hand (ADR-0260: no data migration for a handful of
    pre-launch rows). A hit here is one of those.
    """
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    base_model_rows = tuple(
        AccountDB.objects.filter(
            db_typeclass_path__in=("", "evennia.accounts.models.AccountDB")
        ).values_list("username", flat=True)
    )
    detail = (
        f"Account(s) whose typeclass path is the base AccountDB model, not "
        f"typeclasses.accounts.Account: {', '.join(base_model_rows)}. "
        "Set db_typeclass_path to settings.BASE_ACCOUNT_TYPECLASS by hand: "
        "AccountDB.objects.filter(username=...).update(db_typeclass_path=...) in "
        "`arx manage shell`."
        if base_model_rows
        else ""
    )
    return ProbeResult(present=not base_model_rows, missing=base_model_rows, detail=detail)


def _probe_mfa_secrets_key() -> ProbeResult:
    """``MFA_SECRETS_KEY`` parses and still decrypts the oldest stored 2FA secret.

    Consumer: every 2FA sign-in and every recovery-code read
    (``ArxMFAAdapter.decrypt``, ADR-0265). A key rotated without re-encrypting,
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


def _declarations() -> tuple[ContentDependency, ...]:
    """Every hard-coded row dependency the sentinel tracks.

    Every `world.*` name constant is imported here, at function level, rather
    than at module import time - so this admin module never imports game code
    just by being imported itself, and a rename of one of these constants shows
    up as an import error the next time this function runs rather than as a
    silently stale string literal.
    """
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
    from world.relationships.constants import (  # noqa: PLC0415
        RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,
    )
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
            key="relationship-writeup-kudos-category",
            label="Relationship Writeup kudos category",
            tier=DependencyTier.REQUIRED,
            consumer="world/relationships/services.py:578 give_writeup_kudos()",
            consequence=(
                "Commending a relationship writeup silently skips the author's "
                "kudos award - logged as a warning, never delivered."
            ),
            probe=NamedRowsProbe(
                label="KudosSourceCategory", names=(RELATIONSHIP_WRITEUP_KUDOS_CATEGORY,)
            ),
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
                "signup account). createsuperuser still makes such rows, and "
                "pre-adapter signup rows stay on AccountDB until fixed by hand."
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
                "their authenticators in the admin (ADR-0265)."
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
