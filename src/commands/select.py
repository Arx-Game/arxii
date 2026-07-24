"""The generic select command (#2665).

Resolves any PendingSelection regardless of source. The first consumer
is the Sage's weakness reading; future consumers (tarot mage, etc.) plug
into the same command.
"""

from commands.command import ArxCommand


class CmdSelect(ArxCommand):
    """Resolve a pending selection.

    Usage:
      select              — list your pending selections
      select <option>     — choose an option by id or ordinal number

    Generic: resolves any PendingSelection regardless of source.
    The first consumer is the Sage's weakness reading (#2665).
    """

    key = "select"
    locks = "cmd:all()"
    help_category = "Combat"

    def func(self) -> None:
        caller = self.caller
        try:
            sheet = caller.character_sheet
        except AttributeError:
            sheet = None
        if sheet is None:
            caller.msg("You have no character sheet to make selections for.")
            return

        if not self.args.strip():
            self._list_pending(sheet)
            return

        self._resolve(sheet, self.args.strip())

    def _list_pending(self, sheet: object) -> None:
        from world.combat.models import PendingSelection  # noqa: PLC0415

        selections = PendingSelection.objects.filter(
            participant__character_sheet=sheet,
            resolved_at__isnull=True,
        ).select_related("target_opponent", "encounter")

        if not selections:
            self.caller.msg("You have no pending selections.")
            return

        lines = ["|wPending selections:|n"]
        for sel in selections:
            lines.append(f"\n|c[{sel.selection_type}]|n — Target: {sel.target_opponent}")
            for i, opt in enumerate(sel.options_json, 1):
                lines.append(f"  {i}. {opt['label']}")
                if opt.get("description"):
                    lines.append(f"     {opt['description']}")
        self.caller.msg("\n".join(lines))

    def _resolve(self, sheet: object, arg: str) -> None:
        from world.combat.constants import SelectionType  # noqa: PLC0415
        from world.combat.models import PendingSelection  # noqa: PLC0415

        selections = list(
            PendingSelection.objects.filter(
                participant__character_sheet=sheet,
                resolved_at__isnull=True,
            ).select_related("target_opponent", "encounter", "participant")
        )

        if not selections:
            self.caller.msg("You have no pending selections.")
            return

        # Try to match by ordinal number first
        chosen_id = None
        try:
            ordinal = int(arg)
            for sel in selections:
                if 1 <= ordinal <= len(sel.options_json):
                    chosen_id = sel.options_json[ordinal - 1]["id"]
                    break
        except ValueError:
            chosen_id = arg

        if chosen_id is None:
            self.caller.msg(f"No option matching '{arg}'. Use a number or option name.")
            return

        # Try each selection until one resolves
        for sel in selections:
            option_ids = {opt["id"] for opt in sel.options_json}
            if chosen_id in option_ids:
                if sel.selection_type == SelectionType.WEAKNESS:
                    from world.covenants.weakness import resolve_weakness_selection  # noqa: PLC0415

                    if resolve_weakness_selection(sel, chosen_id):
                        self.caller.msg(f"You actualize: {chosen_id}")
                        return
                    self.caller.msg("That selection could not be resolved.")
                    return
                self.caller.msg(f"Unknown selection type: {sel.selection_type}")
                return

        self.caller.msg(f"No pending option matching '{arg}'.")
