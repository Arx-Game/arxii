"""GM trust-ladder telnet namespace (#2000, Task 7).

Thin over ``world.gm.services`` — the same ``promote_gm`` / ``gm_evidence_summary``
functions the web ``GMProfileViewSet.promote`` / ``GMProfileViewSet.evidence``
actions call. No business logic lives here.

Subverbs:
  gmtrust show [account]     — your own GM level + that level's caps; naming
                                another account requires staff.
  gmtrust evidence <account> — staff-only aggregate track record.
  gmtrust promote <account>=<level> reason=<why>
                              — staff-only level change (promotion or demotion).
                                ``reason`` is required and may not be blank,
                                matching the web ``PromoteGMInputSerializer``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.gm.models import GMProfile
    from world.gm.types import GMEvidenceSummary

_USAGE = (
    "Usage: gmtrust <subcommand>\n"
    "  gmtrust show [account]              — your GM level + caps (staff may name another)\n"
    "  gmtrust evidence <account>          — staff: aggregate track record\n"
    "  gmtrust promote <account>=<level> reason=<why>\n"
    "                                       — staff: change a GM's trust level"
)
_STAFF_ONLY = "Only staff may do that."
_NOT_A_GM = "You are not a GM."
_NO_PROFILE = "That account has no GM profile."
_REASON_PREFIX = "reason="
_PROMOTE_USAGE = "Usage: gmtrust promote <account>=<level> reason=<why>."
_REASON_TOKEN_RE = re.compile(rf"(?i)\b{re.escape(_REASON_PREFIX)}")

_SUBVERB_HANDLERS: dict[str, str] = {
    "show": "_handle_show",
    "evidence": "_handle_evidence",
    "promote": "_handle_promote",
}


class CmdGMTrust(ArxNamespaceCommand):
    """View or change a GM's trust-ladder level (#2000).

    ``show`` is self-service (or staff viewing another account); ``evidence``
    and ``promote`` are staff-only.
    """

    key = "gmtrust"
    aliases = ()
    locks = "cmd:all()"
    _USAGE = _USAGE
    _SUBVERB_HANDLERS = _SUBVERB_HANDLERS

    # -- subverbs -------------------------------------------------------------

    def _handle_show(self, rest: str) -> None:
        """``gmtrust show [account]`` — own level+caps, or staff viewing another's."""
        target_token = rest.strip()
        if not target_token:
            profile = self._own_profile_or_none()
            if profile is None:
                self.msg(_NOT_A_GM)
                return
        else:
            if not bool(self.caller.account and self.caller.account.is_staff):
                raise CommandError(_STAFF_ONLY)
            target_account = self._resolve_account(target_token)
            profile = self._profile_or_error(target_account)
        self.msg(self._render_profile(profile))

    def _handle_evidence(self, rest: str) -> None:
        """``gmtrust evidence <account>`` — staff-only aggregate track record."""
        from world.gm.services import gm_evidence_summary  # noqa: PLC0415

        if not bool(self.caller.account and self.caller.account.is_staff):
            raise CommandError(_STAFF_ONLY)
        account_token = self._require_arg(rest, "Usage: gmtrust evidence <account>.")
        target_account = self._resolve_account(account_token)
        profile = self._profile_or_error(target_account)
        summary = gm_evidence_summary(profile)
        self.msg(self._render_evidence(target_account, summary))

    def _handle_promote(self, rest: str) -> None:
        """``gmtrust promote <account>=<level> reason=<why>`` — staff-only level change."""
        from world.gm.services import promote_gm  # noqa: PLC0415

        usage = _PROMOTE_USAGE
        if not bool(self.caller.account and self.caller.account.is_staff):
            raise CommandError(_STAFF_ONLY)

        if "=" not in rest:
            raise CommandError(usage)
        account_token, _, right = rest.partition("=")
        account_token = account_token.strip()
        right = right.strip()
        if not account_token or not right:
            raise CommandError(usage)

        # The remainder is "<level text> reason=<why>" where the level text may
        # itself be a multi-word label (e.g. "Junior GM"). Find the LAST
        # "reason=" token so a reason value that happens to contain "=" isn't
        # mistaken for another delimiter; everything before it is the level.
        matches = list(_REASON_TOKEN_RE.finditer(right))
        if not matches:
            raise CommandError(usage)
        last_match = matches[-1]
        level_token = right[: last_match.start()].strip()
        reason = right[last_match.end() :].strip()
        if not level_token or not reason:
            raise CommandError(usage)

        target_account = self._resolve_account(account_token)
        profile = self._profile_or_error(target_account)
        new_level = self._resolve_level_token(level_token)

        try:
            change = promote_gm(
                profile,
                new_level,
                changed_by=self.caller.account,
                reason=reason,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.msg(
            f"Changed {target_account.username}: "
            f"{change.get_old_level_display()} → {change.get_new_level_display()}."
        )

    # -- helpers ----------------------------------------------------------------

    def _own_profile_or_none(self) -> GMProfile | None:
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            return self.caller.account.gm_profile
        except GMProfile.DoesNotExist:
            return None

    def _resolve_account(self, token: str) -> AccountDB:
        from evennia.accounts.models import AccountDB  # noqa: PLC0415

        token = token.strip()
        account = AccountDB.objects.filter(username__iexact=token).first()
        if account is None:
            msg = f"No account named '{token}'."
            raise CommandError(msg)
        return account

    def _profile_or_error(self, account: AccountDB) -> GMProfile:
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            return account.gm_profile
        except GMProfile.DoesNotExist as exc:
            raise CommandError(_NO_PROFILE) from exc

    def _resolve_level_token(self, token: str) -> str:
        from world.gm.constants import GMLevel  # noqa: PLC0415

        token_lower = token.strip().lower()
        for value, label in GMLevel.choices:
            if token_lower == value.lower() or token_lower == label.lower():
                return value
        valid_levels = ", ".join(str(label) for label in GMLevel.labels)
        msg = f"Unknown GM level '{token}'. Valid levels: {valid_levels}."
        raise CommandError(msg)

    def _render_profile(self, profile: GMProfile) -> str:
        from world.gm.models import GMLevelCap  # noqa: PLC0415

        lines = [
            f"{profile.account.username}: {profile.get_level_display()}",
        ]
        cap = GMLevelCap.objects.filter(level=profile.level).first()
        if cap is None:
            lines.append("  (no level-cap data configured for this level)")
        else:
            lines.append(f"  Max beat risk: {cap.get_max_beat_risk_display()}")
            lines.append(f"  Custom stakes allowed: {cap.allow_custom_stakes}")
            lines.append(f"  Global-scope authoring allowed: {cap.allow_global_scope_authoring}")
        return "\n".join(lines)

    def _render_evidence(self, account: AccountDB, summary: GMEvidenceSummary) -> str:
        lines = [
            f"GM evidence for {account.username}:",
            f"  Level: {summary.level}",
            f"  GM since: {summary.approved_at}",
            f"  Last active: {summary.last_active_at if summary.last_active_at else 'never'}",
            f"  Stories running: {summary.stories_running}",
        ]
        if summary.beats_completed_by_risk:
            lines.append("  Beats completed by risk:")
            lines.extend(
                f"    {risk}: {count}" for risk, count in summary.beats_completed_by_risk.items()
            )
        else:
            lines.append("  Beats completed by risk: none")
        if summary.feedback_by_category:
            lines.append("  Feedback by category:")
            lines.extend(
                f"    {feedback.category_name}: {feedback.average_rating:.2f} "
                f"({feedback.rating_count} ratings)"
                for feedback in summary.feedback_by_category
            )
        else:
            lines.append("  Feedback by category: none")
        if summary.level_changes:
            lines.append("  Recent level changes:")
            lines.extend(
                f"    {change.get_old_level_display()} → {change.get_new_level_display()} "
                f"by {change.changed_by.username} — {change.reason}"
                for change in summary.level_changes
            )
        else:
            lines.append("  Recent level changes: none")
        return "\n".join(lines)
