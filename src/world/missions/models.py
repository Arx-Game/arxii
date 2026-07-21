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

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.missions.constants import (
    LEGEND_RISK_FLOOR_TIER,
    MAX_PERCENT_REPLACE,
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    ExternalAct,
    GiverKind,
    JointCombine,
    MissionStatus,
    MissionVisibility,
    NodeLocationMode,
    OptionKind,
    OptionSource,
    ReportStyle,
    RewardGroupRule,
)
from world.societies.constants import RenownMagnitude, RenownReach, RenownRisk

_PERSONA_MODEL_PATH = "scenes.Persona"
_MISSION_OPTION_ROUTE_MODEL = "missions.MissionOptionRoute"

# MissionOptionRouteReward XOR (route, candidate) — module-level so the
# clean() messages stay readable and the magic 2 has a name.
_ERR_REWARD_NO_PARENT = "Exactly one of route or candidate must be set; both are null."
_ERR_REWARD_BOTH_PARENTS = "Cannot set both route and candidate — pick one."
_REWARD_BOTH_PARENTS_SET = 2

# Cross-app FK string for the reusable consequence primitive (missions FK to
# it by reference only). Centralized to avoid the duplicated-literal SonarCloud
# smell (python:S1192).
_CONSEQUENCE_FK = "checks.Consequence"

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
OBJECT_DB_MODEL = "objects.ObjectDB"
ROOM_PROFILE_MODEL = "evennia_extensions.RoomProfile"

# #1035 — the durable (non-transient) ExternalAct members. Mirrors
# ``world.missions.services.external_acts._DURABLE_ACTS`` — duplicated here
# rather than imported (models.py must not import the services layer) since
# it is a row-level MissionOption.clean() invariant: a durable-act option may
# only be authored on an entry node (fast_forward_external_acts only runs
# from enter_node on the run's true entry; a mid-run node advance never
# re-checks durable state, so a non-entry durable-act option can never fire).
_DURABLE_EXTERNAL_ACTS = frozenset({ExternalAct.THREAD_WOVEN, ExternalAct.COVENANT_SWORN})


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


class MissionTemplate(NaturalKeyMixin, SharedMemoryModel):
    """An authored mission: the static graph plus its availability metadata.

    A template owns one graph of :class:`MissionNode` rows (entered at the
    single ``is_entry`` node) and is drawn into availability by
    ``base_weight``/``percent_replace``. ``summary``/``epilogue`` are the
    rich IC bookend lore shown to players at start and wrap.
    """

    name = models.CharField(max_length=200, unique=True)
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
    report_to_role = models.ForeignKey(
        "npc_services.NPCRole",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="missions_reported_to",
        help_text=(
            "The NPC role a player reports this mission's outcome to (#1753) — a "
            "Functionary of this role, possibly different from the giver (e.g. a "
            "guildmaster). Null → report to the giver's role (source_offer.role); if "
            "there is no NPC giver either, the mission ends at resolution (legend "
            "spreads, no monetary reward)."
        ),
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
    cooldown = models.DurationField(
        validators=[MinValueValidator(timedelta(0))],
        help_text="Per-giver re-offer cooldown. Must be non-negative.",
    )
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
    visibility = models.CharField(
        max_length=16,
        choices=MissionVisibility.choices,
        default=MissionVisibility.RESTRICTED,
        db_index=True,
        help_text=(
            "Audience gate (#870): OPEN surfaces the template to everyone "
            "(availability_rule is not consulted); RESTRICTED makes the "
            "availability_rule predicate the eligibility gate — an empty "
            "rule admits no PC (the emergent staff-only / in-testing "
            "state, and the production-safe default for new templates). "
            "Staff (is_staff_observer) always bypass."
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

    @staticmethod
    def validate_invariants(
        *,
        level_band_min: int,
        level_band_max: int,
        percent_replace: int,
    ) -> None:
        """Pure validator for MissionTemplate's cross-field invariants.

        Called from both ``clean()`` and ``MissionTemplateSerializer.validate()``
        so the rules cannot drift between the model save path and the API
        400-response path. To add a new invariant: extend this function AND
        the kwargs list — both callers will then statically fail to pass the
        new value, so neither path can bypass the new rule.
        """
        errors: dict[str, str] = {}
        if level_band_min > level_band_max:
            errors["level_band_min"] = "level_band_min cannot exceed level_band_max."
        if percent_replace > MAX_PERCENT_REPLACE:
            errors["percent_replace"] = f"percent_replace cannot exceed {MAX_PERCENT_REPLACE}."
        if errors:
            raise ValidationError(errors)

    def clean(self) -> None:
        # validate_invariants is the single source of truth for cross-field
        # invariants. MissionTemplateSerializer.validate() calls it too, so
        # adding a new rule here automatically covers the API 400-response path.
        super().clean()
        self.validate_invariants(
            level_band_min=self.level_band_min,
            level_band_max=self.level_band_max,
            percent_replace=self.percent_replace,
        )

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class MissionNode(NaturalKeyMixin, SharedMemoryModel):
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
        _CONSEQUENCE_FK,
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
    location_mode = models.CharField(
        max_length=10,
        choices=NodeLocationMode.choices,
        default=NodeLocationMode.ANYWHERE,
        help_text=(
            "Default location gate for this node's options (#885): "
            "ANYWHERE = live wherever the character is; ANCHOR = live only "
            "in the instance's grant-time anchor room; ROOMS = live in this "
            "node's authored ``locations`` set. An option with its own "
            "``locations`` rows overrides this default."
        ),
    )
    locations = models.ManyToManyField(
        ROOM_PROFILE_MODEL,
        blank=True,
        related_name="+",
        help_text=(
            "Authored rooms where this node's options are live (consulted "
            "only when ``location_mode=ROOMS``). Options may override "
            "per-option via ``MissionOption.locations``."
        ),
    )
    target_area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Target area for AREA location_mode. A room matches when its "
            "RoomProfile.area is this area or any descendant via AreaClosure."
        ),
    )
    max_support = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "Cap on support declarations per node entry across the party (#2046). "
            "A support declaration takes the place of the helper's pick/vote."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["template", "key"]
        dependencies = ["missions.MissionTemplate"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "key"],
                name="unique_missionnode_template_key",
            ),
        ]
        # Partial index — the rewrite-queue surfaces a small minority of
        # rows (only those flagged True). Avoids seq-scan on the full
        # table when the Studio asks "show me every flagged node".
        indexes = [
            models.Index(
                fields=["template"],
                condition=models.Q(flavor_text_needs_rewrite=True),
                name="mn_flag_partial_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        self._validate_single_entry_node(errors)
        self._validate_joint_mode_coupling(errors)
        self._validate_target_area(errors)

        if errors:
            raise ValidationError(errors)

    def _validate_single_entry_node(self, errors: dict[str, str]) -> None:
        """Enforce exactly one entry node per template."""
        if not (self.is_entry and self.template_id is not None):
            return
        other_entries = MissionNode.objects.filter(
            template_id=self.template_id,
            is_entry=True,
        ).exclude(pk=self.pk)
        if other_entries.exists():
            errors["is_entry"] = "Template already has an entry node."

    def _validate_joint_mode_coupling(self, errors: dict[str, str]) -> None:
        """Enforce conflict_mode/joint_combine/joint_count coupling."""
        if self.conflict_mode != ConflictMode.JOINT:
            if self.joint_combine:
                errors["joint_combine"] = "Must be null unless conflict_mode is JOINT."
            if self.joint_count is not None:
                errors["joint_count"] = "Must be null unless conflict_mode is JOINT."
            return

        if not self.joint_combine:
            errors["joint_combine"] = "Required when conflict_mode is JOINT."
        elif self.joint_combine == JointCombine.COUNT and self.joint_count is None:
            errors["joint_count"] = "Required when joint_combine is COUNT."
        elif self.joint_combine != JointCombine.COUNT and self.joint_count is not None:
            errors["joint_count"] = "Must be null unless joint_combine is COUNT."

    def _validate_target_area(self, errors: dict[str, str]) -> None:
        """Enforce target_area is set only for AREA location_mode."""
        if self.location_mode == NodeLocationMode.AREA and self.target_area_id is None:
            errors["target_area"] = "AREA location mode requires a target area."
        if self.location_mode != NodeLocationMode.AREA and self.target_area_id is not None:
            errors["target_area"] = "target_area is only valid when location_mode is AREA."

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
        return f"{self.template.name}:{self.key}"


class MissionOption(NaturalKeyMixin, SharedMemoryModel):
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
    key = models.SlugField(
        max_length=100,
        default="",
        help_text=(
            "Stable per-node authoring key (unique within the node), independent "
            "of order — reordering options for display must never change their "
            "identity. Required for real authored content; the '' default only "
            "exists so this schema migration doesn't need a data backfill."
        ),
    )
    option_kind = models.CharField(
        max_length=12,
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
    required_act = models.CharField(
        max_length=32,
        choices=ExternalAct.choices,
        blank=True,
        default="",
        help_text=(
            "EXTERNAL_ACT options only: the non-mission act (cast/weave/covenant) "
            "that resolves this option (#1035). Blank for BRANCH/CHECK options."
        ),
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
    locations = models.ManyToManyField(
        ROOM_PROFILE_MODEL,
        blank=True,
        related_name="+",
        help_text=(
            "Per-option location override (#885): rooms where THIS option "
            "is live, regardless of the node's location_mode/locations "
            "default. Empty = inherit the node. This is what expresses "
            "location-split beats (one node, options live in different "
            "rooms — choosing either resolves the node down that route)."
        ),
    )
    spawns_instance = models.BooleanField(
        default=False,
        help_text=(
            "Resolving this option spawns the run's instanced room and "
            "moves the actor inside (#886 — the inn-hallway doorway). Fires "
            "on ANY resolution outcome, so authors put it on BRANCH-style "
            "doorway options; once per run (later resolutions re-enter the "
            "already-spawned room). INSTANCE-mode nodes gate to that room."
        ),
    )
    instance_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Spawned room name (falls back to the template name).",
    )
    instance_description = models.TextField(
        blank=True,
        default="",
        help_text="Spawned room description (authored prose).",
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

    def _durable_act_entry_node_error(self) -> str | None:
        """EXTERNAL_ACT durable acts (THREAD_WOVEN/COVENANT_SWORN) require an entry node.

        ``fast_forward_external_acts`` only fires from ``enter_node`` on the
        run's true entry (#1035) — a mid-run node advance never re-checks
        durable state, so an option authored on a non-entry node could never
        fast-forward.
        """
        if (
            self.required_act in _DURABLE_EXTERNAL_ACTS
            and self.node_id is not None
            and not self.node.is_entry
        ):
            return (
                "Durable external acts (THREAD_WOVEN/COVENANT_SWORN) may only be "
                "authored on entry nodes (#1035) — fast_forward_external_acts only "
                "fires from enter_node on the run's entry; a mid-run node advance "
                "never re-checks durable state, so an option authored on a "
                "non-entry node could never fast-forward."
            )
        return None

    def _external_act_errors(self) -> dict[str, str]:
        """EXTERNAL_ACT: required_act required + check fields forbidden + entry-node guard."""
        errors: dict[str, str] = {}
        if not self.required_act:
            errors["required_act"] = "Required for EXTERNAL_ACT options."
        if self.authored_check_type_id is not None:
            errors["authored_check_type"] = "Must be null for EXTERNAL_ACT options."
        if self.authored_base_risk:
            errors["authored_base_risk"] = "Must be 0 for EXTERNAL_ACT options."
        durable_act_error = self._durable_act_entry_node_error()
        if durable_act_error is not None:
            errors["required_act"] = durable_act_error
        return errors

    def _kind_errors(self) -> dict[str, str]:
        """BRANCH/EXTERNAL_ACT forbid check fields; AUTHORED+CHECK requires a check type."""
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
        elif self.option_kind == OptionKind.EXTERNAL_ACT:
            errors.update(self._external_act_errors())
        if self.option_kind != OptionKind.EXTERNAL_ACT and self.required_act:
            errors["required_act"] = "Only EXTERNAL_ACT options may set required_act."
        return errors

    def clean(self) -> None:
        super().clean()
        errors = {
            **self._challenge_source_errors(),
            **self._kind_errors(),
        }
        if errors:
            raise ValidationError(errors)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["node", "key"], name="unique_missionoption_node_key"),
        ]
        # Partial index — see MissionNode.Meta.indexes for the rationale.
        indexes = [
            models.Index(
                fields=["node"],
                condition=models.Q(authored_ic_framing_needs_rewrite=True),
                name="mo_flag_partial_idx",
            ),
        ]

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["node", "key"]
        dependencies = ["missions.MissionNode"]

    def save(self, *args: object, **kwargs: object) -> None:
        # Runs the scalar clean() invariants on the real write path so
        # factory creates / explicit create() calls cannot bypass them.
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.node}#{self.order}"


class MissionOptionRoute(NaturalKeyMixin, SharedMemoryModel):
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
        _CONSEQUENCE_FK,
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
            "rolled (design §8.3). WIRED by #885 — the resolution engine "
            "surfaces it as the actor's STORY message (a random-set route "
            "prefers the chosen candidate's outcome_text, #941)."
        ),
    )
    outcome_text_needs_rewrite = models.BooleanField(
        default=False,
        help_text=(
            "The copy service sets True on cloned text; the editor serializer "
            "clears it when the text is rewritten (#941). NOT cleared "
            "automatically at the model layer — service/serializer responsibility."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["option", "outcome_tier"]
        dependencies = ["missions.MissionOption"]

    class Meta:
        # Partial index — see MissionNode.Meta.indexes for the rationale.
        indexes = [
            models.Index(
                fields=["option"],
                condition=models.Q(outcome_text_needs_rewrite=True),
                name="mor_flag_partial_idx",
            ),
        ]

    def __str__(self) -> str:
        tier = self.outcome_tier.name if self.outcome_tier_id else "branch"
        return f"{self.option} [{tier}]"


class MissionOptionRouteCandidate(NaturalKeyMixin, SharedMemoryModel):
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
        _CONSEQUENCE_FK,
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["route", "target_node"]
        dependencies = [_MISSION_OPTION_ROUTE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["route", "target_node"],
                name="unique_missionoptionroutecandidate_route_target",
            ),
        ]
        # Partial index — see MissionNode.Meta.indexes for the rationale.
        indexes = [
            models.Index(
                fields=["route"],
                condition=models.Q(outcome_text_needs_rewrite=True),
                name="morc_flag_partial_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.route} → {self.target_node} ({self.weight})"


class MissionOptionRouteReward(NaturalKeyMixin, SharedMemoryModel):
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
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mission_route_rewards",
        help_text="Required when sink=RESONANCE: which Resonance this reward grants.",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Required when sink=ITEM: which ItemTemplate this reward grants.",
    )
    followon_offer = models.ForeignKey(
        "npc_services.NPCServiceOffer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Required when sink=FOLLOW_ON_SUMMONS: the MISSION-kind offer whose "
            "summons fires as the follow-on reward."
        ),
    )
    followon_message = models.TextField(
        blank=True,
        default="",
        help_text=(
            "IC text for the follow-on summons when sink=FOLLOW_ON_SUMMONS. "
            "Empty = the summons shows the offer's default text."
        ),
    )
    followon_expiry_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "When sink=FOLLOW_ON_SUMMONS: the summons lapses after this many "
            "hours if unanswered (triggering the refusal/escalation path). "
            "Null = no expiry (the summons persists until accepted or declined)."
        ),
    )
    contract_holder_only = models.BooleanField(
        default=False,
        help_text=(
            "True → emit exactly one line to the instance's contract holder, "
            "regardless of how many participants ran the mission. False → "
            "distribute per the template's reward_group_rule."
        ),
    )
    sequence = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "NK discriminator only — reward lines have no display order (nothing "
            "ever reorders them). 0 is a pure 'unassigned' sentinel, never a stored "
            "value: save() assigns 1, 2, 3... per parent (route or candidate) when "
            "left at 0, so a legitimately-first row can never be mistaken for "
            "'still needs assignment' on a later re-import in a different order. "
            "Pass an explicit value ≥1 only for fixture round-trip / deliberate "
            "override — see save()."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["route", "candidate", "sequence"]
        dependencies = [_MISSION_OPTION_ROUTE_MODEL, "missions.MissionOptionRouteCandidate"]

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
            # Partial: route/candidate are XOR-nullable, and a plain composite
            # UniqueConstraint would never dedupe across NULLs under Postgres
            # (each NULL is distinct) — these two partial constraints are what
            # actually enforce "sequence unique per non-null parent" (#2470).
            models.UniqueConstraint(
                fields=["route", "sequence"],
                condition=Q(route__isnull=False),
                name="unique_reward_route_sequence",
            ),
            models.UniqueConstraint(
                fields=["candidate", "sequence"],
                condition=Q(candidate__isnull=False),
                name="unique_reward_candidate_sequence",
            ),
        ]

    def clean(self) -> None:  # noqa: C901, PLR0912 — one branch per sink, grows with the enum
        super().clean()
        set_count = int(self.route_id is not None) + int(self.candidate_id is not None)
        if set_count == 0:
            # Non-field error — neither side is the "wrong" one.
            raise ValidationError(_ERR_REWARD_NO_PARENT)
        if set_count == _REWARD_BOTH_PARENTS_SET:
            raise ValidationError(
                {"route": _ERR_REWARD_BOTH_PARENTS, "candidate": _ERR_REWARD_BOTH_PARENTS}
            )
        if self.sink == DeedRewardSink.RESONANCE and self.resonance_id is None:
            msg = "sink=RESONANCE requires resonance to be set."
            raise ValidationError(msg)
        if self.sink != DeedRewardSink.RESONANCE and self.resonance_id is not None:
            msg = "resonance may only be set when sink=RESONANCE."
            raise ValidationError(msg)
        if self.sink == DeedRewardSink.ITEM and self.item_template_id is None:
            msg = "sink=ITEM requires item_template to be set."
            raise ValidationError(msg)
        if self.sink != DeedRewardSink.ITEM and self.item_template_id is not None:
            msg = "item_template may only be set when sink=ITEM."
            raise ValidationError(msg)
        if self.sink == DeedRewardSink.FOLLOW_ON_SUMMONS and self.followon_offer_id is None:
            msg = "sink=FOLLOW_ON_SUMMONS requires followon_offer to be set."
            raise ValidationError(msg)
        if self.sink != DeedRewardSink.FOLLOW_ON_SUMMONS and self.followon_offer_id is not None:
            msg = "followon_offer may only be set when sink=FOLLOW_ON_SUMMONS."
            raise ValidationError(msg)
        if self.sink == DeedRewardSink.FOLLOW_ON_SUMMONS and not self.contract_holder_only:
            msg = "FOLLOW_ON_SUMMONS requires contract_holder_only=True (targets one actor)."
            raise ValidationError(msg)
        if self.sink != DeedRewardSink.FOLLOW_ON_SUMMONS and self.followon_message:
            msg = "followon_message may only be set when sink=FOLLOW_ON_SUMMONS."
            raise ValidationError(msg)
        if self.sink != DeedRewardSink.FOLLOW_ON_SUMMONS and self.followon_expiry_hours is not None:
            msg = "followon_expiry_hours may only be set when sink=FOLLOW_ON_SUMMONS."
            raise ValidationError(msg)
        # #2045: PROJECT sink — route-parented only, amount ≥ 1.
        if self.sink == DeedRewardSink.PROJECT:
            if self.candidate_id is not None:
                msg = (
                    "PROJECT reward lines must be route-parented (candidate-parented "
                    "lines can be dropped by _terminal_deed's single-deed pick — "
                    "a pre-existing gap this feature declines to inherit)."
                )
                raise ValidationError({"candidate": msg})
            if self.amount is None or self.amount < 1:
                msg = "PROJECT reward lines require amount ≥ 1."
                raise ValidationError({"amount": msg})
        # #2051: legend guard — a LEGEND_POINTS reward requires the parent
        # template's risk_tier to be at or above LEGEND_RISK_FLOOR_TIER (HIGH).
        # Legend is earned in the company of others; a low-risk mission cannot
        # pay legend.
        if self.sink == DeedRewardSink.LEGEND_POINTS:
            template = self._parent_template()
            if template is not None and template.risk_tier < LEGEND_RISK_FLOOR_TIER:
                msg = (
                    f"LEGEND_POINTS reward requires risk_tier ≥ "
                    f"{LEGEND_RISK_FLOOR_TIER} (HIGH), got {template.risk_tier}. "
                    "Legend is earned in the company of others (#2051)."
                )
                raise ValidationError({"sink": msg})

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is None and self.sequence == 0:
            parent_field, parent_id = (
                ("route", self.route_id)
                if self.route_id is not None
                else ("candidate", self.candidate_id)
            )
            max_seq = MissionOptionRouteReward.objects.filter(
                **{parent_field: parent_id}
            ).aggregate(models.Max("sequence"))["sequence__max"]
            self.sequence = (max_seq or 0) + 1
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        scope = "holder" if self.contract_holder_only else "broadcast"
        return f"{self.get_kind_display()}/{self.get_sink_display()} ({scope})"

    def _parent_template(self) -> "MissionTemplate | None":
        """Walk the FK chain to the owning MissionTemplate.

        Returns None if the route/option/node chain is incomplete (e.g. the
        reward was created before its parent route was fully wired).
        """
        route = self.route
        if route is None and self.candidate_id is not None:
            route = self.candidate.route if self.candidate_id else None
        if route is None or route.option_id is None:
            return None
        option = route.option
        if option is None or option.node_id is None:
            return None
        return option.node.template


class MissionRenownAward(NaturalKeyMixin, SharedMemoryModel):
    """Authored Renown award bundle attached to a route OR a route candidate.

    Parallel to ``MissionOptionRouteReward`` (which handles flat money /
    legend-points / etc. distributions) — Renown awards are bundled and
    multi-dimensional (Magnitude + Risk + Archetypes + optional Reach
    override), and on terminal route resolution fire through the renown
    event service to write into Persona / Org / Society / Legend state.

    Phase B authoring lands the model; emit-on-terminal wiring is part of
    Phase B's mission integration. Default propagation: contract-holder-only
    (renown bundles typically award the persona who actually owned the
    deed, not every participant equally — bystanders may witness via
    awareness but don't earn the persona-side prestige).
    """

    route = models.ForeignKey(
        _MISSION_OPTION_ROUTE_MODEL,
        on_delete=models.CASCADE,
        related_name="renown_awards",
    )
    magnitude = models.CharField(
        max_length=16,
        blank=True,
        choices=RenownMagnitude.choices,
        help_text=(
            "Drives fame buffer + prestige-from-deeds. Blank = no fame/"
            "prestige delta (e.g., a Risk-only secret-deed award)."
        ),
    )
    risk = models.CharField(
        max_length=16,
        blank=True,
        choices=RenownRisk.choices,
        default=RenownRisk.NONE,
        help_text=(
            "Drives legend. NONE / blank = no legend awarded — e.g., a "
            "royal wedding has high Magnitude and None Risk."
        ),
    )
    reach_override = models.CharField(
        max_length=16,
        blank=True,
        choices=RenownReach.choices,
        help_text=(
            "Reach override. Blank = derive from Magnitude per "
            "MAGNITUDE_TO_DEFAULT_REACH (Small→LOCAL, Moderate→REGIONAL, "
            "High→CONTINENTAL, Very High→WORLD)."
        ),
    )
    archetypes = models.ManyToManyField(
        "societies.PhilosophicalArchetype",
        related_name="mission_awards",
        blank=True,
        help_text=(
            "Philosophical archetype tags. Their principle deltas sum, then "
            "dot-product against each affected society's principle values "
            "to produce that society's reputation delta. Blank = no "
            "reputation deltas fire (Magnitude-only or Risk-only event)."
        ),
    )
    contract_holder_only = models.BooleanField(
        default=True,
        help_text=(
            "True (default) → renown bundle awards only to the contract "
            "holder persona. False → broadcast per the template's "
            "reward_group_rule, same semantics as MissionOptionRouteReward."
        ),
    )
    sequence = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "NK discriminator only — same rationale as "
            "MissionOptionRouteReward.sequence: 0 is a pure 'unassigned' sentinel, "
            "never a stored value — save() assigns 1, 2, 3... per route when left "
            "at 0."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["route", "sequence"]
        dependencies = [_MISSION_OPTION_ROUTE_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["route", "sequence"], name="unique_renownaward_route_sequence"
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        # Deliberately does NOT call self.clean() — clean()'s legend-risk-floor
        # check is pre-existing validation that is not enforced on save() today
        # (only ever called explicitly in tests); adding that enforcement here
        # would be an unrelated behavior change, out of scope for #2470.
        if self.pk is None and self.sequence == 0:
            max_seq = MissionRenownAward.objects.filter(route_id=self.route_id).aggregate(
                models.Max("sequence")
            )["sequence__max"]
            self.sequence = (max_seq or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        mag = self.get_magnitude_display() if self.magnitude else "—"
        risk = self.get_risk_display() if self.risk else "—"
        return f"Renown(mag={mag}, risk={risk})"

    def clean(self) -> None:
        """Validate the legend risk floor (#2051).

        A MissionRenownAward whose ``risk`` pays legend (i.e. risk is HIGH or
        EXTREME — RISK_LEGEND_AWARDS > 0 and at the floor) requires the parent
        template's risk_tier ≥ LEGEND_RISK_FLOOR_TIER. Legend is earned in the
        company of others; a low-risk mission cannot pay legend.
        """
        super().clean()
        from world.societies.constants import RenownRisk  # noqa: PLC0415

        legend_paying = {RenownRisk.HIGH.value, RenownRisk.EXTREME.value}
        if self.risk not in legend_paying:
            return
        template = None
        if self.route_id is not None and self.route.option_id is not None:
            option = self.route.option
            if option is not None and option.node_id is not None:
                template = option.node.template
        if template is not None and template.risk_tier < LEGEND_RISK_FLOOR_TIER:
            msg = (
                f"RenownAward with legend-paying risk requires risk_tier ≥ "
                f"{LEGEND_RISK_FLOOR_TIER} (HIGH), got {template.risk_tier}. "
                "Legend is earned in the company of others (#2051)."
            )
            raise ValidationError({"risk": msg})


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
    spawned_room = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The instanced room this run spawned (#886), if any. INSTANCE-"
            "mode nodes gate their options to it; torn down at completion "
            "via complete_instanced_room."
        ),
    )
    anchor_room = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The room where this run was granted (#885): the trigger room, "
            "the offering NPC's room, or the character's location at staff "
            "assignment. ANCHOR-mode nodes gate their options to it — what "
            "keeps reusable templates location-flavored without authored "
            "rooms. Null = placeless grant; ANCHOR options never fire."
        ),
    )
    status = models.CharField(
        max_length=10,
        choices=MissionStatus.choices,
        default=MissionStatus.ACTIVE,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_paused = models.BooleanField(
        default=False,
        help_text=(
            "Set when a participant disconnects (#1899) — see maybe_pause_mission_for_disconnect."
        ),
    )
    # #1753 — the after-action report (RESOLVED → COMPLETE). Set when the player
    # reports the outcome to the report-to Functionary; the chosen style drives the
    # money / fame-prestige / resonance deltas.
    reported_at = models.DateTimeField(null=True, blank=True)
    report_style = models.CharField(
        max_length=20,
        choices=ReportStyle.choices,
        blank=True,
        default="",
        help_text="How the player reported this run's outcome (#1753). Blank until reported.",
    )
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
            "Optional: the stories Beat this run resolves. When set, the stakes "
            "contract locks at acceptance (activate_stakes_for_instance) and the "
            "Beat completes at terminal (on_mission_complete_for_beat). SET_NULL "
            "on Beat delete. For offer-issued runs, set from "
            "MissionOfferDetails.source_beat at issue_mission (#1780)."
        ),
    )
    # #686: the NPCServiceOffer that produced this instance (via the MISSION
    # effect handler). Null for legacy / trigger-based / staff-seeded runs.
    # Used to scope the CharacterSheet.max_active_npc_missions cap to
    # NPC-mediated runs only.
    source_offer = models.ForeignKey(
        "npc_services.NPCServiceOffer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The NPCServiceOffer this run was accepted from (#686). Null for "
            "trigger-based mission givers (room/item) and legacy seed rows. "
            "The PC-cap counts only rows with this set."
        ),
    )
    # #686 fix: the persona that accepted this run. Drives the per-(persona ×
    # role) one-in-flight gate in npc_services._mission_gates_pass — a
    # character's PRIMARY persona on a mission from a role does NOT block its
    # ESTABLISHED persona from the same role (those are different IC people).
    # Null for trigger-based / legacy seed rows; SET_NULL on Persona delete so
    # we keep the run record.
    accepted_as_persona = models.ForeignKey(
        _PERSONA_MODEL_PATH,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The persona the contract-holder presented when accepting this run "
            "(#686). Used by the per-(persona × role) one-in-flight gate. Null "
            "for trigger-based and legacy seed rows (which skip the gate)."
        ),
    )
    rescue_target = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The captive this run aims to free (#931 Phase 4 rescue). Resolves "
            "'where is the captive' through their cell; the success route frees "
            "them. Null for non-rescue runs."
        ),
    )
    target_project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Optional: the Project this run advances (#2045). Copied from "
            "MissionOfferDetails.target_project at issuance (mirrors source_beat). "
            "SET_NULL on Project delete — a cancelled project unbinds the run; "
            "report-time payout soft-skips with a notice."
        ),
    )

    def __str__(self) -> str:
        return f"{self.template.name} ({self.status})"


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
        OBJECT_DB_MODEL,
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


class MissionInvite(SharedMemoryModel):
    """An RSVP invitation to join a :class:`MissionInstance` (#887).

    Consent is opt-in participation, not a behavior-altering effect
    (ADR-0024), so this mirrors ``EventInvitation``'s
    PENDING/ACCEPTED/DECLINED RSVP rather than the ``SceneActionRequest``
    consent flow. On ACCEPT, the service calls the existing
    ``share_mission`` to add the invitee as a non-holder participant.
    """

    class Response(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    target_persona = models.ForeignKey(
        _PERSONA_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="mission_invites_received",
    )
    invited_by = models.ForeignKey(
        _PERSONA_MODEL_PATH,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mission_invites_sent",
    )
    response = models.CharField(
        max_length=10,
        choices=Response.choices,
        default=Response.PENDING,
        db_index=True,
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "target_persona"],
                name="unique_missioninvite_instance_target_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"invite {self.target_persona} -> {self.instance} ({self.response})"


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


class MissionGroupBallot(SharedMemoryModel):
    """One participant's pick + vote at a group (multi-participant) node (#1036).

    Backs the two-stage GROUP_VOTE flow. ``picked_option`` is the
    participant's own stage-1 choice (from their per-viewer option list);
    ``voted_option`` is their stage-2 vote for which *surfaced* option the
    party should commit to (any member may vote for any picked option).
    Resolution tallies the votes (plurality, random tiebreak), falling back
    to the picks when no vote was cast, then resolves the single winning
    option as a picker of it. Rows are ephemeral — cleared once the node
    resolves. ``created_at`` of the earliest ballot opens the vote window
    (see ``GROUP_VOTE_TIMEOUT_SECONDS``). One ballot per
    (instance, node, participant).
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="group_ballots",
    )
    node = models.ForeignKey(
        MissionNode,
        on_delete=models.CASCADE,
        related_name="+",
    )
    participant = models.ForeignKey(
        MissionParticipant,
        on_delete=models.CASCADE,
        related_name="group_ballots",
    )
    picked_option = models.ForeignKey(
        MissionOption,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The participant's own stage-1 pick (from their option list).",
    )
    picked_approach = models.ForeignKey(
        "mechanics.ChallengeApproach",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The ChallengeApproach the pick uses, when the option is CHALLENGE-sourced.",
    )
    voted_option = models.ForeignKey(
        MissionOption,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Stage-2 vote for a surfaced option; null until the participant votes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "node", "participant"],
                name="unique_groupballot_instance_node_participant",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"ballot {self.participant_id} @ node {self.node_id}: "
            f"pick={self.picked_option_id} vote={self.voted_option_id}"
        )


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
        OBJECT_DB_MODEL,
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
    route_candidate = models.ForeignKey(
        "missions.MissionOptionRouteCandidate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The random-set candidate that fired for this deed, if any (#941). "
            "Carries the per-candidate consequence / outcome_text / rewards the "
            "engine used; null for non-random routes and BRANCH deeds."
        ),
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    legend_entries = models.ManyToManyField(
        "societies.LegendEntry",
        blank=True,
        related_name="mission_deeds",
        help_text=(
            "Legend entries minted from this deed's terminal renown awards (#2047). "
            "Populated at the emit_terminal_renown_awards call sites from the returned "
            "RenownAwardResult.legend_entry_id values. Used to seed tale authors' "
            "LegendDeedStory rows when they tell the tale."
        ),
    )
    unseen_count = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Count of approaches that went unseen by the party at this "
            "node (moves no participant qualified for + regular options "
            "hidden from all). Set on the deed(s) minted at resolution. "
            "The journal reads it from deed history (#2046)."
        ),
    )

    def __str__(self) -> str:
        return f"deed {self.option} by {self.actor}"


class MissionAssistPattern(SharedMemoryModel):
    """Catalog row auto-offering support moves wherever context + qualifier match (#2046).

    Density without per-node authoring: active patterns whose context axes
    (check_types / challenge_categories) match the node's live CHECK options
    and whose qualifier (capability leg + optional predicate leg) passes
    for a participant are offered as support moves. Authored gems on specific
    nodes add to or suppress these patterns.
    """

    name = models.CharField(max_length=100, unique=True)
    capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assist_patterns",
        help_text="Capability leg: the participant must hold this capability (>0 effective value).",
    )
    qualifier_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate-tree leg (sanctioned AND/OR/NOT vocabulary). Optional; "
            "covers distinction/trait combos that aren't capabilities. Empty "
            "dict = no predicate gate."
        ),
    )
    check_types = models.ManyToManyField(
        "checks.CheckType",
        blank=True,
        related_name="assist_patterns",
        help_text="Context axis: match when the node has a CHECK option using any of these.",
    )
    challenge_categories = models.ManyToManyField(
        "mechanics.ChallengeCategory",
        blank=True,
        related_name="assist_patterns",
        help_text=(
            "Context axis: match when the node has a CHALLENGE option in any of these categories."
        ),
    )
    support_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The CheckType rolled when a helper declares this support move.",
    )
    difficulty = models.PositiveSmallIntegerField(
        default=5,
        help_text="Difficulty for the support move's check (retunable).",
    )
    easing = models.IntegerField(
        default=2,
        help_text="Bonus added to the resolving check on success (retunable, can be negative).",
    )
    complication_consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Consequence fired on the helper on a failed support check (null = nothing fires)."
        ),
    )
    flavor_template = models.CharField(
        max_length=200,
        blank=True,
        help_text="Flavor text shown to the helper. May reference the granting source name.",
    )
    rumor_text = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "When non-empty, the move is 'rumored' — everyone sees this tease even if unqualified."
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(capability__isnull=False) | ~models.Q(qualifier_rule={}),
                name="assist_pattern_at_least_one_qualifier_leg",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class MissionNodeSupportOption(SharedMemoryModel):
    """Authored gem — a per-node support move that adds to or suppresses patterns (#2046).

    When ``suppress_patterns`` is True, only this node's gems are offered
    (the pattern catalog is skipped for this node). Otherwise gems are
    offered in addition to matching patterns.
    """

    node = models.ForeignKey(
        MissionNode,
        on_delete=models.CASCADE,
        related_name="support_options",
    )
    capability = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Capability leg (optional when qualifier_rule covers it).",
    )
    qualifier_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Predicate-tree leg. Empty dict = no predicate gate.",
    )
    support_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The CheckType rolled when a helper declares this support move.",
    )
    difficulty = models.PositiveSmallIntegerField(default=5)
    easing = models.IntegerField(default=2)
    complication_consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    flavor_template = models.CharField(max_length=200, blank=True)
    rumor_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="When non-empty, the move is 'rumored' — everyone sees this tease.",
    )
    suppress_patterns = models.BooleanField(
        default=False,
        help_text="When True, only this node's gems are offered (skip the pattern catalog).",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(capability__isnull=False) | ~models.Q(qualifier_rule={}),
                name="node_support_option_at_least_one_qualifier_leg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.node}: {self.flavor_template or 'support gem'}"


class MissionSupportDeclaration(SharedMemoryModel):
    """A helper's support move declaration at a node entry (#2046).

    Takes the place of the helper's pick/vote in the group flow. One per
    helper per node entry (unique on snapshot — re-entry creates new
    snapshots, so declarations refresh). The helper rolls their own check;
    success banks easing, failure can fire a complication on the helper.
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="support_declarations",
    )
    snapshot = models.ForeignKey(
        MissionNodeSnapshot,
        on_delete=models.CASCADE,
        related_name="support_declaration",
        help_text="The helper's own snapshot row for this node entry.",
    )
    participant = models.ForeignKey(
        MissionParticipant,
        on_delete=models.CASCADE,
        related_name="support_declarations",
    )
    pattern = models.ForeignKey(
        MissionAssistPattern,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    support_option = models.ForeignKey(
        MissionNodeSupportOption,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    outcome = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Resolved outcome tier of the support check.",
    )
    easing_banked = models.IntegerField(
        default=0,
        help_text="Easing banked on success (0 on failure).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot"],
                name="unique_support_declaration_per_snapshot",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(pattern__isnull=False, support_option__isnull=True)
                    | models.Q(pattern__isnull=True, support_option__isnull=False)
                ),
                name="support_declaration_xor_pattern_option",
            ),
        ]

    def __str__(self) -> str:
        return f"support by {self.participant} @ {self.snapshot}"


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

    name = models.CharField(max_length=200, unique=True)
    giver_kind = models.CharField(
        max_length=20,
        choices=GiverKind.choices,
        default=GiverKind.ROOM_TRIGGER,
        help_text="How this giver reaches the player; selects the target's expected typeclass. "
        "ROOM_TRIGGER → Room; ENVIRONMENTAL_DETAIL → examinable item (auto-grants one); "
        "BOARD → examinable item that lists many postings (preview-then-take, #2044).",
    )
    target = models.ForeignKey(
        OBJECT_DB_MODEL,
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
    is_active = models.BooleanField(default=True)
    templates = models.ManyToManyField(
        "missions.MissionTemplate",
        blank=True,
        related_name="givers",
        help_text=(
            "The mission templates this trigger giver offers (#729). A flat draw "
            "pool — each template self-gates at draw time via its own "
            "availability_rule, so per-attachment overrides aren't needed (Option A)."
        ),
    )

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
        if self.giver_kind == GiverKind.ROOM_TRIGGER:
            if not target.is_typeclass(Room, exact=False):
                raise ValidationError(
                    {
                        "target": (
                            f"ROOM_TRIGGER-kind giver's target must be a Room-typeclass "
                            f"ObjectDB; got {target.typeclass_path}."
                        )
                    }
                )
        elif self.giver_kind in (GiverKind.ENVIRONMENTAL_DETAIL, GiverKind.BOARD):
            # An examinable detail / item / notice board — must NOT be a
            # Character, Room, or Exit. (Any other Object subclass is fair
            # game: weapons, books, props, room details, notice boards.)
            # BOARD shares the typeclass rule with ENVIRONMENTAL_DETAIL — a
            # board IS an examinable object whose examine renders postings
            # instead of auto-granting one (#2044).
            if (
                target.is_typeclass(Character, exact=False)
                or target.is_typeclass(Room, exact=False)
                or target.is_typeclass(Exit, exact=False)
            ):
                raise ValidationError(
                    {
                        "target": (
                            f"{self.giver_kind}-kind giver's target must be a "
                            f"non-Character/Room/Exit Object (an examinable item, "
                            f"detail, or notice board); got {target.typeclass_path}."
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
        ``MissionTemplate.visibility`` from ``RESTRICTED`` to ``OPEN``).
        Runtime enforcement in ``offer_missions`` is deferred until the
        Phase-D offering surface — today this property is consumed only by the
        authoring layer. NOT a ``cached_property`` — ``target`` is
        mutable and ``SharedMemoryModel`` keeps the instance long-lived;
        recomputing on access is the safe choice.
        """
        return self.target_id is not None

    def __str__(self) -> str:
        return self.name


class MissionGiverCooldown(SharedMemoryModel):
    """Per-(giver, character) re-offer cooldown for trigger dispatch (#729).

    Mirrors ``npc_services.OfferCooldown``: a trigger giver fires on every
    qualifying room-entry / examine, so dispatch writes a cooldown row after a
    grant and skips the giver while ``available_at`` is in the future — the
    anti-nag guard so the same room doesn't hand out missions on every pass.
    """

    giver = models.ForeignKey(
        MissionGiver,
        on_delete=models.CASCADE,
        related_name="cooldowns",
    )
    # Character is an ObjectDB here to match MissionParticipant.character — the
    # missions app keys runtime participation on the Evennia object, not a Persona.
    character = models.ForeignKey(
        OBJECT_DB_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )
    available_at = models.DateTimeField(
        help_text="The giver won't re-dispatch to this character until this time."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["giver", "character"],
                name="unique_missiongivercooldown_giver_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.giver.name} → {self.character_id} until {self.available_at:%Y-%m-%d %H:%M}"


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
        OBJECT_DB_MODEL,
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
    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Set when sink=RESONANCE: which Resonance this line grants.",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Required when sink=ITEM: which ItemTemplate this reward grants.",
    )
    followon_offer = models.ForeignKey(
        "npc_services.NPCServiceOffer",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Mirrors the template's followon_offer (set when sink=FOLLOW_ON_SUMMONS).",
    )
    followon_message = models.TextField(
        blank=True,
        default="",
        help_text="Mirrors the template's followon_message.",
    )
    followon_expiry_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Mirrors the template's followon_expiry_hours.",
    )
    ref = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional reference/discriminator (e.g., a rumor key).",
    )
    project_contribution = models.ForeignKey(
        "projects.Contribution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Set when sink=PROJECT: the Contribution row this reward line "
            "created on the bound project (#2045). Provenance FK "
            "(specific→general per ADR-0010/0085). SET_NULL on Contribution delete."
        ),
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


class MissionRiskAcknowledgement(SharedMemoryModel):
    """A persona's on-record acknowledgement of a risky mission offer (#1770 PR4).

    The mission sibling of ``combat.EncounterRiskAcknowledgement``: recorded
    idempotently before accepting an offer whose template's ``risk_tier`` is
    at or above ``MISSION_RISK_ACK_TIER``; ``issue_mission`` refuses to
    create the run without one. Keyed on the offer (the thing accepted) and
    the accepting persona, mirroring the per-(persona x role) gates in
    npc_services. At most one row per (offer, persona); the tier is
    snapshotted at first acknowledgement.
    """

    offer = models.ForeignKey(
        "npc_services.NPCServiceOffer",
        on_delete=models.CASCADE,
        related_name="mission_risk_acknowledgements",
    )
    persona = models.ForeignKey(
        _PERSONA_MODEL_PATH,
        on_delete=models.CASCADE,
        related_name="mission_risk_acknowledgements",
    )
    acknowledged_risk_tier = models.PositiveSmallIntegerField(
        help_text="The template's risk_tier at acknowledgement time."
    )
    acknowledged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["acknowledged_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "persona"],
                name="unique_mission_risk_ack_per_offer_persona",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"persona {self.persona_id} acknowledged risk tier "
            f"{self.acknowledged_risk_tier} on offer {self.offer_id}"
        )


class MissionRunTale(SharedMemoryModel):
    """A player-authored epilogue for a completed mission run (#2047).

    One tale per participant per instance (unique constraint). Permissive by
    design — no content gate (see the permissive-canonicity policy in
    ``docs/systems/narrative.md``). On a legend-minting run, saving a tale
    seeds the author's ``LegendDeedStory`` for any unstoried ``LegendEntry``
    linked to the run's deeds (see ``services.play.save_run_tale``).
    """

    instance = models.ForeignKey(
        MissionInstance,
        on_delete=models.CASCADE,
        related_name="tales",
    )
    participant = models.ForeignKey(
        MissionParticipant,
        on_delete=models.CASCADE,
        related_name="tales",
    )
    text = models.TextField(
        help_text="The player-authored account of the run.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "participant"],
                name="unique_tale_per_participant_per_instance",
            ),
        ]

    def __str__(self) -> str:
        return f"Tale by {self.participant} on {self.instance}"
