"""Models for player-submitted items: feedback, bug reports, player reports."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.player_submissions.constants import SubmissionStatus


class PlayerFeedback(SharedMemoryModel):
    """General freeform feedback from a player about the game.

    Anchored on the submitter's active Persona so we can always derive
    the full identity chain (persona -> character -> tenure -> account).
    """

    reporter_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="feedback_submissions",
        help_text="The persona the submitter was wearing when they submitted.",
    )
    description = models.TextField(help_text="Freeform feedback text from the player.")
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

    reporter_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="bug_reports",
    )
    description = models.TextField(help_text="What the player observed.")
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

    reporter_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="reports_submitted",
        help_text="The persona the reporter was wearing when submitting.",
    )
    reported_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="reports_against",
        help_text="The persona of the reported player at the time of the incident.",
    )
    behavior_description = models.TextField(
        help_text="What the reported persona did. Stub — wording needs design pass.",
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
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The scene where the behavior occurred, if applicable.",
    )
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
        help_text="A specific flagged interaction, if applicable.",
    )
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
