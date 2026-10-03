"""Telnet verbs for after-fight allegiance choices (#4091): settle, sendaway, retain."""

from __future__ import annotations

from typing import Any

from actions.definitions.allegiance import SendAwayAction
from actions.definitions.charm_asset import CharmAssetAction
from commands.command import ArxCommand
from commands.consent import ConsentRequestCommand
from commands.exceptions import CommandError

# `retain <character>=<kind>` accepts either spelling of the hyphenated kind.
_RETAIN_ROLE_CONTEXTS = {
    "informant": "informant",
    "contact": "contact",
    "personal_favor": "personal_favor",
    "personal-favor": "personal_favor",
}


class CmdSettle(ConsentRequestCommand):
    """Settle a charm, turn or calm on an NPC. Anyone in the scene may try.

    Usage:
        settle <character>
    """

    key = "settle"
    action_key = "settle"
    help_category = "Social"


class CmdSendAway(ArxCommand):
    """Send an NPC under your sway out of the scene.

    Usage:
        sendaway <character>
    """

    key = "sendaway"
    locks = "cmd:all()"
    help_category = "Social"
    action = SendAwayAction()

    def resolve_action_args(self) -> dict[str, Any]:
        from world.combat.constants import OpponentStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        target = self.search_or_raise((self.args or "").strip())
        sheet = target.character_sheet
        if sheet is not None:
            from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

            return {"target_persona_id": active_persona_for_sheet(sheet).pk}
        opponent = (
            CombatOpponent.objects.filter(objectdb=target, status=OpponentStatus.WON_OVER)
            .order_by("-pk")
            .first()
        )
        if opponent is None:
            not_held_msg = "They are not under your sway."
            raise CommandError(not_held_msg)
        return {"combat_opponent_id": opponent.pk}


class CmdRetain(ArxCommand):
    """Take a won-over NPC into service as a charm-acquired asset.

    Usage:
        retain <character>=<informant|contact|personal_favor>
    """

    key = "retain"
    locks = "cmd:all()"
    help_category = "Social"
    action = CharmAssetAction()

    def resolve_action_args(self) -> dict[str, Any]:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        usage = "Usage: retain <character>=<informant|contact|personal_favor>"
        raw = self.require_args(usage)
        if "=" not in raw:
            raise CommandError(usage)
        name, role_token = (part.strip() for part in raw.split("=", 1))
        if not name or not role_token:
            raise CommandError(usage)
        role_context = _RETAIN_ROLE_CONTEXTS.get(role_token.lower())
        if role_context is None:
            role_msg = "Retain them as what? informant, contact, or personal-favor."
            raise CommandError(role_msg)
        target = self.search_or_raise(name)
        sheet = target.character_sheet
        if sheet is None:
            not_held_msg = "They are not under your sway."
            raise CommandError(not_held_msg)
        return {
            "target_persona_id": active_persona_for_sheet(sheet).pk,
            "role_context": role_context,
        }
