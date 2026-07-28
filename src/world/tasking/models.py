"""Tasking models — the dual-fulfillment job primitive (#2820 phase 1).

An `OrgTask` is a discrete, deadline-bearing job issued by an organization
against an authored `TaskTemplate`. Fulfillment is either an NPC agent (an
`assets.NPCAsset`, resolved offscreen by the game clock as a check with
tiered outcomes) or — once phase 5 lands — a PC running the template's
linked mission. Both paths grade into the same `TaskOutcomeRoute` table.

FK direction (ADR-0010): tasking points at missions, societies, assets,
checks, and traits; none of them import tasking.

Asset risk (ADR-0092): tasking never writes asset status. Templates carry an
optional `actions.ConsequencePool`; resolution routes risk through
`select_consequence_from_result` + `apply_resolution`, where `ASSET_STATUS`
effects do the transitioning.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.tasking.constants import TaskCategory, TaskStatus, TaskTargetKind

_PERSONA_FK = "scenes.Persona"


class TaskTemplateManager(NaturalKeyManager):
    pass


class TaskTemplate(NaturalKeyMixin, SharedMemoryModel):
    """An authored job definition: check, duration, target shape, payouts.

    `mission_template` present means PCs may fulfill instances as a mission
    (phase 5); absent means NPC-only (tax runs, collections). The
    `consequence_pool` is the ADR-0092 risk surface — its `ASSET_STATUS`
    effects are how a dispatched agent ever becomes COMPROMISED or LOST.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=20,
        choices=TaskCategory.choices,
        default=TaskCategory.GENERAL,
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="task_templates",
        help_text="Check both the handler (dispatch) and the agent (resolution) roll.",
    )
    check_difficulty = models.IntegerField(
        default=0,
        help_text="Target difficulty for both dispatch and resolution rolls.",
    )
    duration = models.DurationField(
        help_text="Real time from assignment to resolution by the game clock.",
    )
    target_kind = models.CharField(
        max_length=10,
        choices=TaskTargetKind.choices,
        default=TaskTargetKind.NONE,
        help_text="What kind of target instances of this template point at.",
    )
    eligibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text="Predicate tree gating who may issue/fulfill (NPCServiceOffer convention).",
    )
    mission_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_templates",
        help_text="Set = PCs may fulfill this as a mission (phase 5). Unset = NPC-only.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="task_templates",
        help_text="Risk pool applied on resolution (ADR-0092 — sole path to asset status).",
    )
    is_active = models.BooleanField(default=True)

    objects = TaskTemplateManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"TaskTemplate({self.name})"


class TaskOutcomeRoute(SharedMemoryModel):
    """Per-tier payout row for a template. No row for a tier = nothing happens.

    Mirrors `missions.MissionOptionRoute`'s outcome-tier keying so mission
    fulfillment (phase 5) grades into the same table.
    """

    template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.CASCADE,
        related_name="outcome_routes",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check outcome this route fires on.",
    )
    money_reward = models.PositiveIntegerField(
        default=0,
        help_text="Coppers delivered to the handler's purse on this tier.",
    )
    clue_pool = models.ForeignKey(
        "assets.CluePool",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Weighted clue draw granted to the handler on this tier.",
    )
    report_template = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Agent report prose; format kwargs {task}, {target}, {agent}. Blank = generic line."
        ),
    )
    # --- Spy Job Kit payouts (#2833). Each applies only when the task's
    # target kind matches; mismatches no-op with a report line. Fail closed.
    movements_report = models.BooleanField(
        default=False,
        help_text=(
            "PERSONA target: append the target's recent PUBLIC-room appearances "
            "(scene records, mechanical residue only — ADR-0175)."
        ),
    )
    unmask_target = models.BooleanField(
        default=False,
        help_text=(
            "PERSONA target: mint a PERSONA_LINK clue piercing the target's mask "
            "(no-op when they are their true face)."
        ),
    )
    gossip_heat_delta = models.SmallIntegerField(
        default=0,
        help_text=(
            "PERSONA target: heat applied to the hottest existing gossip about "
            "the target's secrets. Positive = whisper campaign, negative = quash. "
            "Never mints new secrets."
        ),
    )
    building_condition_delta = models.SmallIntegerField(
        default=0,
        help_text="ROOM target: shift the room's building condition tier (sabotage < 0).",
    )
    recruit_target = models.BooleanField(
        default=False,
        help_text=(
            "PERSONA target (NPCs only): the issuing org gains a held asset claim "
            "on the target — remote cultivation. No-op against player characters."
        ),
    )
    incriminate_level = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Residue (#2833): 1-4 mints a Secret about the HANDLER at this level "
            "('they arranged it') plus an investigable hub trail when the target "
            "room's region is derivable. Authors put it on sloppy tiers."
        ),
    )
    # --- Cross-system payouts (#2833 addendum): domain + org espionage.
    domain_report = models.BooleanField(
        default=False,
        help_text=(
            "DOMAIN target: report population/prosperity/unrest, holdings, and "
            "open crises — what a rival spymaster wants to know."
        ),
    )
    domain_unrest_delta = models.SmallIntegerField(
        default=0,
        help_text=(
            "DOMAIN target: foment (positive) or soothe (negative) unrest, "
            "feeding the existing weekly consumption/crisis machinery."
        ),
    )
    organization_report = models.BooleanField(
        default=False,
        help_text=(
            "ORG target: case the organization — member count, banded treasury, "
            "held agents, parent/wings. Never exact coin."
        ),
    )
    military_report = models.BooleanField(
        default=False,
        help_text=(
            "ORG target: assay their strength — the org's military units and "
            "active armies. Movements come when positional troop state exists."
        ),
    )

    class Meta:
        ordering = ["template", "outcome_tier"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "outcome_tier"],
                name="unique_task_outcome_route_per_tier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template.name} -> {self.outcome_tier.name}"


class OrgTask(SharedMemoryModel, DiscriminatorMixin):
    """A live job instance issued by an org against a template.

    Deadline-bearing and always terminal: standing postings are
    `npc_services.NPCAssignment` rows, never tasks.
    """

    template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    org = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="org_tasks",
        help_text="The issuing organization.",
    )
    issued_by = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="org_tasks_issued",
        help_text="The persona who issued the task (audit trail).",
    )
    status = models.CharField(
        max_length=10,
        choices=TaskStatus.choices,
        default=TaskStatus.OPEN,
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Resolution moment; set at assignment (now + template.duration).",
    )
    target_kind = models.CharField(
        max_length=10,
        choices=TaskTargetKind.choices,
        default=TaskTargetKind.NONE,
    )
    target_room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    target_org = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="org_tasks_targeting",
    )
    target_domain = models.ForeignKey(
        "societies.Domain",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    target_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="org_tasks_targeting",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    DISCRIMINATOR_FIELD = "target_kind"
    DISCRIMINATOR_MAP = {
        TaskTargetKind.ROOM: "target_room",
        TaskTargetKind.ORG: "target_org",
        TaskTargetKind.DOMAIN: "target_domain",
        TaskTargetKind.PERSONA: "target_persona",
    }
    _TARGET_FIELDS = ("target_room", "target_org", "target_domain", "target_persona")

    def clean(self) -> None:
        """Validate the target discriminator.

        Kinds in DISCRIMINATOR_MAP: exactly the mapped FK set. NONE: all
        target FKs null (DiscriminatorMixin has no no-field kind, so NONE
        is validated here).
        """
        super().clean()
        if self.target_kind == TaskTargetKind.NONE:
            populated = [f for f in self._TARGET_FIELDS if getattr(self, f"{f}_id") is not None]
            if populated:
                msg = f"target_kind=NONE forbids target FKs; got {', '.join(populated)}."
                raise ValidationError({"target_kind": msg})
            return
        errors = self._validate_discriminator(self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP)
        if errors:
            raise ValidationError(errors)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["org", "status"]),
        ]

    def __str__(self) -> str:
        return f"OrgTask(#{self.pk}, {self.template.name}, {self.status})"


class ListenerPost(SharedMemoryModel):
    """The buzz/harvest sidecar on a LISTENER assignment (#2820 phase 3).

    The standing primitive stays `npc_services.NPCAssignment` (postings
    persist until recalled; tasks always end) — this row carries the spy
    semantics: the buzz meter, its threshold, and the sweep marker. Buzz
    accrues ONLY from mechanical residue (scenes, minted secrets) in the
    posted room; prose is never an input.
    """

    assignment = models.OneToOneField(
        "npc_services.NPCAssignment",
        on_delete=models.CASCADE,
        related_name="listener_post",
        help_text="The LISTENER-role assignment this post decorates.",
    )
    handler = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="listener_posts_handled",
        help_text="The persona who collects — physically, in the room.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="The listener's weekly tradecraft roll. NULL = flat accrual.",
    )
    check_difficulty = models.IntegerField(default=0)
    buzz = models.IntegerField(
        default=0,
        help_text="Accrued intel pressure. Crossing the threshold yields a harvest.",
    )
    threshold = models.PositiveIntegerField(
        default=100,
        help_text="Buzz needed per harvest (LISTENER_BUZZ_THRESHOLD default).",
    )
    last_sweep_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the weekly sweep last processed this post.",
    )
    # --- Counterplay state (#2820 phase 4). NEVER serialized to the handler:
    # a suppressed or flipped post must be indistinguishable from a quiet one.
    suppressed_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Intimidated into silence until this moment. Hidden from the board.",
    )
    flipped_controller = models.ForeignKey(
        _PERSONA_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flipped_listener_posts",
        help_text=(
            "The rival persona who truly controls this listener (double agent). "
            "The original handler's board shows nothing. Hidden."
        ),
    )
    pending_plant = models.ForeignKey(
        "clues.Clue",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "A red-herring clue (accusation-provenance secret) queued by the "
            "flip controller; the next harvest delivers it. Hidden."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ListenerPost(#{self.pk}, room {self.assignment.room_id})"


class ListenerHarvest(SharedMemoryModel):
    """One threshold-crossing's catch, awaiting physical collection.

    ``secret`` present = the post caught a real record (a scene-anchored
    Secret minted in the room); absent = a quiet-week rumor, flavor only.
    Collection grants the handler an AUTOMATIC clue targeting the secret.
    """

    post = models.ForeignKey(
        ListenerPost,
        on_delete=models.CASCADE,
        related_name="harvests",
    )
    secret = models.ForeignKey(
        "secrets.Secret",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="The caught record. NULL = nothing real happened that cycle.",
    )
    planted_clue = models.ForeignKey(
        "clues.Clue",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "A flip controller's red herring delivered instead of a real catch "
            "(#2820 phase 4). Collection grants this clue as if it were real."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"ListenerHarvest(#{self.pk}, post #{self.post_id})"


class TaskFulfillment(SharedMemoryModel):
    """Who is doing a task, and how it resolved.

    NPC path: `npc_asset` + the handler's stored dispatch check. PC path
    (phase 5): `mission_instance`. Exactly one of the two is set.
    """

    task = models.ForeignKey(
        OrgTask,
        on_delete=models.CASCADE,
        related_name="fulfillments",
    )
    npc_asset = models.ForeignKey(
        "assets.NPCAsset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="task_fulfillments",
        help_text="The dispatched agent (NPC path).",
    )
    mission_instance = models.ForeignKey(
        "missions.MissionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_fulfillments",
        help_text="The PC mission run fulfilling this task (phase 5).",
    )
    handler = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="task_fulfillments_handled",
        help_text="The persona running the job: rolls dispatch, collects results.",
    )
    handler_check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Stored outcome of the handler's dispatch check (NPC path).",
    )
    handler_margin = models.IntegerField(
        default=0,
        help_text="Modifier the dispatch check contributes to the agent's resolution roll.",
    )
    resolved_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Outcome of the resolution roll. Null until resolved.",
    )
    report = models.TextField(
        blank=True,
        default="",
        help_text="The agent's report, readable by the handler once resolved.",
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def clean(self) -> None:
        """Exactly one fulfillment source: npc_asset XOR mission_instance."""
        super().clean()
        has_npc = self.npc_asset_id is not None
        has_mission = self.mission_instance_id is not None
        if has_npc == has_mission:
            msg = "Exactly one of npc_asset or mission_instance must be set."
            raise ValidationError({"npc_asset": msg})

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task"],
                condition=models.Q(is_active=True),
                name="unique_active_fulfillment_per_task",
            ),
        ]

    def __str__(self) -> str:
        return f"TaskFulfillment(task #{self.task_id}, handler {self.handler_id})"
