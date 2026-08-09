"""Pre-scene RP capture (#3069 sub-item 4).

On scene start, ``precapture_services.capture_prescene_interactions`` folds recent
unattached (``scene=None``) poses into the new scene: present authors get folded in
immediately, everyone else needs to opt in via a ``PrecaptureConsentRequest`` (this
module) before their content ever attaches. See ``precapture_services`` for the
capture/consent/truncate logic; this file only holds the consent-request row.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.action_constants import ActionRequestStatus


class PrecaptureConsentRequest(SharedMemoryModel):
    """Pending consent to fold a non-member's prior unattached poses into a scene.

    One row per (scene, account) — the ask is "may we capture your recent unattached
    poses into this scene", not one row per pose. ``status`` reuses
    ``ActionRequestStatus`` (the same three-state PENDING/ACCEPTED/DENIED vocabulary
    ``SceneActionRequest`` already uses in this app); ``RESOLVED``/``EXPIRED`` are never
    written here — there is no timeout sweep, because a stale ``PENDING`` row is
    harmless (nothing attaches until it flips to ``ACCEPTED``, so "declined or ignored"
    already reads identically as "stays unattached" per the #3069 ruling).

    ``account`` is the interaction's pinned ``writer_account`` (#1219 party identity),
    not a persona or character — the consent decision belongs to the *player*
    regardless of which face wrote the pose, and matches the field's own documented
    purpose ("party identity for private-content log visibility").
    """

    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.CASCADE,
        related_name="precapture_consent_requests",
        help_text="The scene asking to capture this account's prior unattached poses.",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The pinned writer_account whose unattached poses are pending capture.",
    )
    status = models.CharField(
        max_length=20,
        choices=ActionRequestStatus.choices,
        default=ActionRequestStatus.PENDING,
        db_index=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "account"],
                name="unique_precapture_consent_per_scene_account",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PrecaptureConsentRequest(scene={self.scene_id}, "
            f"account={self.account_id}, {self.status})"
        )
