"""Telnet command for the narrative /consider threat readout (#2716).

Thin wrapper over ``world.combat.consider.consider_opponent`` — the same
service function the REST endpoint calls. No business logic in the command.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdConsider(ArxCommand):
    """Assess a foe's threat level relative to your own.

    Produces a narrative reading — banded prose, not raw numbers. The
    reading can be inaccurate on a failed PERCEPTION check: you get
    confidently wrong information, not silence. One reading per opponent
    per encounter (no re-rolls).

    Usage:
      consider <opponent>
    """

    key = "consider"
    aliases = ["assess"]
    locks = "cmd:all()"
    help_category = "Combat"
    action = None

    def func(self) -> None:
        from world.combat.consider import consider_opponent  # noqa: PLC0415
        from world.combat.models import (  # noqa: PLC0415
            CombatEncounter,
            CombatOpponent,
            CombatParticipant,
        )

        if not self.args:
            self.msg("Consider what? Use: consider <opponent>")
            return

        target_name = self.args.strip()

        # Find the active encounter in the caller's room.
        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere in particular.")
            return

        encounter = (
            CombatEncounter.objects.filter(room=room)
            .exclude(status="completed")
            .select_related("scene")
            .order_by("-created_at")
            .first()
        )
        if encounter is None:
            self.msg("There is no combat encounter here to consider foes in.")
            return

        # Find the caller's participant.
        try:
            sheet = self.caller.sheet_data
        except AttributeError:
            self.msg("You have no character sheet to assess with.")
            return

        participant = CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet=sheet,
        ).first()
        if participant is None:
            self.msg("You are not a participant in this encounter.")
            return

        # Resolve the opponent by name (case-insensitive).
        opponent = CombatOpponent.objects.filter(
            encounter=encounter,
            name__iexact=target_name,
        ).first()
        if opponent is None:
            self.msg(f"No opponent named '{target_name}' in this encounter.")
            return

        reading = consider_opponent(participant, opponent)
        self.msg(reading.prose)
