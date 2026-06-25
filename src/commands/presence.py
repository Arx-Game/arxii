"""Telnet presence-privacy commands (#1463): ``afk`` and ``hide``/``unhide``.

Two per-character self-presence toggles that pair with the ``who``/``where`` surfaces:

- **afk** — a transient "away from keyboard" marker (lives on the puppet's ndb; cleared on
  toggle or reload). While set, you show as ``away`` on ``who`` regardless of real idle.
- **hide** / **unhide** — quiet/hidden mode (persistent ``TenureDisplaySettings.appear_offline``).
  While hidden you drop off ``where``/``who`` and become unpageable — EXCEPT to people on your
  allowlist, who still see and reach you. Mail, missions, and channels keep working, and people
  in your own room always see you. Persists across logins.

These are thin OOC toggles (Django patterns, no flows — see roster/CLAUDE.md); the web frontend
will offer the same hide switch off the player's own visibility settings as a follow-up.
"""

from __future__ import annotations

from typing import ClassVar

from commands.command import ArxCommand

# The command verb that forces quiet mode off (vs. ``hide`` which toggles). Shared by the
# alias list and the func that branches on which verb the player typed.
CMD_UNHIDE = "unhide"


class CmdAfk(ArxCommand):
    """Mark yourself away — or back again.

    While away you show as ``away`` on ``who`` no matter how recently you typed. The marker is
    transient: it clears when you toggle it off or the server reloads.

    Usage:
      afk
    """

    key = "afk"
    aliases: ClassVar[list[str]] = ["/afk"]
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        now_afk = not self.caller.ndb.appear_afk
        self.caller.ndb.appear_afk = now_afk
        if now_afk:
            self.msg("You are now marked |yaway|n. Type afk again when you're back.")
        else:
            self.msg("You are no longer marked away.")


class CmdHide(ArxCommand):
    """Appear offline — or come back online.

    While hidden you drop off ``where`` and ``who`` and others can't page you: they get the same
    response as if you were offline. The exception is your allowlist — friends on it still see you
    and can page you, and you can page them. Mail, missions, and chat channels all keep working,
    and people in your own room always see you; this is just for some peace and quiet at a
    distance. Your choice persists across logins.

    Usage:
      hide      - toggle hidden mode on or off
      unhide    - come back online
    """

    key = "hide"
    aliases: ClassVar[list[str]] = [CMD_UNHIDE]
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.roster.services.display import set_appear_offline  # noqa: PLC0415
        from world.scenes.presence import character_appears_offline  # noqa: PLC0415

        try:
            tenure = self.caller.sheet_data.roster_entry.current_tenure
        except (AttributeError, ObjectDoesNotExist):
            tenure = None
        if tenure is None:
            self.msg("Only a rostered character can change visibility.")
            return

        currently = character_appears_offline(self.caller)
        target = False if self.cmdstring == CMD_UNHIDE else not currently
        set_appear_offline(tenure=tenure, value=target)
        if target:
            self.msg(
                "You are now |yhidden|n — appearing offline. You're off where/who and "
                "unpageable except to your allowlist; mail, missions, and channels still work, "
                "and people in your room still see you. Type unhide to come back."
            )
        else:
            self.msg("You are no longer hidden — you appear online again.")
