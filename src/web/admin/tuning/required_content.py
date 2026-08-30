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

from collections.abc import Callable, Iterable
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
    performs the check and reports the result. `model_label()` is the display/
    grouping seam: a probe that names a model returns that model's label, so
    the collector (and a later panel) can report or group by model without
    knowing each probe's concrete type. `participates_in_name_batch()` is the
    narrower seam that actually drives collector batching: only a
    `NamedRowsProbe` shares a single `values_list` query across declarations
    naming the same model - `AnyRowProbe` also has a `model_label()` (it names
    a model too) but resolves its own `.exists()` query per declaration, so it
    must not be folded into that batch.
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
        """Resolve this probe against `known_names` (pre-fetched, lowercased row
        names for this probe's model), or `None` when the probe fetches its own
        data (an `AnyRowProbe`'s `.exists()`, a `CustomProbe`'s callable)."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NamedRowsProbe(ContentProbe):
    """Checks that every one of `names` exists as a row on `label`.

    Matching is case-insensitive to match `ConditionTemplate.get_by_name`'s
    natural-key lookup (`world/conditions/models.py:503-511`) - a probe that
    compared case-sensitively could report a false fault for a row the game
    resolves at runtime without trouble.
    """

    label: str
    names: tuple[str, ...]

    def model_label(self) -> str | None:
        return self.label

    def participates_in_name_batch(self) -> bool:
        return True

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        known = known_names or frozenset()
        missing = tuple(name for name in self.names if name.lower() not in known)
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


def _probe_escalation_curves() -> ProbeResult:
    """At least one `StakesEscalationModifier` row carries a `default_curve`.

    Consumer: `world/combat/escalation.py` (`assign_default_escalation_curve`,
    `_stakes_intensity_step_bonus`). Both already fall back gracefully (no curve
    assigned, a zero intensity bonus) when a stakes level is unseeded - a high-
    stakes fight just needs a GM to set its curve by hand instead of escalating
    on its own. TUNING, not REQUIRED, for that reason.
    """
    from world.combat.constants import StakesLevel  # noqa: PLC0415
    from world.combat.models import StakesEscalationModifier  # noqa: PLC0415

    total_levels = len(StakesLevel.values)
    with_curve = StakesEscalationModifier.objects.filter(default_curve__isnull=False).count()
    present = StakesEscalationModifier.objects.exists() and with_curve > 0
    detail = f"{with_curve} of {total_levels} stakes levels have a default escalation curve."
    return ProbeResult(present=present, detail=detail)


def _probe_capability_bridges() -> ProbeResult:
    """Every evaluated capability has a non-zero, authored combat-power bridge.

    Reuses `web.admin.tuning.capability_power_analytics`'s existing 24h-cached
    panel builder rather than re-running the DE evaluator - see that module's
    docstring for the caching contract this must not duplicate.
    """
    from web.admin.tuning.capability_power_analytics import (  # noqa: PLC0415
        CapabilityPowerAnalyticsParams,
        build_capability_power_panel,
    )

    panel = build_capability_power_panel(CapabilityPowerAnalyticsParams())
    unbridged = len(panel.zero_bucket)
    detail = (
        f"{unbridged} capabilities have no authored combat-power bridge - see the "
        "Capabilities tuning panel."
    )
    return ProbeResult(present=unbridged == 0, detail=detail)


def _probe_travel_speed_modifier_target() -> ProbeResult:
    """The `travel_speed` `ModifierTarget` exists under the `travel` category.

    A name-only probe would report present for a `travel_speed` row filed
    under the wrong category, which is a false green - the real lookup at
    `world/travel/services.py:138` filters on both.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    exists = ModifierTarget.objects.filter(name="travel_speed", category__name="travel").exists()
    detail = "" if exists else "No ModifierTarget 'travel_speed' row under category 'travel'."
    return ProbeResult(present=exists, detail=detail)


def _probe_gossip_check_type() -> ProbeResult:
    """The Gossip `CheckType` exists under the `Social` category.

    A name-only probe would report present for a Gossip check filed under the
    wrong category - the real lookup at `world/secrets/gossip.py:88` filters
    on both.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME  # noqa: PLC0415

    exists = CheckType.objects.filter(name=GOSSIP_CHECK_TYPE_NAME, category__name="Social").exists()
    detail = (
        "" if exists else f"No CheckType {GOSSIP_CHECK_TYPE_NAME!r} row under category 'Social'."
    )
    return ProbeResult(present=exists, detail=detail)


def _probe_gossip_specialization() -> ProbeResult:
    """The Gossip `Specialization` exists under the Persuasion skill/trait.

    A name-only probe would report present for a Gossip specialization filed
    under the wrong parent skill - the real lookup at
    `world/secrets/gossip.py:94` filters on both.
    """
    from world.skills.models import Specialization  # noqa: PLC0415

    exists = Specialization.objects.filter(
        name="Gossip", parent_skill__trait__name="Persuasion"
    ).exists()
    detail = "" if exists else "No Specialization 'Gossip' row under skill trait 'Persuasion'."
    return ProbeResult(present=exists, detail=detail)


def _probe_willpower_stat_trait() -> ProbeResult:
    """The `willpower` `Trait` exists with `trait_type=STAT`.

    A name-only probe would report present for a `willpower` row of the wrong
    trait type (a skill or aspect can share the name) - the real lookup at
    `world/magic/services/anima.py:393` filters on both.
    """
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    exists = Trait.objects.filter(name="willpower", trait_type=TraitType.STAT).exists()
    detail = "" if exists else "No Trait 'willpower' row with trait_type=STAT."
    return ProbeResult(present=exists, detail=detail)


def _probe_hostile_social_consent_category() -> ProbeResult:
    """The `hostile` `SocialConsentCategory` exists, looked up by `key`.

    `world/secrets/services.py:218` resolves this via
    `get_by_natural_key("hostile")`, and `SocialConsentCategory`'s natural key
    is `key` (`NaturalKeyConfig.fields = ["key"]`), not `name` - a name-based
    `NamedRowsProbe` would check the wrong column entirely (`name` is a
    separate player-facing label field), so this checks `key` directly.
    """
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415

    exists = SocialConsentCategory.objects.filter(key="hostile").exists()
    detail = "" if exists else "No SocialConsentCategory row with key='hostile'."
    return ProbeResult(present=exists, detail=detail)


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
        SURROUNDED_CONDITION_NAME,
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

    return (
        # --- ConditionTemplate: single-feature conditions --------------------------------
        ContentDependency(
            key="audere-conditions",
            label="ConditionTemplate",
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
            ),
        ),
        ContentDependency(
            key="mount-combat-conditions",
            label="ConditionTemplate",
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
                label="ConditionTemplate", names=(MOUNTED_CONDITION_NAME, UNHORSED_CONDITION_NAME)
            ),
        ),
        ContentDependency(
            key="sent-flying-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/combat/services.py:5443 _apply_sent_flying_marker()",
            consequence=(
                "A knockback attack that should send its target flying silently "
                "applies no marker - the target never gets a mid-air catch window "
                "and the fall never resolves at end of round."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(SENT_FLYING_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="shielded-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/covenants/perks/evaluators.py:1180",
            consequence=(
                "A covenant perk gated on an ally being Shielded silently never "
                "triggers, even when the ally is actually defending."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(SHIELDED_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="surrounded-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/battles/resolution.py:1174 (isolation entry)",
            consequence=(
                "A battle participant cut off from their allies never gets tagged "
                "Surrounded - the acute-peril stacking from being isolated silently "
                "never applies."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(SURROUNDED_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="unconscious-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/vitals/services.py:1407 unconscious_instance()",
            consequence=(
                "Every unconsciousness check (dream access, intoxication blackout) "
                "silently reports the character as awake even when they should be "
                "out cold."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(UNCONSCIOUS_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="charm-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/companions/services.py:512 promote_summon_to_companion()",
            consequence=(
                "Promoting a charmed enemy to a permanent companion raises "
                "ConditionTemplate.DoesNotExist and crashes the promotion."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(CHARM_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="plummeting-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/areas/positioning/plummet.py:129 begin_plummet()",
            consequence=(
                "A character who starts falling raises ConditionTemplate.DoesNotExist "
                "instead of beginning to plummet, crashing movement resolution."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(PLUMMETING_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="berserk-condition",
            label="ConditionTemplate",
            tier=DependencyTier.REQUIRED,
            consumer="world/species/moon_sensitivity.py:180 _apply_berserk()",
            consequence=(
                "A character losing control to moon-sensitivity fury logs a warning "
                "and never gets the Berserk condition applied - the forced rampage "
                "compulsion silently never fires."
            ),
            probe=NamedRowsProbe(label="ConditionTemplate", names=(BERSERK_CONDITION_NAME,)),
        ),
        ContentDependency(
            key="soul-tether-status-conditions",
            label="ConditionTemplate",
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
                label="ConditionTemplate", names=("Soul Tether Active", "Tether Strain")
            ),
        ),
        # --- CheckType: single-feature checks ---------------------------------------------
        ContentDependency(
            key="penetration-check-type",
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="CheckType",
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
            label="ChallengeTemplate",
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
            label="ChallengeTemplate",
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
            label="ChallengeTemplate",
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
            label="RoomFeatureKind",
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
            label="Property",
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
            label="KudosSourceCategory",
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
            label="KudosSourceCategory",
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
            label="Ritual",
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
            label="CapabilityType",
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
            label="ModifierTarget",
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
        # --- ModifierTarget: tuning (documented numeric fallback) -------------------------
        ContentDependency(
            key="armor-soak-modifier-target",
            label="ModifierTarget",
            tier=DependencyTier.TUNING,
            consumer="world/combat/services.py:11565 _resonant_armor_soak()",
            consequence=(
                "Armor soak from resonant/magical modifiers falls back to 0 - "
                "combat runs, just without that bonus. Documented at the call site "
                "as an intentional fallback (combat never hard-depends on seed "
                "order)."
            ),
            probe=NamedRowsProbe(label="ModifierTarget", names=(ARMOR_SOAK_TARGET_NAME,)),
        ),
        ContentDependency(
            key="consider-bias-direction-modifier-target",
            label="ModifierTarget",
            tier=DependencyTier.TUNING,
            consumer="world/combat/consider.py:128 bias_direction()",
            consequence=(
                "The consider check's optimism/pessimism skew falls back to a "
                "random direction instead of an authored bias - a worse, not "
                "broken, outcome."
            ),
            probe=NamedRowsProbe(label="ModifierTarget", names=("consider_bias_direction",)),
        ),
        # --- Compound-filter probes: name alone would be a false green -------------------
        ContentDependency(
            key="travel-speed-modifier-target",
            label="ModifierTarget",
            tier=DependencyTier.TUNING,
            consumer="world/travel/services.py:138 compute_travel_time()",
            consequence=(
                "Per-character travel speed modifiers (weather, magic) fall back "
                "to 0 - travel still resolves, just without that adjustment."
            ),
            probe=CustomProbe(fn=_probe_travel_speed_modifier_target),
        ),
        ContentDependency(
            key="gossip-check-type",
            label="CheckType",
            tier=DependencyTier.REQUIRED,
            consumer="world/secrets/gossip.py:88 _gossip_check_type()",
            consequence=(
                "Planting, seeking, or suppressing gossip crashes with "
                "CheckType.DoesNotExist instead of rolling the Gossip check."
            ),
            probe=CustomProbe(fn=_probe_gossip_check_type),
        ),
        ContentDependency(
            key="gossip-specialization",
            label="Specialization",
            tier=DependencyTier.REQUIRED,
            consumer="world/secrets/gossip.py:94 _gossip_specialization()",
            consequence=(
                "Every Gossip skill-gate check (can this character even attempt "
                "gossip actions) crashes with Specialization.DoesNotExist."
            ),
            probe=CustomProbe(fn=_probe_gossip_specialization),
        ),
        ContentDependency(
            key="willpower-stat-trait",
            label="Trait",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/services/anima.py:393 provision_player_anima_ritual()",
            consequence=(
                "Provisioning a player's anima ritual logs a warning and skips "
                "ritual creation entirely for that character when no explicit stat "
                "was chosen at CG."
            ),
            probe=CustomProbe(fn=_probe_willpower_stat_trait),
        ),
        ContentDependency(
            key="hostile-social-consent-category",
            label="SocialConsentCategory",
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
            probe=CustomProbe(fn=_probe_hostile_social_consent_category),
        ),
        # --- CustomProbe: composite invariants a name/existence probe can't express ------
        ContentDependency(
            key="audere-majora-thresholds",
            label="AudereMajoraThreshold",
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
            label="ConditionStage",
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
            label="StakesEscalationModifier",
            tier=DependencyTier.TUNING,
            consumer=(
                "world/combat/escalation.py (assign_default_escalation_curve, "
                "_stakes_intensity_step_bonus)"
            ),
            consequence=(
                "A high-stakes fight with no authored curve for its stakes level "
                "never auto-escalates - it still runs, but a GM must set its "
                "escalation curve by hand instead of it happening automatically."
            ),
            probe=CustomProbe(fn=_probe_escalation_curves),
        ),
        ContentDependency(
            key="capability-power-bridges",
            label="CapabilityType",
            tier=DependencyTier.TUNING,
            consumer=(
                "web.admin.tuning.capability_power_analytics.build_capability_power_panel "
                "(Capabilities tuning panel)"
            ),
            consequence=(
                "Capabilities with no authored combat-power bridge fall into the "
                "zero bucket on the Capabilities tuning panel - they still function "
                "in play, they just contribute nothing measurable to combat power "
                "analytics."
            ),
            probe=CustomProbe(fn=_probe_capability_bridges),
        ),
        # --- TUNING tier: singleton config tables (fallback = a zero'd-out term) ---------
        ContentDependency(
            key="capability-power-config",
            label="CapabilityPowerConfig",
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
            label="LevelPowerConfig",
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
            label="AuraPowerConfig",
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
            label="SoulfrayConfig",
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
            label="AudereThreshold",
            tier=DependencyTier.REQUIRED,
            consumer="world/magic/audere.py:257 offer_audere()",
            consequence=(
                "Accepting an Audere offer silently declines every time regardless "
                "of eligibility - offer_audere() returns accepted=False with no "
                "error, so players believe the offer failed for no reason."
            ),
            probe=AnyRowProbe(label="AudereThreshold"),
        ),
    )


def collect_required_content() -> RequiredContentSnapshot:
    """Resolve every declared `ContentDependency` into a `RequiredContentSnapshot`.

    Batches every `NamedRowsProbe` sharing a model label onto a single
    `values_list("name", flat=True)` query - one per distinct label, never one
    per declaration - and passes the lowercased result to each such probe's
    `resolve()`. `AnyRowProbe` and `CustomProbe` resolve themselves.
    """
    dependencies = build_registry(_declarations())

    named_labels: set[str] = set()
    for dependency in dependencies:
        probe = dependency.probe
        label = probe.model_label()
        if probe.participates_in_name_batch() and label is not None:
            named_labels.add(label)

    known_names_by_label: dict[str, frozenset[str]] = {}
    for label in named_labels:
        model = apps.get_model("arxii", label)
        known_names_by_label[label] = frozenset(
            name.lower() for name in model.objects.values_list("name", flat=True)
        )

    missing_required: list[DependencyRow] = []
    present_required: list[DependencyRow] = []
    missing_tuning: list[DependencyRow] = []
    present_tuning: list[DependencyRow] = []

    for dependency in dependencies:
        probe = dependency.probe
        known_names: frozenset[str] | None = None
        probe_label = probe.model_label()
        if probe.participates_in_name_batch() and probe_label is not None:
            known_names = known_names_by_label[probe_label]
        result = probe.resolve(known_names)
        row = DependencyRow(dependency=dependency, result=result)
        if dependency.tier == DependencyTier.REQUIRED:
            (present_required if result.present else missing_required).append(row)
        else:
            (present_tuning if result.present else missing_tuning).append(row)

    return RequiredContentSnapshot(
        missing_required=missing_required,
        present_required=present_required,
        missing_tuning=missing_tuning,
        present_tuning=present_tuning,
    )
