"""Telnet ``weave`` command — the thin shell over WeaveThreadAction (#1337).

Thin telnet face of ``actions.definitions.threads.WeaveThreadAction``. Parses
``weave resonance=<name> trait=<name or id> [name=<thread name>]`` into the action's
kwargs and delegates; all eligibility/creation logic lives in the action + the
``weave_thread`` service. The web path uses the same action via the thread viewset.

Reference-grammar scope: the worked example supports the **TRAIT** anchor only
(``trait=<name or id>``). Other anchor kinds (covenant role, facet, mantle, technique,
relationship track/capstone, sanctum) are extended by the thread-weaving journey
issue — this command is the direct-viewset→Action telnet pattern proof.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.threads import WeaveThreadAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

# Telnet kwarg tokens players type (``key=value``); ``name`` greedily consumes the
# rest of the line so thread names may contain spaces.
_RESONANCE_KWARG = "resonance"
_TRAIT_KWARG = "trait"
_NAME_KWARG = "name"


class CmdWeaveThread(ArxCommand):
    """Weave a new thread anchored to a trait you are unlocked for.

    Telnet grammar (TRAIT anchor only; the journey issue extends other kinds):
        ``weave resonance=<name> trait=<name or id>``
        ``weave resonance=<name> trait=<name or id> name=<thread name>``

    Example:
        ``weave resonance=Embers trait=Bravery name=Ember of the First Hearth``
        ``weave resonance=Embers trait=5 name=Ember of the First Hearth``

    ``resonance`` and ``trait`` are required; ``name`` is optional and captures
    the rest of the line (so it may contain spaces). The thread's resonance and
    trait anchor are resolved here; everything else is the action's concern.
    """

    key = "weave"
    locks = "cmd:all()"
    action = WeaveThreadAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``weave resonance=<name> trait=<name or id> [name=<...>]`` into action kwargs."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        args = self.require_args(
            "Weave what? (weave resonance=<name> trait=<id> [name=<thread name>])"
        )
        parsed = self._parse_kwargs(args)

        resonance_name = parsed.get(_RESONANCE_KWARG, "").strip()
        if not resonance_name:
            msg = "Specify a resonance: resonance=<name>."
            raise CommandError(msg)
        resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
        if resonance is None:
            msg = f"There is no resonance called '{resonance_name}'."
            raise CommandError(msg)

        trait_val = parsed.get(_TRAIT_KWARG, "").strip()
        if not trait_val:
            msg = "Specify a trait anchor: trait=<name or id>."
            raise CommandError(msg)
        trait = self.resolve_by_name_or_id(
            Trait,
            trait_val,
            not_found_msg=f"No trait found for '{trait_val}'.",
        )

        return {
            "target_kind": TargetKind.TRAIT,
            "target": trait,
            "resonance": resonance,
            "name": parsed.get(_NAME_KWARG, "").strip(),
        }

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens, left to right.

        ``resonance`` and ``trait`` are single whitespace-delimited tokens; once a
        ``name=`` token is seen, the remainder of the line (including spaces) is its
        value, so thread names may contain spaces.
        """
        out: dict[str, str] = {}
        tokens = args.split()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if "=" not in token:
                index += 1
                continue
            key, _, value = token.partition("=")
            if key == _NAME_KWARG:
                out[_NAME_KWARG] = " ".join([value, *tokens[index + 1 :]]).strip()
                break
            out[key] = value
            index += 1
        return out
