"""Telnet consent preference management namespace (#1487)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef
    from world.roster.models import RosterTenure


_MSG_USAGE = (
    "Usage:\n"
    "  consent                          - show your consent settings\n"
    "  consent on|off                   - allow or block all social actions\n"
    "  consent category <key>=<mode>    - set a category to everyone|allowlist|default\n"
    "  consent whitelist add <name> to <category>\n"
    "  consent whitelist remove <name> from <category>\n"
    "  consent whitelist list [category]"
)

# Subverb -> registry action key. The "whitelist" subverb is resolved in func()
# once the second token (add/remove) is known; "list" is handled locally.
_SUBVERBS: dict[str, str] = {
    "on": "set_social_consent_preference",
    "off": "set_social_consent_preference",
    "category": "set_social_consent_category_rule",
}

_PLAYER_FACING_MODE_MAP = {
    "everyone": "everyone",
    "allowlist": "allowlist",
    "whitelist": "allowlist",
    "default": "default",
}


class CmdConsent(DispatchCommand):
    """Manage your social-consent preferences.

    Usage:
        consent                          - show your consent settings
        consent on|off                   - allow or block all social actions
        consent category <key>=<mode>    - set a category to everyone|allowlist|default
        consent whitelist add <name> to <category>
        consent whitelist remove <name> from <category>
        consent whitelist list [category]
    """

    key = "consent"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""
    _registry_key: str = ""

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_summary()
            return

        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""

        if self._subverb in _SUBVERBS:
            self._registry_key = _SUBVERBS[self._subverb]
            if self._subverb == "category" and "=" not in self._rest:  # noqa: STRING_LITERAL
                self.msg(_MSG_USAGE)
                return
        elif self._subverb == "whitelist":  # noqa: STRING_LITERAL
            if not self._handle_whitelist():
                return
        else:
            self.msg(_MSG_USAGE)
            return

        super().func()

    def resolve_action_ref(self) -> ActionRef:
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=self._registry_key)

    def resolve_action_args(self) -> dict[str, Any]:
        tenure = self._active_tenure()
        if self._registry_key == "set_social_consent_preference":  # noqa: STRING_LITERAL
            return {
                "tenure_id": tenure.pk,
                "allow_social_actions": self._subverb == "on",  # noqa: STRING_LITERAL
            }
        if self._registry_key == "set_social_consent_category_rule":  # noqa: STRING_LITERAL
            key, _, mode = self._rest.partition("=")
            return {
                "tenure_id": tenure.pk,
                "category_key": key.strip(),
                "mode": _PLAYER_FACING_MODE_MAP.get(mode.strip().lower(), mode.strip().lower()),
            }
        if self._registry_key in (
            "add_social_consent_whitelist",  # noqa: STRING_LITERAL
            "remove_social_consent_whitelist",  # noqa: STRING_LITERAL
        ):
            connector = "to" if self._registry_key == "add_social_consent_whitelist" else "from"  # noqa: STRING_LITERAL
            name, category_key = self._parse_whitelist_name_and_category(connector)
            target_tenure = self._resolve_target_tenure(name)
            return {
                "tenure_id": tenure.pk,
                "category_key": category_key,
                "allowed_tenure_id": target_tenure.pk,
            }
        _unknown_cmd_msg = "Unknown consent command."
        raise CommandError(_unknown_cmd_msg)

    # -----------------------------------------------------------------------
    # Parsing helpers
    # -----------------------------------------------------------------------

    def _handle_whitelist(self) -> bool:
        """Parse ``consent whitelist <op> ...``.

        Returns True when the command should continue to dispatch (add/remove).
        Returns False when the command has already produced output (list / error).
        """
        parts = self._rest.split(maxsplit=1)
        if not parts:
            self.msg(_MSG_USAGE)
            return False
        op = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if op == "list":  # noqa: STRING_LITERAL
            category_key = rest if rest else None
            self._show_summary(category_key)
            return False

        if op in ("add", "remove"):  # noqa: STRING_LITERAL
            self._registry_key = (
                "add_social_consent_whitelist" if op == "add" else "remove_social_consent_whitelist"  # noqa: STRING_LITERAL
            )
            self._rest = rest
            return True

        self.msg(_MSG_USAGE)
        return False

    def _parse_whitelist_name_and_category(self, connector: str) -> tuple[str, str]:
        """Parse ``<name> <connector> <category>`` from ``self._rest``.

        Raises CommandError with usage guidance on malformed input.
        """
        args = self._rest.strip()
        op = "add" if self._registry_key == "add_social_consent_whitelist" else "remove"  # noqa: STRING_LITERAL
        usage = f"Usage: consent whitelist {op} <name> {connector} <category>."
        if not args:
            raise CommandError(usage)
        match = re.match(
            rf"^(.+?)\s+{re.escape(connector)}\s+(.+)$",
            args,
            flags=re.IGNORECASE,
        )
        if not match:
            raise CommandError(usage)
        return match.group(1).strip(), match.group(2).strip()

    def _resolve_target_tenure(self, name: str) -> RosterTenure:
        """Look up a character in the caller's location and return their active tenure."""
        from world.roster.models import RosterTenure  # noqa: PLC0415

        target = self.search_or_raise(name)
        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            _no_identity_msg = f"{target} has no character identity."
            raise CommandError(_no_identity_msg)
        tenure = RosterTenure.objects.filter(
            roster_entry__character_sheet=sheet,
            end_date__isnull=True,
        ).first()
        if tenure is None:
            _no_tenure_msg = f"{target} has no active character tenure."
            raise CommandError(_no_tenure_msg)
        return tenure

    def _active_tenure(self) -> RosterTenure:
        """Return the caller's active RosterTenure."""
        from world.roster.models import RosterTenure  # noqa: PLC0415

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            _no_identity_msg = "You have no character identity."
            raise CommandError(_no_identity_msg)
        tenure = RosterTenure.objects.filter(
            roster_entry__character_sheet=sheet,
            end_date__isnull=True,
        ).first()
        if tenure is None:
            _no_tenure_msg = "You have no active character tenure."
            raise CommandError(_no_tenure_msg)
        return tenure

    # -----------------------------------------------------------------------
    # Summary display
    # -----------------------------------------------------------------------

    def _show_summary(self, category_key: str | None = None) -> None:
        """Render the caller's social-consent summary."""
        from world.consent.models import SocialConsentCategory  # noqa: PLC0415
        from world.consent.services import get_social_consent_summary  # noqa: PLC0415

        tenure = self._active_tenure()
        summary = get_social_consent_summary(tenure)
        lines: list[str] = ["|wConsent settings:|n"]

        pref = summary["preference"]
        master = "allowed" if pref is None or pref.allow_social_actions else "blocked"
        lines.append(f"  Social actions: {master}")

        rules = summary["rules"]
        if rules:
            lines.append("  |wCategory rules:|n")
            for rule in rules:
                display_mode = "whitelist" if rule.mode == "allowlist" else rule.mode  # noqa: STRING_LITERAL
                lines.append(f"    {rule.category.name}: {display_mode}")
        else:
            lines.append("  No per-category rules set (all categories use the global preference).")

        whitelist = summary["whitelist"]
        if category_key:
            try:
                category = SocialConsentCategory.objects.get_by_natural_key(category_key)
            except SocialConsentCategory.DoesNotExist:
                lines.append(f"  No category named '{category_key}'.")
                self.msg("\n".join(lines))
                return
            filtered = [entry for entry in whitelist if entry.category_id == category.pk]
            if filtered:
                lines.append(f"  |wWhitelist for {category.name}:|n")
                lines.extend(f"    {entry.allowed_tenure}" for entry in filtered)
            else:
                lines.append(f"  No whitelist entries for {category.name}.")
        elif whitelist:
            lines.append("  |wWhitelist entries:|n")
            lines.extend(
                f"    {entry.allowed_tenure} - {entry.category.name}" for entry in whitelist
            )
        else:
            lines.append("  No whitelist entries.")

        self.msg("\n".join(lines))
