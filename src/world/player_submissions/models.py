"""Models for player-submitted items: feedback, bug reports, player reports."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.player_submissions.constants import (
    PetitionCategory,
    ReportCategory,
    SubmissionStatus,
)

PERSONA_MODEL = "arxii.Persona"
SCENE_MODEL = "arxii.Scene"


class PlayerFeedback(SharedMemoryModel):
    """General freeform feedback from a player about the game.

    Stores both the submitter's account (the actionable unit for staff)
    and the persona they were wearing (for IC context).
    """

    reporter_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The account that submitted this.",
    )
    reporter_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="feedback_submissions",
        help_text="The persona the submitter was wearing when they submitted.",
    )
    description = models.TextField(help_text="Freeform feedback text from the player.")
    # ObjectDB by design (#2608): an audit stamp of raw `character.location` — no
    # Room typeclass guarantee, so no RoomProfile to point at.
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Room the submitter was in at the time, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]


class BugReport(SharedMemoryModel):
    """A bug report submitted by a player.

    Captures just a description plus location/timestamp context. Staff
    can follow up via the account history view if more info is needed.
    """

    reporter_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The account that submitted this.",
    )
    reporter_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="bug_reports",
    )
    description = models.TextField(help_text="What the player observed.")
    # ObjectDB by design (#2608): audit stamp of raw `character.location` (see
    # BugReport.location).
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )
    github_issue_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="GitHub issue number, once staff have filed one from this report (#1164).",
    )
    github_issue_url = models.URLField(
        blank=True,
        help_text="Link to the filed GitHub issue (empty until filed).",
    )

    class Meta:
        ordering = ["-created_at"]


class PlayerReport(SharedMemoryModel):
    """Stub: report of problematic behavior from another player.

    The full UX design (form wording, block/mute coupling, accessibility
    flow) is deferred to a later design pass. This stub establishes the
    data model so the infrastructure is in place.

    Identity anchoring: both reporter and reported are anchored on the
    Persona each was wearing at the time of the incident. Staff can
    derive account/tenure/character from each.

    See docs/roadmap/staff-inbox.md for full design notes.
    """

    reporter_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The account that submitted this.",
    )
    reported_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The account behind the reported persona at the time of the incident. "
            "Stored directly so staff can query by account without walking the "
            "persona chain."
        ),
    )
    reporter_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_submitted",
        help_text="The persona the reporter was wearing when submitting.",
    )
    reported_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="reports_against",
        help_text="The persona of the reported player at the time of the incident.",
    )
    behavior_description = models.TextField(
        help_text="What the reported persona did. Stub — wording needs design pass.",
    )
    category = models.CharField(
        max_length=20,
        choices=ReportCategory.choices,
        default=ReportCategory.HARASSMENT,
        help_text="Report category (#1279) — placeholder set, TBD.",
    )
    asked_to_stop = models.BooleanField(
        default=False,
        help_text="Whether the reporter asked the other player to stop the behavior.",
    )
    blocked_or_muted = models.BooleanField(
        default=False,
        help_text="Whether the reporter blocked or muted as a result.",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The scene where the behavior occurred, if applicable.",
    )
    interaction = models.ForeignKey(
        "arxii.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
        help_text="A specific flagged interaction, if applicable.",
    )
    # ObjectDB by design (#2608): audit stamp of raw `character.location` (see
    # BugReport.location).
    location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Room the reporter was in when submitting.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(reporter_persona=models.F("reported_persona")),
                name="player_report_reporter_not_reported",
            ),
        ]


class SystemErrorReport(SharedMemoryModel):
    """An auto-captured runtime error — the system filing its own report (#1164).

    Best-effort hooks (and other caught failures) report here via
    ``player_submissions.services.report_error``, so a real fault (a DB/connection error, a
    bug) reaches staff with a traceback instead of vanishing into the logs. Deduplicated by
    ``signature``: a recurring error is one row with an ``occurrence_count``, not spam.
    Reviewed in the staff inbox alongside player BugReports (``SubmissionCategory.SYSTEM_ERROR``).
    """

    signature = models.CharField(
        max_length=64,
        unique=True,
        help_text="Dedup hash (exception type + originating in-app frame).",
    )
    label = models.CharField(
        max_length=200,
        help_text="Where it happened (the hook / context label).",
    )
    exception_type = models.CharField(max_length=200)
    message = models.TextField(blank=True, help_text="The exception's message.")
    traceback = models.TextField(help_text="Full formatted traceback of the first occurrence.")
    actor_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The persona acting when first captured, if any.",
    )
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )
    github_issue_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="GitHub issue number, once staff have filed one from this report (#1164).",
    )
    github_issue_url = models.URLField(
        blank=True,
        help_text="Link to the filed GitHub issue (empty until filed).",
    )

    class Meta:
        ordering = ["-last_seen"]
        verbose_name = "System Error Report"
        verbose_name_plural = "System Error Reports"

    def __str__(self) -> str:
        return f"{self.exception_type} in {self.label} (x{self.occurrence_count})"


class Petition(SharedMemoryModel):
    """Emergency-only structured staff petition (#2288). No free-form queue.

    One OPEN petition per account — the structural rate-limit that keeps
    "emergency" legible. Frivolous petitions feed the same resolution track
    record as feedback (SubmitterStanding).
    """

    account = models.ForeignKey(
        "accounts.AccountDB", on_delete=models.CASCADE, related_name="petitions"
    )
    category = models.CharField(max_length=30, choices=PetitionCategory.choices)
    scene = models.ForeignKey(
        SCENE_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="petitions",
    )
    subject_character = models.ForeignKey(
        "arxii.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="petitions_about",
    )
    description = models.TextField(
        max_length=1000, help_text="Short and specific — this is an emergency line."
    )
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.OPEN,
        db_index=True,
    )
    staff_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(status="open"),
                name="one_open_petition_per_account",
            ),
        ]

    def __str__(self) -> str:
        return f"petition ({self.category}) by account {self.account_id}"


class CheckProposal(SharedMemoryModel):
    """A player's (or GM's) proposed new ``CheckType``, routed to the staff inbox (#3295).

    The catalog-only ruling (Tehom, 2026-08-21): every check anyone rolls is an
    authored ``CheckType`` -- never a freeform stat+skill+difficulty invention.
    When the catalog lacks a fitting check, a player proposes one instead of
    inventing it on the spot. This row is the proposal -- structured columns,
    no JSON -- never a live catalog write; staff adopt a proposal by authoring
    the real ``CheckType`` row through the normal content path and resolving
    this row separately (``reviewer``/``review_notes``/``resolved_at``), the
    same "propose, never auto-create" shape as ``world.gm.models
    .CatalogSuggestion`` (#2127).

    Deliberately has no FK to ``world.checks.models.CheckType`` -- there is no
    row to point at until (and unless) staff author one, and ``player_submissions``
    stays dependency-free of the checks app either way (ADR-0010 FK direction).
    """

    submitted_by_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="check_proposals",
        help_text="OOC authoring, not IC -- mirrors PlayerFeedback.reporter_account.",
    )
    submitted_by_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="check_proposals",
        help_text="The persona the submitter was wearing when proposing.",
    )
    proposed_name = models.CharField(
        max_length=100,
        help_text="The check's proposed name (e.g. 'Riverside Tracking').",
    )
    intent = models.TextField(
        help_text="What this check is meant to cover -- the gap in the catalog.",
    )
    suggested_traits_text = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Suggested stat+skill pairing in plain text (e.g. 'Perception + Survival'). "
            "Advisory only -- no live Trait FK exists until staff author the real row."
        ),
    )
    situation_text = models.TextField(
        help_text="The situation this check would serve -- when someone would roll it.",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="check_proposals",
        help_text="The scene the proposal arose in, if any.",
    )
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
        help_text="Staff account that reviewed this proposal.",
    )
    review_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Check Proposal"
        verbose_name_plural = "Check Proposals"

    def __str__(self) -> str:
        return f"CheckProposal({self.proposed_name!r} by {self.submitted_by_account.username})"


class SubmitterStanding(SharedMemoryModel):
    """Per-account staff-contact track record (#2288).

    Counters stamped when staff resolve feedback/petitions; ``is_ignored`` is
    the perma-ignore bit — submissions persist but never surface (silently).
    """

    account = models.OneToOneField(
        "accounts.AccountDB", on_delete=models.CASCADE, related_name="submitter_standing"
    )
    actioned_count = models.PositiveIntegerField(default=0)
    dismissed_count = models.PositiveIntegerField(default=0)
    ignored_count = models.PositiveIntegerField(default=0)
    is_ignored = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"standing for account {self.account_id}"
