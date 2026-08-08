"""Models for the guarded beta-reset wipe (#3055 PR 2).

See ``world/beta_reset/services.py`` for the full design writeup (hardcoded
constant + one-way release latch + provenance-filtered scope table) and
ADR-0207 for the one-paragraph rationale.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel


class ReleaseLatch(SharedMemoryModel):
    """Belt-and-suspenders one-way marker that early-access has shipped.

    A single row means "the beta reset command must never run again,
    independent of the ``BETA_RESET_ENABLED`` code constant." Written once by
    ``mark_released()``, which refuses if a row already exists — there is no
    "unmark" path, by design (a one-way latch, not a toggle). The wipe command
    checks ``ReleaseLatch.objects.exists()`` before doing anything else, so
    even a stale deploy that still has ``BETA_RESET_ENABLED = True`` baked in
    is stopped by the DB-side latch.
    """

    released_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the early-access cutover was marked released.",
    )
    released_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Staff account that flipped the latch. PROTECT: the account that made "
            "this irreversible call must never silently vanish from the audit trail."
        ),
    )
    note = models.TextField(
        blank=True,
        default="",
        help_text="Optional free-text context (e.g. cutover ticket link).",
    )

    class Meta:
        verbose_name = "Release Latch"
        verbose_name_plural = "Release Latch"

    def __str__(self) -> str:
        return f"ReleaseLatch(released_at={self.released_at.isoformat()})"
