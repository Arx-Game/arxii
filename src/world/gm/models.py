"""GM system models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager, CachedAllMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.gm.constants import (
    CatalogSuggestionProposalKind,
    GMApplicationStatus,
    GMLevel,
    GMTableStatus,
    TableRequestKind,
    TableRequestStatus,
)
from world.player_submissions.constants import SubmissionStatus
from world.scenes.action_constants import DifficultyChoice
from world.scenes.constants import PersonaType
from world.societies.constants import RenownRisk

if TYPE_CHECKING:
    from world.game_clock.models import GameWeek


class GMProfile(SharedMemoryModel):
    """A player's GM identity: their level, stats, and approval date.

    One per account. Created when a GMApplication is approved.
    The account FK is the anchor — GM level checks query this model.
    """

    account = models.OneToOneField(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="gm_profile",
    )
    level = models.CharField(
        max_length=20,
        choices=GMLevel.choices,
        default=GMLevel.STARTING,
        db_index=True,
    )
    approved_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this account was approved as a GM.",
    )
    approved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Staff account that approved the GM application.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    last_active_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stubbed — will be stamped by future story-update activity hooks.",
    )

    class Meta:
        verbose_name = "GM Profile"
        verbose_name_plural = "GM Profiles"

    def __str__(self) -> str:
        return f"GMProfile({self.account.username}, {self.get_level_display()})"


class GMApplication(SharedMemoryModel):
    """A player's application to become a GM.

    Freeform text field for the applicant to describe what they want to GM,
    which players they'd run for, and what stories they'd tell. Staff reviews
    and responds via staff_response. On approval, a GMProfile is created.
    """

    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="gm_applications",
    )
    application_text = models.TextField(
        help_text=(
            "Freeform: what the applicant wants to GM, who they'd run for, "
            "what stories they'd tell."
        ),
    )
    staff_response = models.TextField(
        blank=True,
        default="",
        help_text="Staff feedback on the application.",
    )
    status = models.CharField(
        max_length=20,
        choices=GMApplicationStatus.choices,
        default=GMApplicationStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Staff account that reviewed this application.",
    )

    class Meta:
        verbose_name = "GM Application"
        verbose_name_plural = "GM Applications"
        constraints = [
            UniqueConstraint(
                fields=["account"],
                condition=Q(status="pending"),
                name="unique_pending_gm_application_per_account",
            ),
        ]

    def __str__(self) -> str:
        return f"GMApplication({self.account.username}, {self.status})"


class GMTable(SharedMemoryModel):
    """A GM's working group — players engaging with a set of stories."""

    gm = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.PROTECT,
        related_name="tables",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=GMTableStatus.choices,
        default=GMTableStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "GM Table"
        verbose_name_plural = "GM Tables"

    def __str__(self) -> str:
        return f"GMTable({self.name}, gm={self.gm.account.username})"


class GMTableMembership(SharedMemoryModel):
    """A player's presence at a GM table, pinned to a specific persona.

    Anchors on Persona rather than CharacterSheet because:
    - The persona is the IC face other players see at the table
    - Pinning prevents drift when the player wears a temporary mask in scenes
    - Membership history can outlive a persona via soft-leave (left_at)

    Note: persona.character_sheet remains walkable, so this is NOT a
    privacy mechanism. Staff and any caller with ORM access can still
    derive the underlying character. Privacy is enforced at the
    serializer/view layer, not at the schema level.

    Soft-leave via left_at. The unique constraint ensures only one active
    membership per (table, persona) — historical (left) memberships can
    coexist with current ones.
    """

    table = models.ForeignKey(
        "gm.GMTable",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="gm_table_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "GM Table Membership"
        verbose_name_plural = "GM Table Memberships"
        constraints = [
            UniqueConstraint(
                fields=["table", "persona"],
                condition=Q(left_at__isnull=True),
                name="unique_active_gm_table_membership",
            ),
        ]

    def clean(self) -> None:
        if self.persona_id and self.persona.persona_type == PersonaType.TEMPORARY:
            msg = (
                "A temporary persona cannot join a GM table — use a primary or established persona."
            )
            raise ValidationError(msg)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Run full_clean() on save to enforce TEMPORARY persona rejection.

        The clean() method is otherwise only invoked during form validation,
        which would let direct ORM calls (``Model.objects.create()`` / raw
        ``.save()``) bypass the rule.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"GMTableMembership({self.table.name}, {self.persona.name})"


class GMRosterInvite(SharedMemoryModel):
    """A GM-generated invite to apply for a specific roster character.

    Single-use: once claimed, can't be reused. Expires after a configurable
    window (default 30 days, set by service). Public invites accept anyone
    with the code; private invites are scoped to a specific email (enforced
    at claim).
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="invites",
    )
    code = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.PROTECT,
        related_name="invites_created",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(
        help_text="Invite cannot be claimed after this time.",
    )
    is_public = models.BooleanField(
        default=False,
        help_text=(
            "If True, anyone with the code can claim. If False, only the invited_email may claim."
        ),
    )
    invited_email = models.EmailField(
        blank=True,
        default="",
        help_text="For private invites: the email expected to claim.",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "GM Roster Invite"
        verbose_name_plural = "GM Roster Invites"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"GMRosterInvite({self.code[:8]}… → {self.roster_entry_id})"

    @property
    def is_claimed(self) -> bool:
        return self.claimed_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return not self.is_claimed and not self.is_expired


class GMLevelCap(SharedMemoryModel):
    """Per-GM-level tuning: what a GM at this level is allowed to do.

    One row per ``GMLevel`` value (seeded via
    ``world.gm.factories.seed_default_gm_level_caps``). Staff-tunable in
    admin — these are designer knobs, not hardcoded gates.
    """

    level = models.CharField(
        max_length=20,
        choices=GMLevel.choices,
        unique=True,
        db_index=True,
    )
    max_beat_risk = models.CharField(
        max_length=20,
        choices=RenownRisk.choices,
        default=RenownRisk.NONE,
        help_text="Highest beat risk tier a GM at this level may author.",
    )
    allow_custom_stakes = models.BooleanField(
        default=False,
        help_text="Whether a GM at this level may author custom (template=null) stakes.",
    )
    allow_global_scope_authoring = models.BooleanField(
        default=False,
        help_text="Whether a GM at this level may author global-scope content.",
    )
    auto_clear_regional = models.BooleanField(
        default=False,
        help_text=(
            "Whether a GM at this level auto-clears REGIONAL impact-tier "
            "stories without a manual CanonReview (#2003)."
        ),
    )
    max_story_areas = models.PositiveIntegerField(
        default=0,
        help_text="Concurrent STORY-origin areas a GM at this level may own (#2450).",
    )
    max_story_rooms_per_area = models.PositiveIntegerField(
        default=0,
        help_text="Rooms a GM at this level may dig into one story area (#2450).",
    )

    class Meta:
        verbose_name = "GM Level Cap"
        verbose_name_plural = "GM Level Caps"
        ordering = ["level"]

    def __str__(self) -> str:
        return f"GMLevelCap({self.get_level_display()})"


class GMLevelChange(SharedMemoryModel):
    """Audit row for a staff-driven change to a GM's trust level.

    Written by ``world.gm.services.promote_gm`` — never edited by hand.
    """

    profile = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.CASCADE,
        related_name="level_changes",
    )
    old_level = models.CharField(max_length=20, choices=GMLevel.choices)
    new_level = models.CharField(max_length=20, choices=GMLevel.choices)
    changed_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Staff account that made this change.",
    )
    reason = models.TextField(help_text="Why the level changed — shown in the audit trail.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "GM Level Change"
        verbose_name_plural = "GM Level Changes"
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"GMLevelChange({self.profile.account.username}, {self.old_level}→{self.new_level})"


class StoryArea(SharedMemoryModel):
    """A GM's ownership claim on a STORY-origin Area (#2450, epic #2436 slice 3).

    Sidecar per ADR-0010 — ``areas`` stays dependency-free; the specific system
    (gm) points at the general primitive (Area). The row is kept after a staff
    promotion flips the area to AUTHORED (provenance); cap counting filters on
    ``area__origin=STORY`` so promoted areas stop counting automatically.
    """

    gm = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.PROTECT,
        related_name="story_areas",
    )
    area = models.OneToOneField(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="story_ownership",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Story Area"
        verbose_name_plural = "Story Areas"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"StoryArea({self.area.name}, gm={self.gm.account.username})"


class StoryRoomGrant(SharedMemoryModel):
    """Access grant letting a character join a GM's story room (#2450).

    Gates the JOIN action only — once inside, movement rides ordinary exits.
    ``return_location`` is captured at join time and cleared on leave. Revoke
    = row delete (a grant is not story-significant data). Works for both
    story-area rooms and temp scene rooms — both carry a RoomProfile.
    """

    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="story_grants",
    )
    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="story_room_grants",
    )
    granted_by = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.PROTECT,
        related_name="story_grants_issued",
    )
    return_location = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Where the character was when they joined; cleared on leave.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Story Room Grant"
        verbose_name_plural = "Story Room Grants"
        constraints = [
            UniqueConstraint(fields=["room", "character"], name="unique_story_room_grant"),
        ]

    def clean(self) -> None:
        if self.return_location_id is not None:
            loc = self.return_location
            if loc is None or not loc.is_typeclass("typeclasses.rooms.Room", exact=False):
                msg = "return_location must be a Room typeclass."
                raise ValidationError({"return_location": msg})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """full_clean() on save so direct ORM writes can't bypass clean()."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"StoryRoomGrant({self.character}, room={self.room_id})"


# --- GM scenario catalog (#2127, ADR-0110) ---------------------------------
#
# "Discovery, never invention", extended past ad-hoc checks (#2118) to the rest
# of the catalog: a cross-cutting SituationKind taxonomy other apps link *into*
# (never the reverse -- ADR-0010, this app depends on checks/mechanics/actions),
# plus the guidance rows a GM browses when adapting authored content. Every
# model here is admin-authored (ADR-0022); nothing on this file writes a live
# ``consequence_pool`` FK anywhere -- ConsequencePoolGuide is advisory text only.


class SituationKindManager(CachedAllMixin, NaturalKeyManager):
    """Manager for SituationKind with natural key support, plus cached_all() (#1871).

    Small, admin-authored taxonomy table read on every ``FindSituationAction``
    browse -- the same "cache the whole table forever" shape as
    ``ConsequencePoolManager``.
    """


class SituationKind(NaturalKeyMixin, SharedMemoryModel):
    """Cross-cutting scenario taxonomy tag ("Chase", "Negotiation", "Infiltration").

    Not a reuse of ``mechanics.ChallengeCategory`` or ``checks.CheckCategory`` --
    those are per-app display groupings that don't span situations/checks/
    encounters/missions. This is the shared tag that lets the same label surface
    consistent checks/difficulty/pool guidance across every per-type listing (the
    "translatable across contexts" requirement, Decision 1). Deliberately holds
    no FK to ``mechanics.SituationTemplate`` -- that would make ``mechanics``
    depend on ``gm``, backwards per ADR-0010; a ``FindSituationAction`` browse
    matches templates by name/description text and kinds by name independently,
    presenting both under the same search term.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    minimum_gm_level = models.CharField(
        max_length=20,
        choices=GMLevel.choices,
        default=GMLevel.STARTING,
        db_index=True,
        help_text=(
            "Lowest GM trust tier that may find/browse this kind (breadth gating, "
            "Decision 9) -- FindSituationAction filters server-side on this field."
        ),
    )

    objects = SituationKindManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Situation Kind"
        verbose_name_plural = "Situation Kinds"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CheckTypeSituationFit(SharedMemoryModel):
    """A ``checks.CheckType`` proven to fit a ``SituationKind`` (through model).

    The "translatable across contexts" record from Decision 1 -- the same check
    can be proven to fit more than one kind, and a kind lists every check proven
    to fit it, regardless of which app's per-type listing is browsing.
    """

    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        related_name="situation_fits",
    )
    situation_kind = models.ForeignKey(
        SituationKind,
        on_delete=models.CASCADE,
        related_name="check_fits",
    )
    fit_notes = models.TextField(
        blank=True,
        default="",
        help_text="Why this check fits this kind of scene -- shown in browse results.",
    )

    class Meta:
        verbose_name = "Check Type Situation Fit"
        verbose_name_plural = "Check Type Situation Fits"
        unique_together = ["check_type", "situation_kind"]
        ordering = ["situation_kind__name", "check_type__name"]

    def __str__(self) -> str:
        return f"{self.check_type.name} fits {self.situation_kind.name}"


class SituationDifficultyGuide(SharedMemoryModel):
    """Authored difficulty recommendation for a ``SituationKind`` at a given risk.

    Targets the live ``DifficultyChoice`` band surface a GM actually picks
    (#2118's ``InvokeCatalogCheckAction``), not ``ChallengeTemplate.severity``
    (a raw int baked into pre-authored Challenge content at authoring time,
    never touched by a live GM -- Decision 6).
    """

    situation_kind = models.ForeignKey(
        SituationKind,
        on_delete=models.CASCADE,
        related_name="difficulty_guides",
    )
    risk = models.CharField(max_length=20, choices=RenownRisk.choices)
    recommended_difficulty = models.CharField(max_length=20, choices=DifficultyChoice.choices)
    guidance_text = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Situation Difficulty Guide"
        verbose_name_plural = "Situation Difficulty Guides"
        unique_together = ["situation_kind", "risk"]
        ordering = ["situation_kind__name", "risk"]

    def __str__(self) -> str:
        return (
            f"{self.situation_kind.name} @ {self.get_risk_display()} -> "
            f"{self.get_recommended_difficulty_display()}"
        )


class ConsequencePoolGuide(SharedMemoryModel):
    """Advisory text on which ``ConsequencePool`` fits a ``SituationKind`` (Decision 7).

    ADVISORY ONLY -- nothing anywhere reads this row to select, compose, or
    write a live ``consequence_pool`` FK. Staff keeps authoring
    ``ActionTemplate.consequence_pool`` / ``ActionTemplateGate.consequence_pool``
    / ``SituationTrapLink.consequence_pool`` by hand in admin (ADR-0022); this
    model exists purely so a GM browsing a kind sees selection guidance text.
    """

    situation_kind = models.ForeignKey(
        SituationKind,
        on_delete=models.CASCADE,
        related_name="pool_guides",
    )
    pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.CASCADE,
        related_name="situation_guides",
    )
    selection_criteria = models.TextField(
        blank=True,
        default="",
        help_text="Guidance on when to pick this pool for this kind of scene.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the suggested default pool for this kind.",
    )

    class Meta:
        verbose_name = "Consequence Pool Guide"
        verbose_name_plural = "Consequence Pool Guides"
        unique_together = ["situation_kind", "pool"]
        ordering = ["situation_kind__name", "-is_default", "pool__name"]

    def __str__(self) -> str:
        return f"{self.situation_kind.name} -> {self.pool.name} (advisory)"


class CatalogSuggestion(SharedMemoryModel):
    """A GM's proposed catalog growth, routed through the staff inbox (#2127).

    Mirrors ``GMApplication``'s exact "GM submits -> staff triages from the
    shared inbox" shape (Decision 8): reuses ``player_submissions
    .SubmissionStatus`` (OPEN/REVIEWED/DISMISSED) rather than a new enum, and is
    mapped into ``world.staff_inbox`` alongside every other submission source.
    Staff acceptance is a manual admin action that separately authors the real
    catalog row(s) -- accepting a suggestion never auto-creates them (Decision
    7/8); this row is a proposal, never a live catalog write.
    """

    submitted_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="catalog_suggestions",
        help_text="OOC authoring, not IC -- mirrors GMApplication.account, not persona-anchored.",
    )
    situation_kind = models.ForeignKey(
        SituationKind,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestions",
        help_text="The kind this suggestion relates to, if any (e.g. a check-fit proposal).",
    )
    proposal_kind = models.CharField(
        max_length=20,
        choices=CatalogSuggestionProposalKind.choices,
    )
    proposal_text = models.TextField(help_text="Freeform: what the GM is proposing, and why.")
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )
    reviewer = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Staff account that reviewed this suggestion.",
    )
    review_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Catalog Suggestion"
        verbose_name_plural = "Catalog Suggestions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        kind_display = self.get_proposal_kind_display()
        return f"CatalogSuggestion({kind_display}, {self.submitted_by.username})"


class GMRewardConfig(SharedMemoryModel):
    """Singleton (pk=1) — tunable award values for the GM Story Reward (#2123).

    Every value that used to be a hardcoded module constant lives here instead,
    since these numbers will almost certainly require balance tuning: per-player
    XP + per-event cap for each of the three story-artifact award events (a
    GM-marked beat, a resolved episode, a completed story), the weekly ceiling
    per GM, and the per-rating-point XP for positive player story-feedback.
    Staff-editable in admin; ``world.gm.services.award_gm_story_reward`` and
    ``world.stories.services.feedback`` read this row, never a module constant.
    """

    objects = ArxSharedMemoryManager()

    beat_xp_per_player = models.PositiveIntegerField(
        default=6,
        help_text="XP per player served, awarded to the GM who marks a GM_MARKED beat.",
    )
    beat_xp_cap = models.PositiveIntegerField(
        default=48,
        help_text="Maximum XP a single beat-mark award may pay, before the weekly ceiling.",
    )
    episode_xp_per_player = models.PositiveIntegerField(
        default=15,
        help_text="XP per player served, awarded to the GM who resolves an episode.",
    )
    episode_xp_cap = models.PositiveIntegerField(
        default=120,
        help_text="Maximum XP a single episode-resolution award may pay, before the weekly cap.",
    )
    story_completion_xp_per_player = models.PositiveIntegerField(
        default=25,
        help_text="XP per player served, awarded to the GM whose table completes a story.",
    )
    story_completion_xp_cap = models.PositiveIntegerField(
        default=200,
        help_text="Maximum XP a single story-completion award may pay, before the weekly ceiling.",
    )
    weekly_reward_cap = models.PositiveIntegerField(
        default=300,
        help_text="Ceiling on total GM Story Reward XP (all event kinds combined) per GM per week.",
    )
    feedback_xp_per_rating_point = models.PositiveIntegerField(
        default=5,
        help_text=(
            "XP per positive rating point, awarded to the GM when a served participant's "
            "StoryFeedback on GM performance averages positive (rounded to the nearest "
            "whole rating point, 1..2)."
        ),
    )

    class Meta:
        verbose_name = "GM Reward Config"
        verbose_name_plural = "GM Reward Config"

    def __str__(self) -> str:
        return "GM Reward defaults"

    @classmethod
    def load(cls) -> GMRewardConfig:
        """Fetch (or lazily create) the singleton row."""
        obj = cls.objects.cached_singleton()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GMWeeklyRewardTracker(SharedMemoryModel):
    """Per-GM weekly GM Story Reward XP ledger (#2123).

    Mirrors ``world.journals.models.WeeklyJournalXP``'s get-or-reset-by-``GameWeek``
    shape: one row per GM, reset to zero whenever the tracked ``game_week`` no
    longer matches the current week. Bounds cross-event farming (e.g. marking
    many beats in one sitting) by the same ceiling regardless of which award
    event fired.
    """

    gm_profile = models.OneToOneField(
        "gm.GMProfile",
        on_delete=models.CASCADE,
        related_name="weekly_reward_tracker",
    )
    game_week = models.ForeignKey(
        "game_clock.GameWeek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gm_reward_trackers",
        help_text="GameWeek this counter belongs to.",
    )
    xp_awarded_this_week = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "GM Weekly Reward Tracker"
        verbose_name_plural = "GM Weekly Reward Trackers"

    def needs_reset(self, current_week: GameWeek) -> bool:
        """Check if this tracker is for a different game week."""
        return self.game_week_id != current_week.pk

    def reset_week(self, current_week: GameWeek) -> None:
        """Reset the weekly counter and set to the current game week."""
        self.xp_awarded_this_week = 0
        self.game_week = current_week
        self.save(update_fields=["xp_awarded_this_week", "game_week"])

    def __str__(self) -> str:
        username = self.gm_profile.account.username
        return f"GMWeeklyRewardTracker({username}: {self.xp_awarded_this_week})"


class TableUpdateRequest(SharedMemoryModel):
    """A player's proposed sheet change awaiting their table GM's sign-off (#2631).

    The structural firewall against the Arx-1 +request failure mode: the player
    proposes a CONCRETE change with their reasoning; the GM's job is a yes/no
    judgment call ("does this fit the story we told"), never authorship. Routed
    through ``GMTableMembership`` — joining a table is a GM taking
    responsibility for a player's story, so no table means no requests.

    Kind-specific payloads live on 1:1 details models (ADR-0007, no JSON):
    ``ProfileTextRequestDetails`` / ``DistinctionChangeRequestDetails``.
    """

    membership = models.ForeignKey(
        "gm.GMTableMembership",
        on_delete=models.PROTECT,
        related_name="update_requests",
        help_text="The table membership this request rides on.",
    )
    kind = models.CharField(max_length=30, choices=TableRequestKind.choices)
    player_reasoning = models.TextField(
        help_text="The player's Reason: — why the story supports this change.",
    )
    status = models.CharField(
        max_length=20,
        choices=TableRequestStatus.choices,
        default=TableRequestStatus.PENDING,
        db_index=True,
    )
    gm_notes = models.TextField(
        blank=True,
        default="",
        help_text="The GM's sign-off/rejection notes.",
    )
    resolved_by = models.ForeignKey(
        "gm.GMProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_update_requests",
        help_text="The GM who signed off or rejected.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "membership"])]
        verbose_name = "Table Update Request"
        verbose_name_plural = "Table Update Requests"

    def __str__(self) -> str:
        return f"TableUpdateRequest({self.get_kind_display()}, {self.status}, #{self.pk})"


class ProfileTextRequestDetails(SharedMemoryModel):
    """PROFILE_TEXT payload: a full-replacement rewrite of one prose field (#2631).

    Zero cost — prose changes apply at approval (no completion step; completion
    exists only to time an XP spend). ``applied_version`` links the history row
    the approval wrote, giving the version timeline its reasoning caption.
    """

    request = models.OneToOneField(
        TableUpdateRequest,
        on_delete=models.CASCADE,
        related_name="profile_text_details",
    )
    field = models.CharField(
        max_length=20,
        help_text="A character_sheets.ProfileTextField value.",
    )
    proposed_text = models.TextField(
        help_text="The full replacement text (player-written).",
    )
    applied_version = models.ForeignKey(
        "character_sheets.ProfileTextVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_by_request_details",
        help_text="The version row this request's approval created.",
    )

    class Meta:
        verbose_name = "Profile Text Request Details"
        verbose_name_plural = "Profile Text Request Details"

    def __str__(self) -> str:
        return f"ProfileTextRequestDetails({self.field}, request #{self.request_id})"


class DistinctionChangeRequestDetails(SharedMemoryModel):
    """DISTINCTION_CHANGE payload: a proposed add/rank-up/remove (#2631).

    Table-GM approval creates AND approves a ``distinctions.SheetUpdateRequest``
    through the #2628 framework — XP auto-debits atomically at approval (no
    separate player accept step), and this table request goes straight to
    COMPLETED. An ADD for a distinction the character already holds is a
    one-step rank-up (the #2628 framework's semantics).
    """

    request = models.OneToOneField(
        TableUpdateRequest,
        on_delete=models.CASCADE,
        related_name="distinction_details",
    )
    action = models.CharField(
        max_length=20,
        help_text="A distinctions.SheetUpdateRequestType value "
        "(distinction_add/distinction_remove).",
    )
    distinction = models.ForeignKey(
        "distinctions.Distinction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="table_update_request_details",
        help_text="The distinction to add/rank up (DISTINCTION_ADD only).",
    )
    character_distinction = models.ForeignKey(
        "distinctions.CharacterDistinction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="table_update_request_details",
        help_text="The held distinction to remove (DISTINCTION_REMOVE only; nulls after deletion).",
    )
    sheet_update_request = models.ForeignKey(
        "distinctions.SheetUpdateRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="table_update_request_details",
        help_text="The #2628 request created-and-approved at table sign-off.",
    )

    class Meta:
        verbose_name = "Distinction Change Request Details"
        verbose_name_plural = "Distinction Change Request Details"

    def __str__(self) -> str:
        return f"DistinctionChangeRequestDetails({self.action}, request #{self.request_id})"

    def clean(self) -> None:
        """Exactly one target, matching the action (mirrors the #2628 model)."""
        from world.distinctions.types import SheetUpdateRequestType  # noqa: PLC0415

        if self.action == SheetUpdateRequestType.DISTINCTION_ADD:
            if not self.distinction_id:
                msg = "DISTINCTION_ADD requires distinction."
                raise ValidationError(msg)
            if self.character_distinction_id:
                msg = "DISTINCTION_ADD must not set character_distinction."
                raise ValidationError(msg)
        elif self.action == SheetUpdateRequestType.DISTINCTION_REMOVE:
            if not self.character_distinction_id:
                msg = "DISTINCTION_REMOVE requires character_distinction."
                raise ValidationError(msg)
            if self.distinction_id:
                msg = "DISTINCTION_REMOVE must not set distinction."
                raise ValidationError(msg)
        else:
            msg = f"Unknown action: {self.action}"
            raise ValidationError(msg)
