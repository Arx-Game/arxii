"""Shared pull-keyword parsing mixin for telnet commands (#1919).

Extracted from ``_CombatCommandMixin`` so that both combat commands
(``cast``/``clash``) and consent commands (``persuade``/``intimidate``/…)
can reuse the same pull-parser without duplicating logic.

The ``beseech=`` token is a COVENANT_ROLE combat mechanic (#1718) and is
meaningless for social actions. It stays in ``_PULL_KWARG_KEYS`` so
``_extract_pull_keywords`` extracts and removes it from the remainder
(otherwise it would contaminate target-name resolution). Social commands
extract the ``beseech=`` value but discard it — ``_resolve_cast_pull`` is
called with ``beseech_bonus=0`` so no emergency draw fires, and
``_charge_social_pull`` also passes ``beseech_bonus=0`` as defense-in-depth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.magic.types.pull import CastPullDeclaration


# Keyword prefix used to parse effort=<level> from command args.
_EFFORT_PREFIX = "effort="
# Standalone keyword that declares the technique as a passive secondary action.
_SECONDARY_KEYWORD = "secondary"
# Standalone keyword that opts out of gift-technique variant resolution.
_BASE_KEYWORD = "base"
# Keyword prefixes used to parse fury=<tier> anchor=<name> from cast command args.
_FURY_PREFIX = "fury="
_ANCHOR_PREFIX = "anchor="


class PullParsingMixin:
    """Shared pull-keyword parsing for telnet commands.

    Provides ``_extract_pull_keywords`` and ``_resolve_cast_pull`` (plus
    related statics) so that any command that accepts ``pull=`` / ``resonance=``
    / ``tier=`` / ``beseech=`` tokens can reuse the same parser.
    """

    # Pull-kwarg prefixes recognised by _extract_pull_keywords.
    _PULL_KWARG_KEYS: frozenset[str] = frozenset({"pull", "resonance", "tier", "beseech"})

    # -- Pull-keyword parsing --------------------------------------------------

    @staticmethod
    def _is_pull_stop_token(tok: str, pull_keys: frozenset[str]) -> bool:
        """Return True when *tok* marks the start of a non-pull keyword boundary.

        Stops on any ``pull_keys``-prefixed token (``pull=``, ``resonance=``,
        ``tier=``), on ``effort=`` / ``secondary``, and on ``fury=`` / ``anchor=``
        (all handled elsewhere) so a greedy pull value never swallows them.
        """
        lower = tok.lower()
        return (
            any(lower.startswith(k + "=") for k in pull_keys)
            or lower.startswith((_EFFORT_PREFIX, _FURY_PREFIX, _ANCHOR_PREFIX))
            or lower in (_SECONDARY_KEYWORD, _BASE_KEYWORD)
        )

    @staticmethod
    def _greedy_consume(
        tokens: list[str],
        start: int,
        initial: str,
        pull_keys: frozenset[str],
    ) -> tuple[str, int, set[int]]:
        """Greedily extend *initial* with tokens from *start* until a stop boundary.

        Returns ``(value, next_index, consumed_indices)`` where *consumed_indices*
        are the token positions that were merged into *value*.
        """
        consumed: set[int] = set()
        j = start
        while j < len(tokens):
            if PullParsingMixin._is_pull_stop_token(tokens[j], pull_keys):
                break
            consumed.add(j)
            initial = initial + " " + tokens[j]
            j += 1
        return initial.strip(), j, consumed

    @staticmethod
    def _validate_pull_tier(tier_val: str | None) -> int:
        """Return the integer tier (default 1) and raise CommandError when invalid."""
        if tier_val is None:
            return 1
        if not tier_val.isdigit() or int(tier_val) not in (1, 2, 3):
            msg = f"Invalid tier '{tier_val}' — choose 1, 2, or 3."
            raise CommandError(msg)
        return int(tier_val)

    @staticmethod
    def _validate_pull_beseech(beseech_val: str | None) -> int:
        """Return the integer emergency-draw bonus (default 0); raise CommandError if invalid.

        Mirrors ``_validate_pull_tier``'s shape: a single optional non-negative
        int token. 0 (absent) means no emergency thread-bond draw was invoked (#1718).
        """
        if beseech_val is None:
            return 0
        if not beseech_val.isdigit():
            msg = f"Invalid beseech amount '{beseech_val}' — must be a non-negative integer."
            raise CommandError(msg)
        return int(beseech_val)

    @classmethod
    def _extract_pull_keywords(
        cls,
        raw: str,
    ) -> tuple[str, str | None, str | None, int, int]:
        """Extract pull=, resonance=, tier=, and beseech= tokens from *raw*.

        Each keyword's value is consumed greedily until the next known keyword
        prefix or end-of-string, so multi-word thread names (e.g. "Ember Strand")
        and comma-separated lists ("Strand A,Strand B") are captured intact.

        Raises:
            CommandError: If ``tier=`` is present but not 1–3, if ``beseech=``
                is present but not a non-negative integer, or if ``pull=`` is
                given without ``resonance=``.

        Returns:
            ``(remainder, pull_val, resonance_val, pull_tier, beseech_bonus)``
            where *remainder* is *raw* with all four keywords stripped out,
            *pull_tier* defaults to 1 when ``tier=`` is absent, and
            *beseech_bonus* defaults to 0 when ``beseech=`` is absent (#1718).
        """
        pull_keys = cls._PULL_KWARG_KEYS
        tokens = raw.split()
        pull_val: str | None = None
        resonance_val: str | None = None
        tier_val: str | None = None
        beseech_val: str | None = None
        skip_indices: set[int] = set()

        i = 0
        while i < len(tokens):
            lower_tok = tokens[i].lower()
            matched_key = next((k for k in pull_keys if lower_tok.startswith(k + "=")), None)
            if matched_key is None:
                i += 1
                continue

            skip_indices.add(i)
            initial = tokens[i][len(matched_key) + 1 :]  # strip "key="
            value, i, consumed = cls._greedy_consume(tokens, i + 1, initial, pull_keys)
            skip_indices.update(consumed)

            if matched_key == "pull":  # noqa: STRING_LITERAL
                pull_val = value or None
            elif matched_key == "resonance":  # noqa: STRING_LITERAL
                resonance_val = value or None
            elif matched_key == "tier":  # noqa: STRING_LITERAL
                tier_val = value or None
            else:
                beseech_val = value or None

        remainder = " ".join(t for idx, t in enumerate(tokens) if idx not in skip_indices)

        pull_tier = cls._validate_pull_tier(tier_val)
        beseech_bonus = cls._validate_pull_beseech(beseech_val)
        if pull_val is not None and resonance_val is None:
            msg = "pull= requires resonance=<name> to be specified as well."
            raise CommandError(msg)

        return remainder, pull_val, resonance_val, pull_tier, beseech_bonus

    def _resolve_cast_pull(
        self,
        pull_thread_str: str | None,
        pull_resonance_str: str | None,
        pull_tier: int,
        beseech_bonus: int = 0,
    ) -> CastPullDeclaration | None:
        """Return a ``CastPullDeclaration`` if *pull_thread_str* is set, else ``None``.

        Resolves threads by name/id owned by the caller's character sheet
        (same resonance, active only) and the resonance by name.

        Args:
            pull_thread_str: Comma-separated thread names/ids, or ``None``.
            pull_resonance_str: Resonance name string, or ``None``.
            pull_tier: Integer tier (1–3).
            beseech_bonus: Emergency thread-bond draw bonus (#1718); 0 means
                no emergency draw was invoked. Social commands always pass 0.

        Raises:
            CommandError: If resonance is unknown, any thread is not found /
                does not match the resonance / is retired, or pull= is present
                without resonance=.
        """
        if pull_thread_str is None:
            return None

        from world.magic.models import Resonance, Thread  # noqa: PLC0415
        from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

        resonance_val = (pull_resonance_str or "").strip()
        if not resonance_val:
            msg = "pull= requires resonance=<name> to be specified as well."
            raise CommandError(msg)

        resonance_qs = Resonance.objects.filter(name__iexact=resonance_val)
        resonance = resonance_qs.first()
        if resonance is None:
            msg = f"No resonance named '{resonance_val}' found."
            raise CommandError(msg)

        sheet = self.caller.sheet_data
        thread_vals = [t.strip() for t in pull_thread_str.split(",") if t.strip()]
        if not thread_vals:
            msg = "pull= requires at least one thread name or id."
            raise CommandError(msg)

        threads: list[Thread] = []
        for val in thread_vals:
            qs = Thread.objects.filter(owner=sheet, resonance=resonance, retired_at__isnull=True)
            if val.isdigit():
                thread = qs.filter(pk=int(val)).first()
            else:
                thread = qs.filter(name__iexact=val).first()
            if thread is None:
                msg = (
                    f"No active thread '{val}' found for resonance '{resonance_val}'. "
                    "Check that the thread exists, is active, and matches the resonance."
                )
                raise CommandError(msg)
            threads.append(thread)

        return CastPullDeclaration(
            resonance=resonance,
            tier=pull_tier,
            threads=tuple(threads),
            beseech_bonus=beseech_bonus,
        )
