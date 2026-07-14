"""Telnet command for voluntary asset introduction (#2295)."""

from __future__ import annotations

from commands.command import ArxCommand


class CmdIntroduce(ArxCommand):
    """Introduce one of your assets to a co-present ally.

    Usage:
        introduce <asset name>=<ally name>

    Creates a co-ownership NPCAsset for the ally, allowing them to task
    the same NPC independently. Both you and the ally must be in the
    same room.
    """

    key = "introduce"
    aliases = ["introduce_asset"]
    locks = "cmd:all()"
    help_category = "Social"

    def func(self) -> None:
        from actions.registry import get_action  # noqa: PLC0415
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.scenes.services import (  # noqa: PLC0415
            MissingPrimaryPersonaError,
            persona_for_character,
        )

        if not self.args or "=" not in self.args:
            self.msg("Usage: introduce <asset name>=<ally name>")
            return

        asset_name, ally_name = self.args.split("=", 1)
        asset_name = asset_name.strip()
        ally_name = ally_name.strip()

        if not asset_name or not ally_name:
            self.msg("Usage: introduce <asset name>=<ally name>")
            return

        # Resolve the asset: search the caller's owned assets by asset_persona name.
        try:
            persona = persona_for_character(self.caller)
        except (AttributeError, MissingPrimaryPersonaError):
            self.msg("No active character sheet.")
            return

        asset = NPCAsset.objects.filter(
            promoter_persona=persona,
            asset_persona__name__iexact=asset_name,
        ).first()
        if asset is None:
            self.msg(f"You don't own an asset named '{asset_name}'.")
            return

        # Resolve the ally by searching the room.
        ally = self.caller.search(ally_name, location=self.caller.location)
        if ally is None:
            return  # search() sends its own error message

        # Resolve ally's persona.
        try:
            ally_persona = persona_for_character(ally)
        except (AttributeError, MissingPrimaryPersonaError):
            self.msg(f"{ally.name} has no active character sheet.")
            return

        action = get_action("introduce_asset")
        result = action.run(
            actor=self.caller,
            asset_id=asset.pk,
            ally_persona_id=ally_persona.pk,
        )
        self.msg(result.message)
