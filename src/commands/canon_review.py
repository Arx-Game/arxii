"""Telnet ``canonreview`` command (#2003) — staff canon-review queue surface.

Thin layer over ``world.stories.services.canon_review`` (the same service the
web ``CanonReviewViewSet`` calls). Staff-only (``perm(Admin)``). Subverbs:

- ``canonreview list`` — pending reviews (oldest first).
- ``canonreview clear <id> [notes=...]`` — approve a PENDING review.
- ``canonreview changes <id> notes=...`` — send a review back with notes.

No business logic in the command — authorization is replicated inline to match
the API's ``IsAdminUser`` exactly, never looser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags

if TYPE_CHECKING:
    from world.stories.models import CanonReview

_USAGE = (
    "Usage:\n"
    "  canonreview list                       — pending reviews (oldest first)\n"
    "  canonreview clear <id> [notes=<text>]   — approve a pending review\n"
    "  canonreview changes <id> notes=<text>   — request changes with notes"
)
_CHANGES_USAGE = "Usage: canonreview changes <id> notes=<text>"
_MULTIWORD_KEYS = frozenset({"notes"})


class CmdCanonReview(ArxCommand):
    """Staff canon-review queue (#2003).

    Usage:
      canonreview list
      canonreview clear <id> [notes=<text>]
      canonreview changes <id> notes=<text>
    """

    key = "canonreview"
    aliases = ("canonreviews",)
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        """Route by leading subverb (CommandError surfaces as a player message)."""
        raw = (self.args or "").strip()
        if not raw:
            self.msg(_USAGE)
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        try:
            if subverb == "list":  # noqa: STRING_LITERAL
                self._handle_list()
            elif subverb == "clear":  # noqa: STRING_LITERAL
                self._handle_clear(rest)
            elif subverb == "changes":  # noqa: STRING_LITERAL
                self._handle_changes(rest)
            else:
                raise CommandError(_USAGE)
        except CommandError as err:
            self.msg(str(err))

    def _handle_list(self) -> None:
        """List pending canon reviews (oldest first)."""
        from world.stories.services.canon_review import pending_canon_reviews  # noqa: PLC0415

        reviews = list(pending_canon_reviews())
        if not reviews:
            self.msg("No pending canon reviews.")
            return
        lines = [
            f"  [{review.pk}] {review.story.title} — tier {review.tier} (status {review.status})"
            for review in reviews
        ]
        lines.insert(0, "Pending canon reviews:")
        self.msg("\n".join(lines))

    def _handle_clear(self, rest: str) -> None:
        """``clear <id> [notes=...]`` — approve a PENDING review."""
        from world.stories.services.canon_review import clear_canon_review  # noqa: PLC0415

        review, notes = self._parse_id_and_notes(rest, require_notes=False)
        updated = clear_canon_review(review, self.caller.account, notes=notes)
        self.msg(f"Canon review #{updated.pk} cleared for {updated.story.title}.")

    def _handle_changes(self, rest: str) -> None:
        """``changes <id> notes=<text>`` — send a review back with notes."""
        from world.stories.services.canon_review import request_changes  # noqa: PLC0415

        review, notes = self._parse_id_and_notes(rest, require_notes=True)
        updated = request_changes(review, self.caller.account, notes=notes)
        self.msg(f"Canon review #{updated.pk} returned with changes for {updated.story.title}.")

    def _parse_id_and_notes(self, rest: str, *, require_notes: bool) -> tuple[CanonReview, str]:
        """Parse ``<id> [notes=<text>]`` (notes runs free-text to end of input)."""
        from world.stories.models import CanonReview  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens or not tokens[0].isdigit():
            raise CommandError(_CHANGES_USAGE if require_notes else _USAGE)
        review_id = int(tokens[0])
        # Parse kv from the tail after the id (notes= may span multiple words).
        tail = tokens[1] if len(tokens) > 1 else ""
        kv, _flags = parse_kv_and_flags(
            tail, multiword_keys=_MULTIWORD_KEYS, known_flags=frozenset()
        )
        notes = kv.get("notes", "")
        if require_notes and not notes.strip():
            raise CommandError(_CHANGES_USAGE)
        try:
            review = CanonReview.objects.select_related("story").get(pk=review_id)
        except CanonReview.DoesNotExist:
            msg = f"No canon review #{review_id}."
            raise CommandError(msg) from None
        return review, notes
