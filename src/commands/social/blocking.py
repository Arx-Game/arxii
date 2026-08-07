"""Telnet block/mute commands (#1278).

Thin wrappers over ``world.scenes.block_services`` / ``mute_services`` — the telnet-compatibility
face of the same controls the web persona menu uses. No business logic here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.scenes.models import Persona

_NO_IDENTITY = "You have no character identity to act with."
_LOCK_ALL = "cmd:all()"
_PERSONA_SWITCH = "persona"


def _caller_persona(command: ArxCommand) -> Persona:
    try:
        return command.caller.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise CommandError(_NO_IDENTITY) from exc


def _target_persona(command: ArxCommand, name: str) -> tuple[object, Persona]:
    target = command.search_or_raise(name)
    try:
        return target, target.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist) as exc:
        msg = f"{target} has no character sheet."
        raise CommandError(msg) from exc


def _account_scope_from_switches(command: ArxCommand) -> bool:
    """True (account-first) unless the caller passed /persona (#2996 Decision 1).

    Reads ``switches`` defensively (not a bare ``command.switches``) because unit tests
    routinely call ``func()`` directly without going through Evennia's ``parse()`` step that
    would otherwise set it — a command instance built that way has no ``switches`` attribute
    at all yet.
    """
    try:
        switches = command.switches
    except AttributeError:
        switches = None
    return _PERSONA_SWITCH not in {s.lower() for s in (switches or [])}


class CmdBlock(ArxCommand):
    """Block a character's entire account so you can't see or be targeted by any of their faces.

    A reason is required and goes to staff, and a block only clears a full cron cycle after you
    lift it, so blocks are deliberate. Blocks the whole account by default (#2996) — use the
    /persona switch for the advanced, narrower option of blocking only this one face.

    Usage:
      +block <character>=<reason>          - block their whole account (default)
      +block/persona <character>=<reason>  - block only this one face (advanced)
    """

    key = "+block"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from world.scenes.block_services import create_block  # noqa: PLC0415

        try:
            name, _, reason = (self.args or "").partition("=")
            name, reason = name.strip(), reason.strip()
            if not name or not reason:
                self.msg("Usage: +block <character>=<reason>  (a reason is required).")
                return
            blocker_persona = _caller_persona(self)
            target, target_persona = _target_persona(self, name)
            # #2996 Decision 1: +block is account-first by default — blocks every face the
            # target's player currently plays. /persona opts into the narrower advanced shape
            # (create_block's own default, account_level=False) — only this exact face.
            account_level = _account_scope_from_switches(self)
            try:
                create_block(
                    blocker_account=self.account,
                    blocker_persona=blocker_persona,
                    blocked_persona=target_persona,
                    reason=reason,
                    account_level=account_level,
                )
            except ValidationError as exc:
                self.msg(exc.messages[0])
                return
            scope = "account" if account_level else "this character only"
            self.msg(
                f"You have blocked {target} ({scope}). It can only be lifted after a cron "
                f"cycle."
                + ("" if account_level else f" Use +shareblock {target} to extend it account-wide.")
            )
        except CommandError as err:
            self.msg(str(err))


class CmdUnblock(ArxCommand):
    """Lift a block. It stays in effect until the next cron sweep clears it.

    Usage:
      +unblock <character>
    """

    key = "+unblock"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from world.scenes.block_services import request_unblock  # noqa: PLC0415
        from world.scenes.models import Block  # noqa: PLC0415

        try:
            name = self.require_args("Usage: +unblock <character>")
            _, target_persona = _target_persona(self, name)
            block = Block.objects.filter(
                owner__account=self.account, blocked_persona=target_persona
            ).first()
            if block is None:
                self.msg(f"You have not blocked {name}.")
                return
            request_unblock(block)
            self.msg(f"Unblocking {name} — it clears after the next cron cycle.")
        except CommandError as err:
            self.msg(str(err))


class CmdShareBlock(ArxCommand):
    """Extend an existing block so ALL your characters block them.

    They may then realize those characters share a player. Usage:
      +shareblock <character>
    """

    key = "+shareblock"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from world.scenes.block_services import share_block_account_wide  # noqa: PLC0415
        from world.scenes.models import Block  # noqa: PLC0415

        try:
            name = self.require_args("Usage: +shareblock <character>")
            _, target_persona = _target_persona(self, name)
            block = Block.objects.filter(
                owner__account=self.account, blocked_persona=target_persona
            ).first()
            if block is None:
                self.msg(f"You have not blocked {name}.")
                return
            share_block_account_wide(block)
            self.msg(f"All of your characters now block {name}.")
        except CommandError as err:
            self.msg(str(err))


class CmdMute(ArxCommand):
    """Quietly filter a character's whole account out of your own feed (they're never aware).

    Mutes the whole account by default (#2996) — every face that player currently plays — for
    symmetry with block. Use the /persona switch for the advanced, narrower option of muting
    only this one face.

    Usage:
      +mute <character>[=ic|ooc|both]          - mute their whole account (default)
      +mute/persona <character>[=ic|ooc|both]  - mute only this one face (advanced)
    """

    key = "+mute"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from evennia_extensions.models import PlayerData  # noqa: PLC0415
        from world.scenes.mute_services import set_mute  # noqa: PLC0415

        try:
            name, _, scope = (self.args or "").partition("=")
            name, scope = name.strip(), scope.strip().lower()
            if not name:
                self.msg("Usage: +mute <character>[=ic|ooc|both]")
                return
            ic = scope in ("", "ic", "both")
            ooc = scope in ("", "ooc", "both")
            _, target_persona = _target_persona(self, name)
            owner, _ = PlayerData.objects.get_or_create(account=self.account)
            # #2996: +mute is account-first by default, mirroring +block's Decision 1 default.
            # /persona opts into the narrower advanced shape (set_mute's own default,
            # account_level=False) — only this exact face.
            account_level = _account_scope_from_switches(self)
            set_mute(
                owner=owner,
                muted_persona=target_persona,
                ic=ic,
                ooc=ooc,
                account_level=account_level,
            )
            scopes = "/".join(s for s, on in (("IC", ic), ("OOC", ooc)) if on)
            account_note = "account" if account_level else "this character only"
            self.msg(f"Muted {name} ({scopes}, {account_note}).")
        except CommandError as err:
            self.msg(str(err))


class CmdUnmute(ArxCommand):
    """Stop muting a character.

    Usage:
      +unmute <character>
    """

    key = "+unmute"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from evennia_extensions.models import PlayerData  # noqa: PLC0415
        from world.scenes.mute_services import unmute  # noqa: PLC0415

        try:
            name = self.require_args("Usage: +unmute <character>")
            _, target_persona = _target_persona(self, name)
            owner, _ = PlayerData.objects.get_or_create(account=self.account)
            unmute(owner=owner, muted_persona=target_persona)
            self.msg(f"Unmuted {name}.")
        except CommandError as err:
            self.msg(str(err))


class CmdBlockList(ArxCommand):
    """List the characters you've blocked and muted.

    Usage:
      +blocklist
    """

    key = "+blocklist"
    locks = _LOCK_ALL
    action = None

    def func(self) -> None:
        from world.scenes.models import Block, Mute  # noqa: PLC0415

        blocks = Block.objects.filter(owner__account=self.account).select_related("blocked_persona")
        mutes = Mute.objects.filter(owner__account=self.account).select_related("muted_persona")
        lines = ["|wBlocked:|n"]
        lines += [
            f"  {b.blocked_persona.name}"
            + (" (all my characters)" if b.account_level else "")
            + (" - lifting" if b.pending_removal_at is not None else "")
            for b in blocks
        ] or ["  (none)"]
        lines.append("|wMuted:|n")
        lines += [
            f"  {m.muted_persona.name}" + (" (all my characters)" if m.account_level else "")
            for m in mutes
        ] or ["  (none)"]
        self.msg("\n".join(lines))
