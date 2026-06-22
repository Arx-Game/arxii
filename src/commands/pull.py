"""Telnet ``pull`` command — spend resonance through threads for tier effects.

Pull has no ceremony prerequisite (it is always in service of another declared
action). Grammar:

    pull resonance=<name> tier=<1-3> thread=<name or id>[,...] \\
        [trait=<name or id>] [technique=<name or id>]

    pull preview resonance=<name> tier=<1-3> thread=<name or id>[,...] ...

``preview`` as the first positional word switches to read-only mode (calls
preview_resonance_pull; no Action dispatched).

trait= and technique= populate PullActionContext.involved_traits /
involved_techniques. RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE, and FACET
threads are always in-action (exempt from these requirements).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.pull import PullThreadAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdPull(ArxCommand):
    """Pull resonance through threads to activate tier effects.

    Syntax:
        ``pull resonance=<name> tier=<1-3> thread=<name or id>[,...] ...``
        ``pull preview resonance=<name> tier=<1-3> thread=<name or id>[,...] ...``

    Examples:
        ``pull resonance=Embers tier=1 thread=Ember of Endurance trait=Endurance``
        ``pull preview resonance=Embers tier=1 thread=Ember of Endurance trait=Endurance``
    """

    key = "pull"
    locks = "cmd:all()"
    action = PullThreadAction()

    def _is_preview_mode(self) -> bool:
        tokens = (self.args or "").strip().split()
        return bool(tokens) and tokens[0].lower() == "preview"  # noqa: STRING_LITERAL

    def _pull_args(self) -> str:
        """Return args with 'preview' prefix stripped if present."""
        tokens = (self.args or "").strip().split()
        if tokens and tokens[0].lower() == "preview":  # noqa: STRING_LITERAL
            return " ".join(tokens[1:])
        return (self.args or "").strip()

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens left to right.

        ``thread`` greedily consumes tokens until the next ``key=`` is found,
        so thread names (and comma-separated thread lists) may contain spaces.
        All other kwargs are single whitespace-delimited tokens.
        """
        known_keys = {"resonance", "tier", "thread", "trait", "technique"}
        out: dict[str, str] = {}
        tokens = args.split()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if "=" not in token:
                index += 1
                continue
            key, _, value = token.partition("=")
            if key == "thread":  # noqa: STRING_LITERAL
                # Greedily consume remaining tokens until the next known key=
                remaining: list[str] = [value]
                index += 1
                while index < len(tokens):
                    next_token = tokens[index]
                    if "=" in next_token and next_token.partition("=")[0] in known_keys:
                        break
                    remaining.append(next_token)
                    index += 1
                out["thread"] = " ".join(remaining).strip()
                continue
            out[key] = value
            index += 1
        return out

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse pull kwargs and build PullActionContext."""
        from world.magic.models import Resonance, Thread  # noqa: PLC0415
        from world.magic.types import PullActionContext  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        raw = self._pull_args()
        if not raw:
            msg = "Pull what? (pull resonance=<name> tier=<1-3> thread=<name or id> [trait=<name>])"
            raise CommandError(msg)
        parsed = self._parse_kwargs(raw)

        resonance_val = parsed.get("resonance", "").strip()
        if not resonance_val:
            msg = "Specify a resonance: resonance=<name>."
            raise CommandError(msg)
        resonance = self.resolve_by_name_or_id(
            Resonance,
            resonance_val,
            not_found_msg=f"No resonance '{resonance_val}'.",
        )

        tier_str = parsed.get("tier", "").strip()
        if not tier_str or not tier_str.isdigit() or int(tier_str) not in (1, 2, 3):
            msg = "Specify tier 1, 2, or 3: tier=<1-3>."
            raise CommandError(msg)
        tier = int(tier_str)

        thread_str = parsed.get("thread", "").strip()
        if not thread_str:
            msg = "Specify at least one thread: thread=<name or id>."
            raise CommandError(msg)
        sheet = self.caller.sheet_data
        thread_vals = [t.strip() for t in thread_str.split(",") if t.strip()]
        threads = [
            self.resolve_by_name_or_id(
                Thread,
                v,
                owner=sheet,
                retired_at__isnull=True,
                not_found_msg=f"No thread found for '{v}'.",
            )
            for v in thread_vals
        ]

        involved_traits: tuple[int, ...] = ()
        trait_val = parsed.get("trait", "").strip()
        if trait_val:
            trait = self.resolve_by_name_or_id(
                Trait,
                trait_val,
                not_found_msg=f"No trait '{trait_val}'.",
            )
            involved_traits = (trait.pk,)

        involved_techniques: tuple[int, ...] = ()
        technique_val = parsed.get("technique", "").strip()
        if technique_val:
            from world.magic.models import Technique  # noqa: PLC0415

            technique = self.resolve_by_name_or_id(
                Technique,
                technique_val,
                not_found_msg=f"No technique '{technique_val}'.",
            )
            involved_techniques = (technique.pk,)

        pull_ctx = PullActionContext(
            involved_traits=involved_traits,
            involved_techniques=involved_techniques,
            involved_objects=(),
        )

        return {
            "resonance": resonance,
            "tier": tier,
            "threads": threads,
            "pull_action_context": pull_ctx,
        }

    def func(self) -> None:
        """Branch on preview vs commit."""
        if self._is_preview_mode():
            self._run_preview()
        else:
            super().func()

    def _run_preview(self) -> None:
        """Call preview_resonance_pull and display results (read-only)."""
        from world.magic.services.resonance import preview_resonance_pull  # noqa: PLC0415

        try:
            kwargs = self.resolve_action_args()
        except CommandError as exc:
            self.caller.msg(str(exc))
            return

        result = preview_resonance_pull(
            character_sheet=self.caller.sheet_data,
            resonance=kwargs["resonance"],
            tier=kwargs["tier"],
            threads=kwargs["threads"],
        )

        effects = ", ".join(e.kind for e in result.resolved_effects) or "none"
        affordable = "yes" if result.affordable else "no"
        msg = (
            f"Tier-{kwargs['tier']} pull using {len(kwargs['threads'])} thread(s) "
            f"via {kwargs['resonance'].name} "
            f"(cost: {result.resonance_cost} resonance / {result.anima_cost} anima)\n"
            f"Effects: {effects}  |  Affordable: {affordable}"
        )
        self.caller.msg(msg)
