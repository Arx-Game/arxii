"""Missions data models (Phase 1).

Phase 1 builds the *affordance registry* and the authored-once
descriptor→affordance bindings.

Design recap: a mission challenge declares which *affordances* it accepts
(e.g. ``distraction``, ``lethal``). Any durable descriptor a character owns
that is *tagged* (bound) with a matching affordance auto-surfaces as an
option. The binding is authored ONCE per (descriptor, affordance) and
globally reused; it records whether the option produces a narrative BRANCH
(no check) or a CHECK (which ``checks.CheckType`` + base risk), the thin IC
framing line, and an optional reusable ``checks.Consequence`` "rider".

The check/consequence substrate is reused wholesale — bindings FK directly
to ``checks.CheckType`` / ``checks.Consequence``; this app introduces no new
check or consequence models.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.missions.constants import (
    MAX_PERCENT_REPLACE,
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    JointCombine,
    MissionStatus,
    OptionKind,
    OptionProduces,
    OptionSource,
)

# Discriminator value -> typed FK field name. Authored-once bindings point at
# a single durable-descriptor model; the discriminator selects which typed FK
# is active (validated by DiscriminatorMixin). ``source_technique`` is
# intentionally absent — see the class docstring on AffordanceBinding.
SOURCE_TRAIT = "trait"
SOURCE_DISTINCTION = "distinction"
SOURCE_ACHIEVEMENT = "achievement"
SOURCE_CAPABILITY = "capability"
SOURCE_CONDITION = "condition"


class SourceKind(models.TextChoices):
    """Which durable-descriptor family a binding is authored against."""

    TRAIT = SOURCE_TRAIT, "Trait"
    DISTINCTION = SOURCE_DISTINCTION, "Distinction"
    ACHIEVEMENT = SOURCE_ACHIEVEMENT, "Achievement"
    CAPABILITY = SOURCE_CAPABILITY, "Capability"
    CONDITION = SOURCE_CONDITION, "Condition"


class AffordanceManager(NaturalKeyManager):
    """Manager for Affordance with natural-key support."""


class Affordance(NaturalKeyMixin, SharedMemoryModel):
    """A capability-category a mission challenge can accept.

    Examples: ``distraction``, ``lethal``, ``stealth``, ``social``. A
    challenge declares the set of affordances it will accept; any descriptor
    a character owns that is bound to one of those affordances surfaces as a
    player option. Pure lookup table — mirrors ``mechanics.ModifierCategory``.
    """

    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Affordance name (e.g., 'distraction', 'lethal').",
    )
    description = models.TextField(
        blank=True,
        help_text="What kind of approach this affordance represents.",
    )

    objects = AffordanceManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class AffordanceBinding(DiscriminatorMixin, SharedMemoryModel):
    """Authored-once link from a durable descriptor to an affordance.

    Exactly one typed ``source_*`` FK is set, selected by ``source_kind``
    (enforced by :class:`~core.mixins.DiscriminatorMixin`). When a character
    owns that descriptor and a challenge accepts ``affordance``, this binding
    surfaces as one player option carrying its ``produces`` mode, optional
    ``check_type`` + ``base_risk``, the thin ``ic_framing`` line, and an
    optional reusable ``rider`` consequence.

    ``source_technique`` is intentionally omitted. ``magic.Technique`` is a
    *per-character* instance (``Technique.name`` is explicitly non-unique and
    techniques are "unique per character and not shared"), so a globally
    authored-once binding cannot point at one technique without binding to a
    single character's instance; Phase 0 also ships no technique-ownership
    resolver to reuse. Deferred until the magic technique catalog model is
    confirmed.
    # DESIGN: technique source deferred — verify magic technique model
    """

    DISCRIMINATOR_FIELD = "source_kind"
    DISCRIMINATOR_MAP = {
        SOURCE_TRAIT: "source_trait",
        SOURCE_DISTINCTION: "source_distinction",
        SOURCE_ACHIEVEMENT: "source_achievement",
        SOURCE_CAPABILITY: "source_capability",
        SOURCE_CONDITION: "source_condition",
    }

    source_kind = models.CharField(
        max_length=20,
        choices=SourceKind.choices,
        help_text="Which durable-descriptor family this binding is authored against.",
    )
    source_trait = models.ForeignKey(
        "traits.Trait",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_distinction = models.ForeignKey(
        "distinctions.Distinction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_achievement = models.ForeignKey(
        "achievements.Achievement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_capability = models.ForeignKey(
        "conditions.CapabilityType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )
    source_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
    )

    affordance = models.ForeignKey(
        Affordance,
        on_delete=models.PROTECT,
        related_name="bindings",
        help_text="The affordance this descriptor satisfies.",
    )
    produces = models.CharField(
        max_length=10,
        choices=OptionProduces.choices,
        help_text="Whether this option is a narrative branch or a resolved check.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="affordance_bindings",
        help_text="Resolved when produces=check; must be null when produces=branch.",
    )
    base_risk = models.PositiveSmallIntegerField(
        default=0,
        help_text="Authored base risk for the surfaced option.",
    )
    ic_framing = models.CharField(
        max_length=200,
        help_text="Thin in-character one-liner describing the approach.",
    )
    rider = models.ForeignKey(
        "checks.Consequence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional reusable consequence attached to this option.",
    )

    def clean(self) -> None:
        super().clean()
        if self.produces == OptionProduces.CHECK and self.check_type_id is None:
            raise ValidationError({"check_type": "Required when produces is 'check'."})
        if self.produces == OptionProduces.BRANCH and self.check_type_id is not None:
            raise ValidationError({"check_type": "Must be null when produces is 'branch'."})

    def __str__(self) -> str:
        return f"{self.get_active_target_name()} → {self.affordance.name}"


# ---------------------------------------------------------------------------
# Phase 2 — mission graph data model (no engine logic; that is Phase 3)
# ---------------------------------------------------------------------------
#
# The mission graph is built NATIVELY here. It reuses the existing
# check/consequence *primitives* by FK only — ``checks.CheckType``,
# ``traits.CheckOutcome`` (the six-tier outcome), ``checks.Consequence`` —
# and does NOT overload ``mechanics.ChallengeTemplate``/``ChallengeInstance``
# (those carry combat/situation/reveal semantics missions do not want).


class MissionTemplate(SharedMemoryModel):
    """An authored mission: the static graph plus its availability metadata.

    A template owns one graph of :class:`MissionNode` rows (entered at the
    single ``is_entry`` node) and is drawn into availability by
    ``base_weight``/``percent_replace``. ``summary``/``epilogue`` are the
    rich IC bookend lore shown to players at start and wrap.
    """

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    summary = models.TextField(help_text="Rich IC opening lore (mission bookend).")
    epilogue = models.TextField(blank=True, help_text="Rich IC wrap-up lore.")
    level_band_min = models.PositiveSmallIntegerField()
    level_band_max = models.PositiveSmallIntegerField()
    risk_tier = models.PositiveSmallIntegerField()
    base_weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative weight in the availability draw.",
    )
    created_in_era = models.ForeignKey(
        "stories.Era",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Arc association — the era this mission was authored for.",
    )
    arc_scope = models.CharField(
        max_length=10,
        choices=ArcScope.choices,
        help_text="Whether this is offered globally, per-org, or per-giver.",
    )
    percent_replace = models.PositiveSmallIntegerField(
        default=0,
        help_text="Percent chance this template replaces an existing offer (0-100).",
    )
    cooldown = models.DurationField(help_text="Per-giver re-offer cooldown.")
    is_active = models.BooleanField(default=True)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.level_band_min > self.level_band_max:
            errors["level_band_min"] = "level_band_min cannot exceed level_band_max."
        if self.percent_replace > MAX_PERCENT_REPLACE:
            errors["percent_replace"] = f"percent_replace cannot exceed {MAX_PERCENT_REPLACE}."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.name


class MissionNode(SharedMemoryModel):
    """One decision point in a mission graph.

    Exactly one node per template is the ``is_entry`` node. Multi-participant
    nodes resolve contested choices via ``conflict_mode``; JOINT mode further
    needs ``joint_combine`` (and ``joint_count`` when COUNT).
    """

    template = models.ForeignKey(
        MissionTemplate,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    key = models.SlugField(
        max_length=100,
        help_text="Stable per-template node key (unique within the template).",
    )
    is_entry = models.BooleanField(default=False)
    conflict_mode = models.CharField(
        max_length=10,
        choices=ConflictMode.choices,
        help_text="How contested option choices resolve for multiple participants.",
    )
    joint_combine = models.CharField(
        max_length=10,
        choices=JointCombine.choices,
        null=True,
        blank=True,
        help_text="JOINT mode: how participant results combine.",
    )
    joint_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="JOINT+COUNT mode: minimum number of successes required.",
    )
    allowed_riders = models.ManyToManyField(
        "checks.Consequence",
        blank=True,
        related_name="+",
        help_text="Reusable consequence riders permitted at this node.",
    )
    deny_all_riders = models.BooleanField(
        default=False,
        help_text="When true, no consequence riders may attach at this node.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "key"],
                name="unique_missionnode_template_key",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        # Exactly one entry node per template.
        if self.is_entry and self.template_id is not None:
            other_entries = MissionNode.objects.filter(
                template_id=self.template_id,
                is_entry=True,
            ).exclude(pk=self.pk)
            if other_entries.exists():
                errors["is_entry"] = "Template already has an entry node."

        # JOINT-mode coupling between conflict_mode/joint_combine/joint_count.
        if self.conflict_mode == ConflictMode.JOINT:
            if not self.joint_combine:
                errors["joint_combine"] = "Required when conflict_mode is JOINT."
            elif self.joint_combine == JointCombine.COUNT and self.joint_count is None:
                errors["joint_count"] = "Required when joint_combine is COUNT."
            elif self.joint_combine != JointCombine.COUNT and self.joint_count is not None:
                errors["joint_count"] = "Must be null unless joint_combine is COUNT."
        else:
            if self.joint_combine:
                errors["joint_combine"] = "Must be null unless conflict_mode is JOINT."
            if self.joint_count is not None:
                errors["joint_count"] = "Must be null unless conflict_mode is JOINT."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.template.slug}:{self.key}"


class MissionOption(SharedMemoryModel):
    """One choice available at a :class:`MissionNode`.

    An option is either AFFORDANCE-sourced (surfaced from the acting
    character's owned descriptor bindings whose affordance is accepted) or
    AUTHORED (hand-written). Independently, it is a BRANCH (routes the graph
    with no dice) or a CHECK (resolves a ``checks.CheckType`` first).
    """

    node = models.ForeignKey(
        MissionNode,
        on_delete=models.CASCADE,
        related_name="options",
    )
    order = models.PositiveSmallIntegerField(
        help_text="Display/evaluation order within the node (no Meta.ordering — "
        "callers order explicitly).",
    )
    option_kind = models.CharField(
        max_length=10,
        choices=OptionKind.choices,
    )
    source_kind = models.CharField(
        max_length=10,
        choices=OptionSource.choices,
    )
    accepted_affordances = models.ManyToManyField(
        Affordance,
        blank=True,
        related_name="accepting_options",
        help_text="AFFORDANCE source: descriptor bindings to these affordances surface here.",
    )
    # SANCTIONED DYNAMIC JSON: this is the design §4 predicate tree consumed
    # by the Phase 0 ``evaluate`` engine. It is the one approved JSONField in
    # this app, exactly mirroring ``distinctions.DistinctionPrerequisite.
    # rule_json`` — see world/missions/types.py for the rationale. No other
    # JSONField is permitted in missions.
    visibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Phase 0 predicate tree gating this option's visibility.",
    )
    authored_check_type = models.ForeignKey(
        "checks.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="AUTHORED+CHECK: the check resolved by this option.",
    )
    authored_base_risk = models.PositiveSmallIntegerField(default=0)
    authored_ic_framing = models.CharField(max_length=200, blank=True)
    branch_target = models.ForeignKey(
        MissionNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="BRANCH/authored route: the node this option leads to.",
    )

    def _affordance_source_errors(self) -> dict[str, str]:
        """AFFORDANCE-sourced options forbid the authored_* fields.

        NOTE: ``accepted_affordances`` is M2M and cannot be validated in
        ``model.clean()`` before the row has a pk. The "≥1 accepted
        affordance" rule is enforced by
        ``world.missions.services.validate_mission_option`` (covered by a
        dedicated test). We do NOT fake an M2M check here.
        """
        if self.source_kind != OptionSource.AFFORDANCE:
            return {}
        errors: dict[str, str] = {}
        if self.authored_check_type_id is not None:
            errors["authored_check_type"] = "Must be null for AFFORDANCE-sourced options."
        if self.authored_base_risk:
            errors["authored_base_risk"] = "Must be 0 for AFFORDANCE-sourced options."
        if self.authored_ic_framing:
            errors["authored_ic_framing"] = "Must be blank for AFFORDANCE-sourced options."
        return errors

    def _kind_errors(self) -> dict[str, str]:
        """BRANCH forbids check fields; AUTHORED+CHECK requires a check type."""
        errors: dict[str, str] = {}
        if self.option_kind == OptionKind.BRANCH:
            if self.authored_check_type_id is not None:
                errors["authored_check_type"] = "Must be null for BRANCH options."
            if self.authored_base_risk:
                errors["authored_base_risk"] = "Must be 0 for BRANCH options."
        elif (
            self.option_kind == OptionKind.CHECK
            and self.source_kind == OptionSource.AUTHORED
            and self.authored_check_type_id is None
        ):
            errors["authored_check_type"] = "Required for AUTHORED options that resolve a CHECK."
        return errors

    def clean(self) -> None:
        super().clean()
        errors = {**self._affordance_source_errors(), **self._kind_errors()}
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.node}#{self.order}"


class MissionOptionRoute(SharedMemoryModel):
    """Where a :class:`MissionOption` leads.

    For a CHECK option there is one route per resolved ``traits.CheckOutcome``
    tier. For a BRANCH option there is exactly one route with ``outcome_tier``
    null. A null ``target_node`` is a terminal (mission-complete) route.
    ``is_random_set`` flags that the destination is drawn from this route's
    weighted :class:`MissionOptionRouteCandidate` rows instead of
    ``target_node``.
    """

    option = models.ForeignKey(
        MissionOption,
        on_delete=models.CASCADE,
        related_name="routes",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Resolved outcome tier; null = the single BRANCH route.",
    )
    target_node = models.ForeignKey(
        MissionNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Destination node; null = terminal (mission complete).",
    )
    is_random_set = models.BooleanField(
        default=False,
        help_text="When true, destination is drawn from weighted candidates.",
    )

    def __str__(self) -> str:
        tier = self.outcome_tier.name if self.outcome_tier_id else "branch"
        return f"{self.option} [{tier}]"


class MissionOptionRouteCandidate(SharedMemoryModel):
    """One weighted destination in a randomized :class:`MissionOptionRoute`.

    When the parent route's ``is_random_set`` is true the engine picks one
    candidate by ``weight``.
    """

    route = models.ForeignKey(
        MissionOptionRoute,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    target_node = models.ForeignKey(
        MissionNode,
        on_delete=models.CASCADE,
        related_name="+",
    )
    weight = models.PositiveSmallIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.route} → {self.target_node} ({self.weight})"


class MissionInstance(SharedMemoryModel):
    """A live run of a :class:`MissionTemplate`.

    INVARIANT: there is NO scratch/variable/JSON-state field. All run state
    is the tuple of ``current_node`` (null = complete), the durable
    :class:`MissionNodeSnapshot` rows, and the real applied consequences
    recorded as :class:`MissionDeedRecord` rows (design §7). Do not add a
    state blob here.
    """

    template = models.ForeignKey(
        MissionTemplate,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    current_node = models.ForeignKey(
        MissionNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Where the run currently sits; null = complete.",
    )
    status = models.CharField(
        max_length=10,
        choices=MissionStatus.choices,
        default=MissionStatus.ACTIVE,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.template.slug} ({self.status})"


class MissionParticipant(SharedMemoryModel):
    """A character taking part in a :class:`MissionInstance`.

    Exactly one participant per instance is the contract holder.
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="+",
    )
    is_contract_holder = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "character"],
                name="unique_missionparticipant_instance_character",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.is_contract_holder and self.instance_id is not None:
            other_holders = MissionParticipant.objects.filter(
                instance_id=self.instance_id,
                is_contract_holder=True,
            ).exclude(pk=self.pk)
            if other_holders.exists():
                raise ValidationError(
                    {"is_contract_holder": "Instance already has a contract holder."}
                )

    def __str__(self) -> str:
        return f"{self.character} @ {self.instance}"


class MissionNodeSnapshot(SharedMemoryModel):
    """Durable per-node-entry state capture for one participant.

    Phase 2 only defines the row; Phase 3 populates it on node entry. It is
    the durable-state capture point that lets the engine reason about a run
    without any mutable state blob on :class:`MissionInstance`.
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    node = models.ForeignKey(
        MissionNode,
        on_delete=models.PROTECT,
        related_name="+",
    )
    participant = models.ForeignKey(
        MissionParticipant,
        on_delete=models.CASCADE,
        related_name="+",
    )
    taken_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"snapshot {self.node} / {self.participant}"


class MissionDeedRecord(SharedMemoryModel):
    """A recorded consequential act within a :class:`MissionInstance`.

    Moral/narrative consequence follows the *actor* (design §10), so the
    actor is the acting participant's character. ``outcome`` is null for a
    BRANCH option (no dice). The structured rewards emitted by the engine
    are stored as child :class:`MissionDeedRewardLine` rows (NOT a dict);
    the in-memory return shape is ``world.missions.types.DeedRewardLine``.
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="deeds",
    )
    actor = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The acting participant's character — consequence follows the actor.",
    )
    node = models.ForeignKey(
        MissionNode,
        on_delete=models.PROTECT,
        related_name="+",
    )
    option = models.ForeignKey(
        MissionOption,
        on_delete=models.PROTECT,
        related_name="+",
    )
    outcome = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Resolved outcome tier; null for a BRANCH deed.",
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"deed {self.option} by {self.actor}"


class MissionDeedRewardLine(SharedMemoryModel):
    """One persisted structured reward line for a :class:`MissionDeedRecord`.

    This is the persisted counterpart of
    :class:`world.missions.types.DeedRewardLine`. Reward summaries are
    structured wire/record data, NOT config — but we still do not use a
    JSONField. The payload is kept to the minimal typed columns Phase 5
    needs: an optional ``amount`` and a free ``ref`` discriminator string.
    """

    deed = models.ForeignKey(
        MissionDeedRecord,
        on_delete=models.CASCADE,
        related_name="reward_lines",
    )
    kind = models.CharField(
        max_length=12,
        choices=DeedRewardKind.choices,
    )
    sink = models.CharField(
        max_length=14,
        choices=DeedRewardSink.choices,
    )
    amount = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Numeric magnitude of the reward, when applicable.",
    )
    ref = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional reference/discriminator (e.g., a rumor key).",
    )

    def __str__(self) -> str:
        return f"{self.get_kind_display()}/{self.get_sink_display()} ({self.amount})"
