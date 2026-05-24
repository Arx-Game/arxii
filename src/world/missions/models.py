"""Missions data models.

The mission graph is built natively here. It reuses the existing
check/consequence *primitives* by FK only — ``checks.CheckType``,
``traits.CheckOutcome`` (the outcome ladder), ``checks.Consequence`` — and
does NOT overload ``mechanics.ChallengeTemplate``/``ChallengeInstance``
(those carry combat/situation/reveal semantics missions do not want).

A mission node attaches one or more ``mechanics.ChallengeTemplate`` via
CHALLENGE-sourced :class:`MissionOption`s; each attached challenge's
``ChallengeApproach``es fan out into challenge-contributed options at
runtime (see ``services.challenge_options``). The check/consequence
substrate is reused wholesale — options FK directly to ``checks.CheckType``
and ``checks.Consequence``; this app introduces no new check or consequence
models.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.missions.constants import (
    MAX_PERCENT_REPLACE,
    AccessTier,
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    GiverKind,
    JointCombine,
    MissionStatus,
    OptionKind,
    OptionSource,
    RewardGroupRule,
)

# MissionOptionRouteReward XOR (route, candidate) — module-level so the
# clean() messages stay readable and the magic 2 has a name.
_ERR_REWARD_NO_PARENT = "Exactly one of route or candidate must be set; both are null."
_ERR_REWARD_BOTH_PARENTS = "Cannot set both route and candidate — pick one."
_REWARD_BOTH_PARENTS_SET = 2


# ---------------------------------------------------------------------------
# Mission graph data model
# ---------------------------------------------------------------------------


class MissionCategory(NaturalKeyMixin, SharedMemoryModel):
    """A content-type tag a :class:`MissionTemplate` can carry (multi-valued).

    Examples: assassination, investigation, courtly, heist, social, combat.
    Categories drive browse/filter in the authoring tool (Phase B–D) and
    are designed so a future category→path-aspect-bonus mechanic can hang
    off them without a schema change (design §11.1).
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Browse ordering in the authoring tool (lower = earlier). "
            "No Meta.ordering on the model — callers order explicitly via "
            "``order_by('display_order', 'name')``."
        ),
    )

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Mission categories"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


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
    reward_group_rule = models.CharField(
        max_length=16,
        choices=RewardGroupRule.choices,
        default=RewardGroupRule.ALL_EQUAL,
        help_text=(
            "Multi-participant payout split (authoring knob only; actual "
            "distribution-by-rule is Phase 5)."
        ),
    )
    # SANCTIONED DYNAMIC JSON: the Phase-0 predicate tree consumed by
    # ``world.missions.predicates.evaluate``. Same rationale as
    # ``MissionOption.visibility_rule`` and
    # ``distinctions.DistinctionPrerequisite.rule_json`` — this is the one
    # approved JSONField in the missions app. Empty ``{}`` = no gate
    # (template is available to any predicate-eligible character).
    availability_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Phase 0 predicate tree gating front-door availability for this template.",
    )
    is_active = models.BooleanField(default=True)
    access_tier = models.CharField(
        max_length=16,
        choices=AccessTier.choices,
        default=AccessTier.STAFF_ONLY,
        db_index=True,
        help_text=(
            "Audience gate: STAFF_ONLY hides the template from all but "
            "is_staff_observer characters (the 'in testing' state — the "
            "production-safe default for new templates). OPEN lets the "
            "usual predicate / cooldown / level-band filters take over. "
            "Phase B-7 intentionally ships only two tiers; richer tiers "
            "(society, GM-level, etc.) follow after a permission-design "
            "brainstorm."
        ),
    )
    categories = models.ManyToManyField(
        MissionCategory,
        blank=True,
        related_name="templates",
        help_text=(
            "Content-type tags for this mission (multi-valued, e.g. "
            "assassination, courtly, heist). Drives browse/filter in the "
            "authoring tool."
        ),
    )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.level_band_min > self.level_band_max:
            errors["level_band_min"] = "level_band_min cannot exceed level_band_max."
        if self.percent_replace > MAX_PERCENT_REPLACE:
            errors["percent_replace"] = f"percent_replace cannot exceed {MAX_PERCENT_REPLACE}."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

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
    # DESIGN: rider config is kept as authored node state but no engine
    # path currently consumes it — the binding-rider mechanism it serviced
    # was retired alongside the affordance system. The fields persist so a
    # future phase (e.g. per-approach riders) can wire them up without a
    # schema change.
    allowed_riders = models.ManyToManyField(
        "checks.Consequence",
        blank=True,
        related_name="+",
        help_text=(
            "Reusable consequence riders permitted at this node. NOT "
            "consumed by the engine in Phase A; reserved for future use."
        ),
    )
    deny_all_riders = models.BooleanField(
        default=False,
        help_text=(
            "When true, no consequence riders may attach at this node. NOT "
            "consumed by the engine in Phase A; reserved for future use."
        ),
    )
    editor_x = models.IntegerField(
        default=0,
        help_text=(
            "Mission Studio (Phase E) canvas X coordinate. Pure authoring "
            "metadata — no engine meaning. IntegerField (negatives allowed) "
            "so authors can pan to negative coords."
        ),
    )
    editor_y = models.IntegerField(
        default=0,
        help_text=(
            "Mission Studio (Phase E) canvas Y coordinate. Pure authoring "
            "metadata — no engine meaning. IntegerField (negatives allowed) "
            "so authors can pan to negative coords."
        ),
    )
    flavor_text = models.TextField(
        blank=True,
        help_text=(
            "Thin abstract description of the moment shown to the player "
            "when they enter this node (design §8.2). Paragraph-style "
            "(TextField, unbounded) — the short per-option label is the "
            "option's authored_ic_framing (CharField/200). The rich "
            "narration is the player-authored Legend Entry; this is just "
            "the engine's framing line."
        ),
    )
    flavor_text_needs_rewrite = models.BooleanField(
        default=False,
        help_text=(
            "Phase-D copy service sets True (inherited copy reads as "
            "'rewrite me'); the Phase-D edit service clears it on save. "
            "Surfaces in the Studio's 'N flavor fields are still flagged "
            "as un-rewritten copy' counter (design §10). NOT cleared "
            "automatically at the model layer — service responsibility."
        ),
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

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    # DESIGN: row-level clean() enforces only the single-row node invariants
    # (entry-node uniqueness, JOINT-mode field coupling). Route-set
    # well-formedness across this node's options — a single null-tier BRANCH
    # route per BRANCH option, full outcome-tier coverage + per-tier
    # uniqueness per CHECK option — is GRAPH-level and is validated by the
    # Phase-3 authoring/resolution service, NOT at row level (it cannot be
    # expressed as a single-row invariant). Entry-node uniqueness is
    # row-level; route-set completeness is graph-level-deferred. See the
    # MissionOptionRoute DESIGN note. This split is intentional-on-record.

    def __str__(self) -> str:
        return f"{self.template.slug}:{self.key}"


class MissionOption(SharedMemoryModel):
    """One choice available at a :class:`MissionNode`.

    An option is either AUTHORED (hand-written) or CHALLENGE (references a
    ``mechanics.ChallengeTemplate`` whose approaches fan out into
    challenge-contributed options at runtime). Independently, it is a BRANCH
    (routes the graph with no dice) or a CHECK (resolves a ``checks.CheckType``
    first). CHALLENGE-sourced options are always CHECK.
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
    authored_ic_framing = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Short option-row label shown in the choice list (CharField/200). "
            "Keep terse; the longer 'what happens at this node' narration "
            "belongs in MissionNode.flavor_text."
        ),
    )
    authored_ic_framing_needs_rewrite = models.BooleanField(
        default=False,
        help_text=(
            "Phase-D copy service sets True (inherited copy reads as "
            "'rewrite me'); the Phase-D edit service clears it on save. "
            "Surfaces in the Studio's 'N flavor fields are still flagged "
            "as un-rewritten copy' counter (design §10). NOT cleared "
            "automatically at the model layer — service responsibility."
        ),
    )
    branch_target = models.ForeignKey(
        MissionNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="BRANCH/authored route: the node this option leads to.",
    )
    challenge = models.ForeignKey(
        "mechanics.ChallengeTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "CHALLENGE source: the challenge whose approaches fan out into "
            "this option's challenge-contributed options at runtime. "
            "on_delete=PROTECT — detach all referencing options before "
            "deleting the challenge."
        ),
    )

    def _challenge_source_errors(self) -> dict[str, str]:
        """CHALLENGE-sourced options carry a challenge and forbid authored_* fields.

        A CHALLENGE option fans out per qualifying ``ChallengeApproach``; the
        check type and odds come from the chosen approach and the difficulty
        from the challenge's ``severity``, so the ``authored_*`` fields are
        meaningless here. It is always a CHECK (every approach resolves to a
        ``CheckOutcome``). A non-CHALLENGE option may not set a ``challenge``.
        """
        if self.source_kind != OptionSource.CHALLENGE:
            return (
                {"challenge": "Only CHALLENGE-sourced options may set a challenge."}
                if self.challenge_id is not None
                else {}
            )
        errors: dict[str, str] = {}
        if self.challenge_id is None:
            errors["challenge"] = "Required for CHALLENGE-sourced options."
        if self.option_kind != OptionKind.CHECK:
            errors["option_kind"] = "CHALLENGE-sourced options must be CHECK."
        if self.authored_check_type_id is not None:
            errors["authored_check_type"] = "Must be null for CHALLENGE-sourced options."
        if self.authored_base_risk:
            errors["authored_base_risk"] = "Must be 0 for CHALLENGE-sourced options."
        if self.authored_ic_framing:
            errors["authored_ic_framing"] = "Must be blank for CHALLENGE-sourced options."
        if self.branch_target_id is not None:
            errors["branch_target"] = "Must be null for CHALLENGE-sourced options."
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
        errors = {
            **self._challenge_source_errors(),
            **self._kind_errors(),
        }
        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        # Runs the scalar clean() invariants on the real write path so
        # factory creates / explicit create() calls cannot bypass them.
        self.clean()
        super().save(*args, **kwargs)

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

    # DESIGN: route-set well-formedness is GRAPH-level, NOT row-level, and is
    # deliberately deferred to the Phase-3 authoring/resolution service:
    #   * exactly one null-``outcome_tier`` route per BRANCH option
    #   * full ``traits.CheckOutcome`` tier coverage with no per-tier
    #     duplicates per CHECK option
    # A single MissionOptionRoute row cannot observe its siblings at
    # clean()/save() time, so no row-level invariant is added here.
    # Contrast: entry-node uniqueness IS row-level (enforced in
    # MissionNode.clean()); route-set completeness is graph-level. This split
    # is intentional-on-record, not an oversight.
    #
    # DESIGN (JOINT routing): JOINT nodes route by combined
    # success/failure BUCKET (best success-tier route / worst failure-tier
    # route via ``CheckOutcome.success_level``), NOT per rolled tier — see
    # ``services.multiplayer._combined_route``. Authors of JOINT nodes must
    # author route-sets accordingly: a JOINT contract-holder option needs at
    # least one success-tier route AND at least one failure-tier route; the
    # specific tier within each bucket selects the representative
    # consequence/destination.

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
    consequence = models.ForeignKey(
        "checks.Consequence",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Authored structured effect applied when this route's outcome "
            "tier is rolled; null = pure routing/no effect."
        ),
    )
    outcome_text = models.TextField(
        blank=True,
        help_text=(
            "Player-facing outcome text shown when this route's tier is "
            "rolled (design §8.3). STORED BUT UNCONSUMED in Phase B — the "
            "resolution engine doesn't surface outcome_text today; Phase D "
            "wires it into the player message."
        ),
    )
    outcome_text_needs_rewrite = models.BooleanField(
        default=False,
        help_text=(
            "Phase-D copy service sets True; the Phase-D edit service "
            "clears it on save. NOT cleared automatically at the model "
            "layer — service responsibility."
        ),
    )

    def __str__(self) -> str:
        tier = self.outcome_tier.name if self.outcome_tier_id else "branch"
        return f"{self.option} [{tier}]"


class MissionOptionRouteCandidate(SharedMemoryModel):
    """One weighted destination in a randomized :class:`MissionOptionRoute`.

    When the parent route's ``is_random_set`` is true the engine picks one
    candidate by ``weight``. Each candidate can optionally carry its OWN
    ``consequence`` + ``outcome_text`` override so a random pool entry is
    a full self-contained outcome bundle (design §8.3 — destination +
    consequence + outcome text + (via :class:`MissionOptionRouteReward`
    with ``candidate=`` set) reward lines). The overrides are STORED BUT
    UNCONSUMED in Phase B; Phase D wires per-candidate emission. Until
    then, null/blank values mean "fall back to the parent route's".
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
    consequence = models.ForeignKey(
        "checks.Consequence",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Optional per-candidate consequence override; falls back to "
            "the parent route's consequence when null. STORED BUT "
            "UNCONSUMED in Phase B — Phase D wires per-candidate emission."
        ),
    )
    outcome_text = models.TextField(
        blank=True,
        help_text=(
            "Optional per-candidate outcome text shown to the player. "
            "STORED BUT UNCONSUMED in Phase B — Phase D wires it."
        ),
    )
    outcome_text_needs_rewrite = models.BooleanField(
        default=False,
        help_text=(
            "Phase-D copy service sets True; the Phase-D edit service "
            "clears it on save. NOT cleared automatically at the model "
            "layer — service responsibility."
        ),
    )

    def __str__(self) -> str:
        return f"{self.route} → {self.target_node} ({self.weight})"


class MissionOptionRouteReward(SharedMemoryModel):
    """Authored reward template attached to a route OR a route candidate.

    Phase 5b.0 closed the Phase-3 gap that left no authored source for
    structured rewards on routes. B4 extends the parent surface to also
    allow per-candidate reward bundles (design §8.3 self-contained
    outcome bundle) — exactly one of ``route``/``candidate`` is set.
    Per-candidate rewards are STORED BUT UNCONSUMED in Phase B; Phase D
    wires emission. The route-parented path is unchanged: when the engine
    resolves a TERMINAL route (a route whose ``target_node`` is null), it
    walks the route's ``reward_templates`` and emits one
    :class:`MissionDeedRewardLine` per (template × participant)
    combination per the template's ``reward_group_rule``:

      * ``contract_holder_only=True`` rows emit exactly ONE line, recipient =
        the instance's contract-holding participant's character (regardless of
        the acting actor).
      * ``contract_holder_only=False`` rows broadcast per
        :attr:`MissionTemplate.reward_group_rule` — ``ALL_EQUAL`` emits one
        line per participant with the same ``amount``; ``BY_ROLE`` and
        ``BY_PARTICIPATION`` are deferred to Phase 6 (the engine raises
        :class:`NotImplementedError` so missions authored against unbuilt
        rules surface early, NOT silently degrading to ALL_EQUAL).

    See :func:`world.missions.services.rewards.emit_terminal_rewards`.
    """

    route = models.ForeignKey(
        MissionOptionRoute,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reward_templates",
        help_text=(
            "Parent route (route-level reward). Exactly one of route / "
            "candidate must be set; enforced in clean()."
        ),
    )
    candidate = models.ForeignKey(
        MissionOptionRouteCandidate,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reward_templates",
        help_text=(
            "Parent candidate (per-candidate reward bundle — design §8.3). "
            "STORED BUT UNCONSUMED in Phase B; Phase D wires emission "
            "when a random candidate fires. Exactly one of route / "
            "candidate must be set."
        ),
    )
    kind = models.CharField(
        max_length=12,
        choices=DeedRewardKind.choices,
        help_text="When the emitted line pays out (IMMEDIATE/POST_CRON/PROPAGATION).",
    )
    sink = models.CharField(
        max_length=14,
        choices=DeedRewardSink.choices,
        help_text="Which ledger the emitted line pays into.",
    )
    amount = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Numeric magnitude of the broadcast reward, when applicable.",
    )
    ref = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional reference/discriminator (e.g., a rumor key).",
    )
    contract_holder_only = models.BooleanField(
        default=False,
        help_text=(
            "True → emit exactly one line to the instance's contract holder, "
            "regardless of how many participants ran the mission. False → "
            "distribute per the template's reward_group_rule."
        ),
    )

    class Meta:
        constraints = [
            # Database-level XOR enforcement: bulk_create / QuerySet.update
            # bypass clean(), and a row with both FKs null would be a
            # permanently orphaned reward (invisible to either reverse
            # manager). CHECK constraint catches that at the row level.
            models.CheckConstraint(
                check=(
                    (Q(route__isnull=False) & Q(candidate__isnull=True))
                    | (Q(route__isnull=True) & Q(candidate__isnull=False))
                ),
                name="missionoptionroutereward_exactly_one_parent",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        set_count = int(self.route_id is not None) + int(self.candidate_id is not None)
        if set_count == 0:
            # Non-field error — neither side is the "wrong" one.
            raise ValidationError(_ERR_REWARD_NO_PARENT)
        if set_count == _REWARD_BOTH_PARENTS_SET:
            raise ValidationError(
                {"route": _ERR_REWARD_BOTH_PARENTS, "candidate": _ERR_REWARD_BOTH_PARENTS}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        scope = "holder" if self.contract_holder_only else "broadcast"
        return f"{self.get_kind_display()}/{self.get_sink_display()} ({scope})"


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
    # DESIGN: SET_NULL + the SharedMemoryModel identity map means that after
    # a MissionNode is deleted, an already-loaded MissionInstance's
    # ``current_node``/``current_node_id`` stays STALE until the instance is
    # reloaded (the in-memory FK is not invalidated by the DB-level SET_NULL).
    # The Phase-3 engine must resolve "where is this run" via a fresh query
    # (or treat node-deletion as a run-terminating event) and must NOT assume
    # a live cached ``current_node`` reflects post-delete DB state.
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
    # Phase 5b.3: runtime side of the stories-missions seam. When set, this
    # instance was launched as the resolver of a specific Beat; the Phase-3
    # terminal helper notifies the seam (see
    # ``world.missions.services.beat.on_mission_complete_for_beat``). When
    # null the instance is a "free" run with no Beat reporting. SET_NULL on
    # Beat delete: losing the Beat must not also lose the run record.
    source_beat = models.ForeignKey(
        "stories.Beat",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Optional: the stories Beat that launched this run. SET_NULL on "
            "Beat delete. Engine that flips the Beat at terminal is deferred "
            "to a future stories-missions seam design pass (5b.3 stub-records "
            "the trigger only)."
        ),
    )

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

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

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


class MissionGiver(SharedMemoryModel):
    """An abstracted offer point publishing a curated set of mission templates.

    A giver is the player-facing "front door" (a guild-hall guildmaster, a
    notice-board, a society fixer) and is intentionally NOT a piloted NPC.
    The giver is bound to one Evennia object — its ``target`` — and the
    ``giver_kind`` enum says how to interpret that object: NPC means
    ``target`` is the giver-NPC Character; ROOM_TRIGGER means ``target`` is
    the trigger room itself; ENVIRONMENTAL_DETAIL means ``target`` is the
    examinable item / detail. (All three end up as ``ObjectDB`` rows in
    Evennia — the discrimination happens at the typeclass level, not the
    schema, which is why there is one FK rather than three.) ``org`` is
    optional and used by ORG arc-scope filtering. ``is_active`` is the
    master on/off switch for the giver itself (staff toggle).

    Validation is **loose**: ``clean()`` enforces that ``target`` has the
    typeclass matching ``giver_kind`` when set, but a giver without its
    target is a 'draft' that ``is_publishable`` reports unready. The
    runtime offering surface intentionally doesn't gate on
    ``is_publishable`` today (Phase D's offering surface will).
    """

    name = models.CharField(max_length=200)
    giver_kind = models.CharField(
        max_length=20,
        choices=GiverKind.choices,
        default=GiverKind.ROOM_TRIGGER,
        help_text="How this giver reaches the player; selects the target's expected typeclass.",
    )
    target = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The Evennia object this giver is bound to. Its typeclass must "
            "match giver_kind: NPC → Character-typeclass; ROOM_TRIGGER → "
            "Room-typeclass; ENVIRONMENTAL_DETAIL → any non-Character/Room/"
            "Exit Object (an examinable item or room detail). Null = draft "
            "(see is_publishable). All FK targets land in ObjectDB; the "
            "kind enum + clean() typeclass check enforce semantic shape "
            "without the wasted nullable columns of a discriminator."
        ),
    )
    org = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional organization this giver fronts for (used by ORG arc-scope).",
    )
    templates = models.ManyToManyField(
        MissionTemplate,
        through="MissionGiverOffering",
        blank=True,
        related_name="givers",
        help_text=(
            "Authored template draw pool — see services.availability.offer_missions. "
            "Backed by MissionGiverOffering for per-link odds/requirements overrides."
        ),
    )
    is_active = models.BooleanField(default=True)

    def clean(self) -> None:
        super().clean()
        if self.target_id is None:
            super().clean()
            return
        # Lazy typeclass imports — typeclasses pull in Evennia object
        # machinery and would create circular imports at module load.
        from typeclasses.characters import Character  # noqa: PLC0415
        from typeclasses.exits import Exit  # noqa: PLC0415
        from typeclasses.rooms import Room  # noqa: PLC0415

        target = self.target
        if self.giver_kind == GiverKind.NPC:
            if not target.is_typeclass(Character, exact=False):
                raise ValidationError(
                    {
                        "target": (
                            f"NPC-kind giver's target must be a Character-typeclass "
                            f"ObjectDB; got {target.typeclass_path}."
                        )
                    }
                )
        elif self.giver_kind == GiverKind.ROOM_TRIGGER:
            if not target.is_typeclass(Room, exact=False):
                raise ValidationError(
                    {
                        "target": (
                            f"ROOM_TRIGGER-kind giver's target must be a Room-typeclass "
                            f"ObjectDB; got {target.typeclass_path}."
                        )
                    }
                )
        elif self.giver_kind == GiverKind.ENVIRONMENTAL_DETAIL:
            # An examinable detail / item — must NOT be a Character, Room,
            # or Exit. (Any other Object subclass is fair game: weapons,
            # books, props, room details.)
            if (
                target.is_typeclass(Character, exact=False)
                or target.is_typeclass(Room, exact=False)
                or target.is_typeclass(Exit, exact=False)
            ):
                raise ValidationError(
                    {
                        "target": (
                            f"ENVIRONMENTAL_DETAIL-kind giver's target must be a "
                            f"non-Character/Room/Exit Object (an examinable item or "
                            f"detail); got {target.typeclass_path}."
                        )
                    }
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_publishable(self) -> bool:
        """True when this giver has its ``target`` populated.

        A 'drafty' giver (kind set, target unset) passes ``clean()`` —
        the model layer intentionally allows partial in-progress rows so
        authoring tools can save mid-edit state. ``is_publishable`` is the
        boolean signal that an authoring UI / admin surface uses to gate
        the "ready for live audience" transition (e.g. the operator flipping
        ``MissionTemplate.access_tier`` from ``STAFF_ONLY`` to ``OPEN``).
        Runtime enforcement in ``offer_missions`` is deferred until the
        Phase-D offering surface and the broader visibility/permission
        brainstorm — today this property is consumed only by the
        authoring layer. NOT a ``cached_property`` — ``target`` is
        mutable and ``SharedMemoryModel`` keeps the instance long-lived;
        recomputing on access is the safe choice.
        """
        return self.target_id is not None

    def __str__(self) -> str:
        return self.name


class MissionGiverOffering(SharedMemoryModel):
    """Per-(giver, template) link with optional offering-time overrides.

    The default draw weight and availability requirements come from the
    :class:`MissionTemplate` itself. A per-link override lets the same
    template be offered with different odds or extra gating by a specific
    giver — e.g. the guildmaster offers the standard 'rescue' template
    with extra-favourable odds to VIP members.
    """

    giver = models.ForeignKey(
        MissionGiver,
        on_delete=models.CASCADE,
        related_name="offerings",
    )
    template = models.ForeignKey(
        MissionTemplate,
        on_delete=models.CASCADE,
        related_name="offerings",
    )
    weight_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Optional per-offering draw weight; null = use "
            "template.base_weight. Must be >= 1 when set — 0 would silently "
            "disable this offering, which is not the right tool (use the "
            "template's is_active flag or delete the offering instead)."
        ),
    )
    # SANCTIONED DYNAMIC JSON: same shape as MissionTemplate.availability_rule
    # — a Phase-0 predicate tree consumed by world.missions.predicates.evaluate.
    # Empty {} = use the template's own availability_rule only.
    requirements_override = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Optional per-offering predicate gate (Phase-0 tree shape). "
            "STORED BUT UNCONSUMED in Phase B — services.availability "
            "reads only the template's availability_rule today; Phase D "
            "wires this override in (semantic: AND-compose with the "
            "template rule). Empty {} = no per-offering override."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["giver", "template"],
                name="unique_missiongiveroffering_giver_template",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.weight_override is not None and self.weight_override < 1:
            raise ValidationError(
                {
                    "weight_override": (
                        "Must be >= 1; use null to fall back to "
                        "template.base_weight. 0 would silently disable "
                        "this offering."
                    ),
                }
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.giver} → {self.template}"


class MissionGiverStanding(SharedMemoryModel):
    """Per-(giver, character) standing — cooldown plus an affection integer.

    Generalises the original cooldown-only row to also carry the giver's
    affection / standing with this character. Set by
    ``services.run.accept_mission`` to ``now + template.cooldown`` (cooldown
    side); the affection side is moved by future flirt/seduce-style checks
    against the giver NPC (gameplay TBD — the model just carries the value).
    ``services.availability.offer_missions`` excludes templates whose giver
    has a standing row with ``available_at > now`` for this character.
    Design §6 (giver standing) + §10 (contractual consequence is the
    contract-holder's alone — sharees never get standing rows from accept).
    """

    giver = models.ForeignKey(
        MissionGiver,
        on_delete=models.CASCADE,
        related_name="standings",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="+",
    )
    available_at = models.DateTimeField()
    affection = models.IntegerField(
        default=0,
        help_text=(
            "Per-character standing / affection with this giver. Authoring "
            "tool exposes 'giver_standing_at_least' predicate gates against "
            "this value (Phase C). Negative values are permitted and mean "
            "disliked — the Phase-C 'giver_standing_at_least: N' gate uses "
            "plain >= comparison so it works uniformly across the integer "
            "range (e.g. 'at least -5' is True for affection=-3, False for "
            "affection=-10). Movement mechanic (flirt/seduce checks against "
            "the NPC) is adjacent gameplay work, not built here."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["giver", "character"],
                name="unique_missiongiverstanding_giver_character",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.giver}/{self.character} until {self.available_at:%Y-%m-%d} "
            f"(affection={self.affection})"
        )


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
    recipient = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Character whose ledger this line pays into. May differ from "
            "the parent deed's actor when the route emitted a "
            "contract_holder_only line (Phase 5b.0)."
        ),
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


class MissionRewardQueue(SharedMemoryModel):
    """Deferred-payout queue entry for one emitted :class:`MissionDeedRewardLine`.

    Phase 5b.1 introduces this 1:1 routing trace from emitted lines to the
    deferred-payout cron (Phase 5b.2). Every row corresponds to exactly one
    ``MissionDeedRewardLine`` — the FK is the natural unique key, so
    re-application via ``update_or_create(line=...)`` is idempotent.

    ``kind`` and ``sink`` mirror the line's columns so the cron can filter
    cheaply without an extra join. ``applied`` and ``applied_at`` are flipped
    by the cron when payout succeeds; ``failure_reason`` is populated when
    the cron's sink call raised — telemetry only, NOT used in 5b.1.

    See :func:`world.missions.services.rewards.apply_deed_rewards`.
    """

    deed = models.ForeignKey(
        MissionDeedRecord,
        on_delete=models.CASCADE,
        related_name="queued_rewards",
    )
    line = models.ForeignKey(
        MissionDeedRewardLine,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "The emitted reward line this queue row routes. Exactly one queue "
            "row per line — see UniqueConstraint below."
        ),
    )
    kind = models.CharField(
        max_length=12,
        choices=DeedRewardKind.choices,
        help_text=("Mirrors the line's kind so the cron filters cheaply without an extra join."),
    )
    sink = models.CharField(
        max_length=14,
        choices=DeedRewardSink.choices,
        help_text=("Mirrors the line's sink so the cron filters cheaply without an extra join."),
    )
    applied = models.BooleanField(default=False)
    applied_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Populated when applied=True but the cron's sink call raised; "
            "cron telemetry — not used in Phase 5b.1."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["line"],
                name="unique_missionrewardqueue_line",
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        applied = "applied" if self.applied else "pending"
        return f"queue {self.kind}/{self.sink} ({applied})"
