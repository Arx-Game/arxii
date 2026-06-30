"""Telnet ``gossip`` command (#1572) — work the rumor mill at a social hub.

Thin over ``world.secrets.gossip``: **plant** (spread a Level-1 secret you've come into), **seek**
(roll to overhear a hot secret you don't yet know), **suppress** (talk a secret's heat down). Gated
on Gossip >= 1 and standing in an ``is_social_hub`` room (the services enforce both). The reserved
``gossip`` verb — see ``commands/CLAUDE.md`` (``gossip`` is for Level-1-secret access at hubs).
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand

_NO_SKILL = "You don't have the ear for it (requires Gossip 1+)."
_USAGE = "Usage: gossip [seek | plant <#> | suppress <#>]  (bare `gossip` lists your secrets)."

# Subcommand verbs (kept as constants — STRING_LITERAL linter forbids bare identifier strings).
_LIST = "list"
_SEEK = "seek"
_PLANT = "plant"
_SUPPRESS = "suppress"


class CmdGossip(ArxCommand):
    """Work the rumor mill at a social hub.

    Usage:
      gossip               — your gossipable secrets (+ their heat in this hub's region)
      gossip seek          — roll to overhear a hot secret you don't yet know
      gossip plant <#>     — spread secret # (raises its regional heat)
      gossip suppress <#>  — talk secret #'s heat down
    """

    key = "gossip"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        from world.secrets.gossip import has_gossip_skill  # noqa: PLC0415

        character = self.caller
        if not has_gossip_skill(character):
            self.msg(_NO_SKILL)
            return
        room = character.location
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _LIST:
            self._show(character, room)
            return
        verb, _, rest = raw.partition(" ")
        verb = verb.lower()
        if verb == _SEEK:
            self._seek(character, room)
        elif verb in (_PLANT, _SUPPRESS):
            self._spread(character, room, verb, rest.strip())
        else:
            self.msg(_USAGE)

    def _show(self, character: Any, room: Any) -> None:
        from world.secrets.gossip import region_heat_for, spreadable_secrets  # noqa: PLC0415

        secrets = spreadable_secrets(character)
        if not secrets:
            self.msg("You hold no idle gossip worth spreading.")
            return
        lines = ["|wGossip you could spread:|n"]
        for index, secret in enumerate(secrets, 1):
            heat = region_heat_for(secret, room=room)
            lines.append(f"  {index}. {secret.content}  |x(heat here: {heat})|n")
        lines.append("Use |wgossip plant <#>|n to spread, or |wgossip suppress <#>|n to quiet it.")
        self.msg("\n".join(lines))

    def _seek(self, character: Any, room: Any) -> None:
        from world.secrets.gossip import GossipError, seek_gossip  # noqa: PLC0415
        from world.secrets.models import Secret  # noqa: PLC0415

        try:
            result = seek_gossip(character, room=room)
        except GossipError as exc:
            self.msg(exc.user_message)
            return
        if not result.success or result.surfaced_secret_id is None:
            self.msg("You catch nothing worth repeating.")
            return
        secret = Secret.objects.get(pk=result.surfaced_secret_id)
        self.msg(f"|yYou overhear a rumor:|n {secret.content}")

    def _spread(self, character: Any, room: Any, verb: str, arg: str) -> None:
        from world.secrets.gossip import (  # noqa: PLC0415
            GossipError,
            plant_gossip,
            spreadable_secrets,
            suppress_gossip,
        )

        secrets = spreadable_secrets(character)
        try:
            position = int(arg) - 1
        except (ValueError, TypeError):
            self.msg(_USAGE)
            return
        if not 0 <= position < len(secrets):
            self.msg(f"No gossip #{arg}. See |wgossip|n for the list.")
            return
        secret = secrets[position]
        action = plant_gossip if verb == _PLANT else suppress_gossip
        try:
            result = action(character, secret, room=room)
        except GossipError as exc:
            self.msg(exc.user_message)
            return
        if not result.success:
            self.msg("Your effort falls flat — the rumor doesn't take.")
            return
        verbed = "spread" if verb == _PLANT else "quieted"
        extra = " |R(now public knowledge!)|n" if result.went_public else ""
        self.msg(f"You {verbed} the rumor. Heat in this region: {result.heat}.{extra}")
