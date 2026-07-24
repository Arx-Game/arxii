"""Telnet command for the Ritual of the Durance — status / intent / convene (#1700).

A single command routes verbs through the Durance lifecycle:
- bare ``durance`` / ``durance status`` — readiness hub: level, unlock gate, eligible paths,
  declared intent, and whether a training site is present.
- ``durance intent <path|clear>`` — declare (or clear) a path intent via the existing
  ``SetPathIntentAction`` / ``ClearPathIntentAction`` actions.
- ``durance convene`` — open a site-convened Durance session via ``convene_durance_at_site``;
  the inductee then joins via ``ritual join <session_pk>``.
- ``durance selectpath <path name or id>`` — late-selection recovery for a character with no
  path on record at all (GM-finalize quickstart, NPCAsset promotion, #2121) via
  ``SelectPathAction``. Distinct from ``intent`` (which requires an existing path to compute
  the *next*-stage options from) — this is the one-time initial pick.

This is setup + status only — never a ceremony bypass. The rite itself runs through
the existing ``ritual`` verbs (``ritual join <id> testament=<oration> path=<name>``).
Mirrors ``CmdSanctum`` for subverb dispatch + error wrapping and ``CmdRitual`` for
lazy-import style.
"""

from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError

_STATUS_SUBVERB = "status"
_INTENT_SUBVERB = "intent"
_CONVENE_SUBVERB = "convene"
_SELECTPATH_SUBVERB = "selectpath"
_CLEAR_TOKEN = "clear"  # noqa: S105


class CmdDurance(ArxCommand):
    """Track readiness and open a Ritual of the Durance training session.

    Usage:
        durance                             — show your Durance readiness hub
        durance status                      — (same)
        durance intent <path name or id>    — declare your intended next path
        durance intent clear                — clear your declared path intent
        durance convene                     — open a site-convened Durance session
        durance selectpath <path name or id> — one-time recovery: pick a path when
                                                you have none on record at all
    """

    key = "durance"
    locks = "cmd:all()"
    help_category = "Progression"

    def func(self) -> None:
        """Route the leading subverb; bare ``durance``/``durance status`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _STATUS_SUBVERB:
            try:
                self._status()
            except CommandError as err:
                self.caller.msg(str(err))
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        try:
            if subverb == _INTENT_SUBVERB:
                self._intent(rest)
            elif subverb == _CONVENE_SUBVERB:
                self._convene()
            elif subverb == _SELECTPATH_SUBVERB:
                self._selectpath(rest)
            else:
                self.caller.msg(
                    f"Unknown durance action '{subverb}'. Try: status, intent, convene, selectpath."
                )
        except CommandError as err:
            self.caller.msg(str(err))

    # ------------------------------------------------------------------
    # Subverb handlers
    # ------------------------------------------------------------------

    def _status(self) -> None:
        """Display the Durance readiness hub for the caller."""
        from world.magic.audere_majora import AudereMajoraThreshold  # noqa: PLC0415
        from world.progression.selectors import eligible_advanced_paths_for  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)

        level = sheet.current_level
        target = level + 1

        lines = [f"|wDurance Readiness|n — level {level}, seeking {target}"]

        # Tier-boundary check: Audere Majora, not Durance.
        if AudereMajoraThreshold.objects.filter(boundary_level=level).exists():
            lines.append(
                "Your next step crosses a tier — that is Audere Majora, the Crossing, "
                "not the Durance."
            )
            lines.extend(self._intent_line(sheet))
            self.caller.msg("\n".join(lines))
            return

        # Authored unlock + requirements.
        lines.extend(self._unlock_readiness_lines(sheet, target))

        # Eligible Potential paths.
        eligible = eligible_advanced_paths_for(sheet)
        if eligible:
            names = ", ".join(p.name for p in eligible)
            lines.append(f"Eligible paths at this stage: {names}.")
        else:
            lines.append("No eligible advanced paths at this stage.")

        # Declared intent.
        lines.extend(self._intent_line(sheet))

        # Training site.
        lines.extend(self._site_lines())

        self.caller.msg("\n".join(lines))

    def _unlock_readiness_lines(self, sheet: object, target: int) -> list[str]:
        """Return lines for the ClassLevelUnlock gate + unmet requirements."""
        from world.progression.models import CharacterUnlock, ClassLevelUnlock  # noqa: PLC0415
        from world.progression.services.advancement import primary_class_level  # noqa: PLC0415
        from world.progression.services.spends import check_requirements_for_unlock  # noqa: PLC0415

        cl = primary_class_level(sheet.character)
        if cl is None:
            return ["You have no class level to advance."]

        try:
            unlock = ClassLevelUnlock.objects.get(
                character_class=cl.character_class, target_level=target
            )
        except ClassLevelUnlock.DoesNotExist:
            return [f"No advancement is authored for your next level ({target})."]

        met, failed = check_requirements_for_unlock(sheet.character, unlock)
        purchased = CharacterUnlock.objects.filter(
            character=sheet,
            character_class=unlock.character_class,
            target_level=unlock.target_level,
        ).exists()
        if purchased:
            unlock_line = "XP unlock: purchased."
        else:
            cost = unlock.get_xp_cost_for_character(sheet.character)
            unlock_line = f"XP unlock: not purchased (cost {cost})."

        if met and purchased:
            return [f"You are ready to advance to level {target}.", unlock_line]
        lines = [f"Not yet ready for level {target}:"]
        if not met:
            lines.extend(f"  — {r}" for r in failed)
        lines.append(unlock_line)
        return lines

    def _intent_line(self, sheet: object) -> list[str]:
        """Return a line showing the declared PathIntent, or none if unset."""
        from world.progression.models import PathIntent  # noqa: PLC0415

        intent = PathIntent.objects.filter(character_sheet=sheet).first()
        if intent is not None:
            return [f"Declared intent: {intent.intended_path.name}."]
        return ["No path intent declared."]

    def _site_lines(self) -> list[str]:
        """Return a line noting whether a Durance training site is in the current room."""
        if self.caller.location is None:
            return ["You are not in a room."]

        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.progression.models import DuranceTrainingSite  # noqa: PLC0415

        profile = get_room_profile(self.caller.location)
        if DuranceTrainingSite.objects.filter(room_profile=profile, is_active=True).exists():
            return ["A Durance training site is here."]
        return ["No training site here."]

    def _intent(self, rest: str) -> None:
        """Declare or clear the caller's path intent."""
        from actions.definitions.progression_rewards import (  # noqa: PLC0415
            ClearPathIntentAction,
            SetPathIntentAction,
        )

        if not rest:
            msg = "Usage: durance intent <path name or id> | clear."
            raise CommandError(msg)

        if rest.lower() == _CLEAR_TOKEN:
            result = ClearPathIntentAction().run(actor=self.caller)
            self.caller.msg(result.message)
            return

        # Resolve the token to a path.
        if rest.isdigit():
            path_id = int(rest)
        else:
            from world.progression.selectors import next_path_options  # noqa: PLC0415

            needle = rest.casefold()
            matched = [p for p in next_path_options(self.caller) if p.name.casefold() == needle]
            if not matched:
                msg = (
                    f"No available path named '{rest}'. Use 'durance status' to see eligible paths."
                )
                raise CommandError(msg)
            path_id = matched[0].pk

        result = SetPathIntentAction().run(actor=self.caller, path_id=path_id)
        self.caller.msg(result.message)

    def _selectpath(self, rest: str) -> None:
        """One-time recovery: pick a Path when the caller has none on record (#2121)."""
        from actions.definitions.progression_rewards import SelectPathAction  # noqa: PLC0415
        from world.classes.models import Path, PathStage  # noqa: PLC0415

        if not rest:
            msg = "Usage: durance selectpath <path name or id>."
            raise CommandError(msg)

        prospect_paths = Path.objects.filter(stage=PathStage.PROSPECT, is_active=True)
        if rest.isdigit():
            path_id = int(rest)
        else:
            needle = rest.casefold()
            matched = [p for p in prospect_paths if p.name.casefold() == needle]
            if not matched:
                names = ", ".join(p.name for p in prospect_paths)
                msg = f"No starting path named '{rest}'. Options: {names}."
                raise CommandError(msg)
            path_id = matched[0].pk

        result = SelectPathAction().run(actor=self.caller, path_id=path_id)
        self.caller.msg(result.message)

    def _convene(self) -> None:
        """Open a site-convened Durance session at the caller's current room."""
        from commands.ritual import _advancement_error_message  # noqa: PLC0415
        from world.progression.exceptions import ClassLevelAdvancementError  # noqa: PLC0415
        from world.progression.services.advancement import convene_durance_at_site  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)

        try:
            session = convene_durance_at_site(
                inductee_sheet=sheet,
                room=self.caller.location,
            )
        except ClassLevelAdvancementError as exc:
            raise CommandError(_advancement_error_message(exc)) from exc

        self.caller.msg(
            f"One stands before us in Durance. Speak thy name and testament.\n"
            f"Speak it with: ritual join {session.pk} testament=<oration> path=<name>"
        )
