"""A stylist's offer to restyle another character, waiting for that character's answer (#4187).

A cosmetic item used on another player's character is a question when the target's
makeover consent resolves to ``ConsentOutcome.ASK``: nothing is spent, this row is
written, and the target answers (web card, or telnet ``accept makeover`` /
``decline makeover``). A grant runs the ordinary ``use_item`` with this row as its
proof of consent; a decline spends nothing.

Not a ``SceneActionRequest``: that needs a scene and carries a contested-roll response
(plausibility band, resist effort) that means nothing for a haircut, and a makeover
happens in any room. Not a ``PrecaptureConsentRequest`` either: that is scene + account
scoped and holds no item or style. The row keeps the stylist's choices at offer time
(``option``, ``blend``, ``descriptor``) exactly as a direct use would pass them.

The item FK cascades on purpose: the kit gone means the ask gone. There is no timer; an
ask lapses lazily when the stylist is no longer in the target's room (checked whenever
the target's asks are listed or answered), and a newer ask from the same stylist
supersedes the old one, so at most one is pending per stylist/target pair.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.action_constants import ActionRequestStatus


class MakeoverConsentRequest(SharedMemoryModel):
    """One stylist's pending (or answered) offer to restyle one character."""

    stylist_persona = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.CASCADE,
        related_name="makeover_requests_made",
        help_text="The face the stylist is presenting; what the target sees on the ask.",
    )
    target_persona = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.CASCADE,
        related_name="makeover_requests_received",
        help_text="The character being asked, as the face they are presenting.",
    )
    item_instance = models.ForeignKey(
        "arxii.ItemInstance",
        on_delete=models.CASCADE,
        related_name="makeover_requests",
        help_text="The cosmetic item the stylist offered to use.",
    )
    option = models.ForeignKey(
        "arxii.FormTraitOption",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="The chosen style for a choose-at-use item; null for a fixed-option one.",
    )
    blend = models.BooleanField(
        default=False, help_text="Add the color instead of replacing it (#2632)."
    )
    descriptor = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Free-text presentation flavor the stylist chose (#2632).",
    )
    status = models.CharField(
        max_length=20,
        choices=ActionRequestStatus.choices,
        default=ActionRequestStatus.PENDING,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "Makeover Consent Request"
        verbose_name_plural = "Makeover Consent Requests"
        constraints = [
            models.UniqueConstraint(
                fields=["stylist_persona", "target_persona"],
                condition=models.Q(status=ActionRequestStatus.PENDING),
                name="one_pending_makeover_ask_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"MakeoverConsentRequest({self.stylist_persona_id} -> "
            f"{self.target_persona_id}, {self.status})"
        )
