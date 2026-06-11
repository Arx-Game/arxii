"""Reaction-window primitive (#904): windows + per-persona reactions.

A ReactionWindow attaches a reaction affordance to one scene Interaction
(an ENTRY pose, a told tale, a fashion display...). Present players react
at most once per window; the window's KIND (see
``world.scenes.constants.ReactionWindowKind``) supplies the choice
vocabulary and the effect handlers through the registry in
``world.scenes.reaction_services``. Windows live until the scene closes.

Kind-specific mechanical records (e.g. ``SceneEntryEndorsement``) are
*settlement targets* written by the kind's handlers — WindowReaction is the
generic social-surface record, deliberately thin.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.constants import ReactionWindowKind


class ReactionWindow(SharedMemoryModel):
    """A reaction affordance on one scene interaction, open until scene close.

    The ``interaction`` FK uses ``db_constraint=False`` because Interaction
    is partitioned by timestamp; the denormalized ``timestamp`` mirrors the
    InteractionReceiver / PoseEndorsement pattern for composite-FK use.
    """

    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.CASCADE,
        related_name="reaction_windows",
        db_constraint=False,
        help_text="The scene event being reacted to.",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction — required for composite FK "
        "with partitioned table",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="reaction_windows",
        help_text="Scene whose close settles this window.",
    )
    kind = models.CharField(
        max_length=32,
        choices=ReactionWindowKind.choices,
        help_text="Selects the choice vocabulary + effect handlers (registry).",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set by the scene-close sweep; a settled window is read-only.",
    )

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "kind"],
                name="unique_reaction_window_per_interaction_kind",
            ),
        ]

    def __str__(self) -> str:
        state = "settled" if self.settled_at else "open"
        return f"ReactionWindow({self.kind}, interaction={self.interaction_id}, {state})"

    @property
    def is_open(self) -> bool:
        return self.settled_at is None


class WindowReaction(SharedMemoryModel):
    """One persona's reaction to a window — at most one per (window, persona)."""

    window = models.ForeignKey(
        ReactionWindow,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    reactor_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="window_reactions",
        help_text="The IC face that reacted.",
    )
    choice = models.CharField(
        max_length=64,
        help_text="Slug from the kind's choices provider (e.g. a resonance id).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["window", "reactor_persona"],
                name="unique_window_reaction_per_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"WindowReaction({self.reactor_persona_id} -> {self.window_id}: {self.choice})"
