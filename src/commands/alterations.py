"""Telnet commands for resolving Mage Scars (magical alterations).

Thin telnet face of ``actions.definitions.alterations.ResolveAlterationAction``.
The web path uses ``PendingAlterationViewSet.resolve``; both converge on the
same action.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.alterations import ResolveAlterationAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdMageScar(ArxCommand):
    """List and resolve pending Mage Scars.

    Usage:
        magescar
        magescar list
        magescar resolve <id> template=<library_id>
        magescar resolve <id> [scratch] name=<name> player=<desc> observer=<desc>
                           [weakness=<damage_type>] weak_mag=<n> res_mag=<n>
                           social_mag=<n> visible=yes|no [parent=<template_id>]
    """

    key = "magescar"
    locks = "cmd:all()"
    action = ResolveAlterationAction()

    def func(self) -> None:
        """Route ``list`` and ``resolve`` subcommands."""
        args = (self.args or "").strip()
        usage_msg = "Usage: magescar [list|resolve <id> ...]"
        try:
            if not args or args.lower().startswith("list"):
                self._handle_list()
                return

            first = args.split()[0].lower()
            if first == "resolve":  # noqa: STRING_LITERAL
                rest = args[len("resolve") :].strip()
                self._handle_resolve(rest)
                return

            raise CommandError(usage_msg)
        except CommandError as err:
            self.caller.msg(str(err))

    def _handle_list(self) -> None:
        """List OPEN pending alterations for the actor."""
        from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
        from world.magic.models import PendingAlteration  # noqa: PLC0415

        sheet = self.caller.sheet_data
        pendings = PendingAlteration.objects.filter(
            character=sheet,
            status=PendingAlterationStatus.OPEN,
        ).select_related("origin_affinity", "origin_resonance", "triggering_scene")

        if not pendings.exists():
            self.caller.msg("You have no pending Mage Scars.")
            return

        lines = ["|wPending Mage Scars:|n"]
        for p in pendings:
            scene = p.triggering_scene
            scene_text = f" (scene {scene.pk})" if scene else ""
            lines.append(
                f"  [#{p.pk}] Tier {p.get_tier_display()} — "
                f"{p.origin_affinity.name}/{p.origin_resonance.name}{scene_text}"
            )
        self.caller.msg("\n".join(lines))

    def _handle_resolve(self, rest: str) -> None:
        """Resolve a pending alteration by library entry or scratch fields."""
        tokens = rest.split()
        if not tokens:
            msg = "Resolve which pending alteration? Usage: magescar resolve <id> ..."
            raise CommandError(msg)
        try:
            pending_id = int(tokens[0])
        except ValueError as exc:
            msg = "Pending alteration id must be a number."
            raise CommandError(msg) from exc

        kwargs: dict[str, Any] = {"pending_id": pending_id}
        kw_tokens = tokens[1:]
        if kw_tokens and kw_tokens[0].lower() == "scratch":  # noqa: STRING_LITERAL
            kw_tokens = kw_tokens[1:]
        raw_kwargs = self._parse_kwargs(kw_tokens)

        if "template" in raw_kwargs:  # noqa: STRING_LITERAL
            try:
                kwargs["library_template_id"] = int(raw_kwargs["template"])
            except ValueError as exc:
                msg = "Library template id must be a number."
                raise CommandError(msg) from exc
        else:
            kwargs.update(self._build_scratch_kwargs(raw_kwargs))

        result = self.action.run(actor=self.caller, **kwargs)
        if result and result.message:
            self.caller.msg(result.message)

    def _parse_kwargs(self, tokens: list[str]) -> dict[str, str]:
        """Parse trailing ``key=value`` tokens into a normalized dict."""
        kwargs: dict[str, str] = {}
        for token in tokens:
            if "=" not in token or token.startswith("="):
                msg = f"Invalid argument '{token}'. Expected key=value."
                raise CommandError(msg)
            key, _, value = token.partition("=")
            kwargs[key.lower()] = value
        return kwargs

    def _build_scratch_kwargs(self, raw: dict[str, str]) -> dict[str, Any]:
        """Translate scratch-form kwargs into ResolveAlterationAction kwargs."""
        required = {"name", "player", "observer"}
        missing = required - raw.keys()
        if missing:
            msg = f"Missing scratch fields: {', '.join(sorted(missing))}"
            raise CommandError(msg)

        from world.conditions.models import DamageType  # noqa: PLC0415

        kwargs: dict[str, Any] = {
            "name": raw["name"],
            "player_description": raw["player"],
            "observer_description": raw["observer"],
        }

        if "weakness" in raw:  # noqa: STRING_LITERAL
            kwargs["weakness_damage_type"] = self.resolve_by_name_or_id(
                DamageType,
                raw["weakness"],
                field="name",
                not_found_msg=f"Damage type '{raw['weakness']}' was not found.",
            )
        else:
            kwargs["weakness_damage_type"] = None

        kwargs["weakness_magnitude"] = self._int_or_zero(raw.get("weak_mag"), "weak_mag")
        kwargs["resonance_bonus_magnitude"] = self._int_or_zero(raw.get("res_mag"), "res_mag")
        kwargs["social_reactivity_magnitude"] = self._int_or_zero(
            raw.get("social_mag"), "social_mag"
        )
        kwargs["is_visible_at_rest"] = raw.get("visible", "").lower() in {"yes", "true", "y"}

        if "parent" in raw:  # noqa: STRING_LITERAL
            from world.magic.models import (  # noqa: PLC0415
                MagicalAlterationTemplate,
            )

            try:
                kwargs["parent_template"] = MagicalAlterationTemplate.objects.get(
                    pk=int(raw["parent"])
                )
            except (ValueError, MagicalAlterationTemplate.DoesNotExist) as exc:
                msg = "Parent template id was not found."
                raise CommandError(msg) from exc
        else:
            kwargs["parent_template"] = None

        return kwargs

    def _int_or_zero(self, value: str | None, label: str) -> int:
        """Parse an optional int token; raise CommandError on bad input."""
        if value is None:
            return 0
        try:
            return int(value)
        except ValueError as exc:
            msg = f"{label} must be a number."
            raise CommandError(msg) from exc
