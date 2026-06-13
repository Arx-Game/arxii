"""Captivity records (#931).

A ``Captivity`` is the state of one character being held: where (the cell
instance), by whom (the captor org), under what stakes (the off-screen-loss
flag set at the consent gate), and — once it exists — against what ransom.

Shared cells are the default: a party captured together points many
``Captivity`` rows at one ``InstancedRoom``. Separate linked cells off a
shared hallway are a deferred enhancement; nothing here forbids them, since
``cell`` is a plain FK, not one-per-room.

The captive's IC condition lives on ``CharacterSheet.lifecycle_state`` (it
flips to ``CAPTURED`` on capture and back to ``ALIVE`` on resolution). That
state already makes the character read as ``is_inactive`` everywhere, which
is what enforces the umbrella's off-screen-stasis ruling for captives — no
separate AP-freeze field is needed (there is no AP-regen cron to suppress,
and any future one must already skip inactive characters).
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.captivity.constants import CaptivityStatus


class Captivity(SharedMemoryModel):
    """One character's imprisonment and how it ends."""

    captive = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="captivities",
        help_text="The held character (the body, regardless of presented persona).",
    )
    cell = models.ForeignKey(
        "instances.InstancedRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captivities",
        help_text=(
            "The instanced cell this captive is held in (shared by a captured"
            " party). Goes null when the cell is torn down on resolution — a"
            " resolved captivity outlives its cell so its history survives."
        ),
    )
    captor_organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captives",
        help_text="The NPC org holding the captive and issuing any ransom demand.",
    )
    status = models.CharField(
        max_length=20,
        choices=CaptivityStatus.choices,
        default=CaptivityStatus.HELD,
    )
    offscreen_loss_allowed = models.BooleanField(
        default=False,
        help_text=(
            "Authored at the consent gate. Intended to gate off-screen loss"
            " (False = un-loseable while the player is away), but NO consumer"
            " reads it yet — escalation/loss logic that honours it is a later"
            " phase. Today it is a recorded intent only.  TODO(#931 followup)."
        ),
    )
    ransom_contract = models.ForeignKey(
        "currency.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ransom_captivities",
        help_text="The one-shot demand contract surfaced on the captor-debtor's books.",
    )
    captured_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the captivity ended. Null while HELD.",
    )

    class Meta:
        verbose_name = "Captivity"
        verbose_name_plural = "Captivities"
        ordering = ["-captured_at"]
        constraints = [
            # A character can hold at most one active captivity at a time.
            # Partial unique constraints already create their backing index,
            # so no separate Meta.indexes entry is needed here.
            models.UniqueConstraint(
                fields=["captive"],
                condition=models.Q(status=CaptivityStatus.HELD),
                name="unique_active_captivity_per_captive",
            ),
        ]

    def __str__(self) -> str:
        return f"Captivity({self.captive.character.key}: {self.get_status_display()})"
