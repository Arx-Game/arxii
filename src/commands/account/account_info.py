"""
Account information commands for ArxII.
"""

import re
from typing import ClassVar

from allauth.account.models import EmailAddress
from evennia import Command

# Minimal sanity check — full validation (deliverability, MX, etc.) is out of scope;
# allauth's own EmailAddress field validation runs on save.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SUBVERB_STATUS = "status"
_SUBVERB_EMAIL = "email"


class CmdAccount(Command):  # ty: ignore[invalid-base]
    """
    Show account information, or set/update your account email.

    Usage:
        @account
        account email <address>

    Bare ``@account``/``account`` shows your account information, preferences,
    and current session status (OOC account-level info, not character info).

    ``account email <address>`` sets your account's primary email address and
    (re)sends a verification link — the same allauth confirmation flow the web
    signup form uses. Telnet-registered accounts (``create <user> <pass>``
    collects no email) have no other way to satisfy the verified-email gate
    that character applications require (#2122).
    """

    key = "@account"
    aliases: ClassVar[list[str]] = ["account"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:
        """Route: bare → info display; ``email <address>`` → set/update email."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_info()
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if subverb == _SUBVERB_EMAIL:
            self._set_email(rest)
            return

        self.caller.msg(f"Unknown account command '{subverb}'. Try: email <address>.")

    def _show_info(self) -> None:
        """Display account information."""
        account = self.account
        player_data = account.player_data

        # Account header
        self.caller.msg(f"Account Information for {account.username}")
        self.caller.msg("=" * 50)

        # Basic info
        self.caller.msg(f"Display Name: {player_data.display_name}")
        self.caller.msg(f"Email: {account.email}")
        self.caller.msg(f"Last Login: {account.last_login}")
        self.caller.msg(f"Account Created: {account.date_created}")

        # Session info
        sessions = account.sessions.all()
        self.caller.msg(f"\nActive Sessions: {len(sessions)}")

        for i, session in enumerate(sessions, 1):
            puppet_info = f" (controlling {session.puppet.name})" if session.puppet else " (OOC)"
            self.caller.msg(f"  Session {i}: {session.protocol_key}{puppet_info}")

        # Character access
        available_chars = account.get_available_characters()
        puppeted_chars = account.get_puppeted_characters()

        self.caller.msg(f"\nCharacter Access: {len(available_chars)} character(s)")
        if available_chars:
            for char in available_chars:
                status = " (currently playing)" if char in puppeted_chars else ""
                self.caller.msg(f"  {char.name}{status}")

        # Preferences
        self.caller.msg("\nPreferences:")
        self.caller.msg(f"  Hide from watch lists: {player_data.hide_from_watch}")
        self.caller.msg(f"  Private mode: {player_data.private_mode}")

        # Staff info (if staff)
        if account.is_staff:
            self.caller.msg("\nStaff Information:")
            self.caller.msg(f"  Karma: {player_data.karma}")
            if player_data.gm_notes:
                self.caller.msg(f"  GM Notes: {player_data.gm_notes}")
            else:
                self.caller.msg("  GM Notes: None")

    def _set_email(self, address: str) -> None:
        """Set/update the account's primary email and send a confirmation link.

        Operates on ``self.account`` only — there is no target-account argument,
        so a caller can never touch another account's email (#2122 leak analysis).

        allauth API note (resolved at implementation time — allauth 65.14.1
        installed here): the higher-level ``EmailAddress.objects.add_email(request,
        ...)`` / ``send_verification_email_to_address`` path additionally calls
        ``django.contrib.messages.add_message(request, ...)``, which requires a
        real ``HttpRequest`` with message-storage middleware attached and raises
        ``TypeError`` when ``request`` is ``None`` outside an HTTP request/response
        cycle (this project has ``django.contrib.messages`` installed, via
        Evennia's default settings). We therefore call the lower-level
        ``EmailAddress.set_as_primary()`` + ``EmailAddress.send_confirmation()``
        directly — the same model API the higher-level helper delegates to for
        actually sending the mail, minus the messages-framework side effect
        (irrelevant here; this command sends its own telnet confirmation line).
        ``send_confirmation(request=None, ...)`` is itself a documented, supported
        call shape (see ``DefaultAccountAdapter.get_email_confirmation_url``'s
        docstring: confirmations sent outside a request context may pass
        ``request=None``) and is safe here because ``HEADLESS_FRONTEND_URLS`` /
        ``settings.FRONTEND_URL`` is always an absolute URL, so allauth's
        ``render_url`` never dereferences ``request.build_absolute_uri``.
        """
        address = address.strip()
        if not address or not _EMAIL_RE.match(address):
            self.caller.msg(f"'{address}' doesn't look like a valid email address.")
            return

        address = address.lower()
        account = self.account
        email_address, _created = EmailAddress.objects.get_or_create(
            user=account,
            email=address,
            defaults={"email": address},
        )
        email_address.set_as_primary()

        if email_address.verified:
            self.caller.msg(f"Your account email is already set and verified: {address}")
            return

        email_address.send_confirmation(request=None, signup=False)
        self.caller.msg(
            f"Account email set to {address}. A verification link has been sent — "
            "verify it to unlock character applications.",
        )


class CmdRoster(Command):  # ty: ignore[invalid-base]
    """
    Check your own pending roster application(s).

    Usage:
        roster
        roster status

    Shows the status of applications you've already submitted. Roster
    browsing and applying for new characters happens on the website
    (see the connection screen or ``@account`` for the URL) — this
    command is a read-only status check, not a browse/apply surface
    (#2122).
    """

    key = "roster"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:
        """Show the caller's own pending roster applications."""
        raw = (self.args or "").strip().lower()
        if raw and raw != _SUBVERB_STATUS:
            self.caller.msg(f"Unknown roster command '{raw}'. Try: roster status.")
            return

        # Scoped to the caller's own PlayerData only — mirrors
        # RosterEntryViewSet's owned-scope filter (#2122 leak analysis);
        # no id-based lookup exists on this command.
        pending = self.account.player_data.get_pending_applications()

        if not pending:
            self.caller.msg("You have no pending roster applications.")
            return

        lines = ["Your pending roster applications:"]
        lines.extend(
            f"  {application.character.key} — {application.get_status_display()} "
            f"(applied {application.applied_date:%Y-%m-%d})"
            for application in pending
        )
        self.caller.msg("\n".join(lines))
