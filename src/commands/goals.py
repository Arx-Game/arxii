"""Goal authoring telnet command — the ``goal <subverb>`` namespace (#1350).

A single ``ArxCommand`` routes the goal verbs through ``action.run()`` — the
same seam the web ``CharacterGoalViewSet`` / ``GoalJournalViewSet`` now use.

- ``goal add domain=<id|name> points=<n> [notes=<text>]``  — revise one allocation
  (weekly-gated; merges with the rest)
- ``goal set domain=<id>:points=<n>[,...]``                — bulk replace (weekly revision-gated)
- ``goal log [domain=<id|name>] title=<text> content=<text> [public]``
- bare ``goal``                                            — current allocations + remaining points
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags

_SUBVERB_ADD = "add"
_SUBVERB_SET = "set"
_SUBVERB_LOG = "log"
_SUBVERB_LIST = "list"
_VALID_SUBVERBS = frozenset({_SUBVERB_ADD, _SUBVERB_SET, _SUBVERB_LOG, _SUBVERB_LIST})

_KEY_DOMAIN = "domain"
_KEY_POINTS = "points"
_KEY_NOTES = "notes"
_KEY_TITLE = "title"
_KEY_CONTENT = "content"
_FLAG_PUBLIC = "public"

# Multi-word value keys — their value runs until the next ``key=`` token or a
# known bare flag (so ``content=Hello public`` does not swallow ``public``).
_MULTIWORD_KEYS = frozenset({_KEY_TITLE, _KEY_CONTENT, _KEY_NOTES})

# Bare-token flags — a multi-word value terminates when one appears.
_KNOWN_FLAGS = frozenset({_FLAG_PUBLIC})


def _require(value: str | None, name: str) -> str:
    if value is None or value == "":
        msg = f"{name} is required."
        raise CommandError(msg)
    return value


def _require_int(value: str | None, name: str) -> int:
    raw = _require(value, name)
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"{name} must be a number."
        raise CommandError(msg) from exc


class CmdGoal(ArxCommand):
    """Set character goals and log progress toward them.

    Usage:
        goal                            — list allocations + points remaining
        goal list                       — same as bare ``goal``
        goal add domain=<id|name> points=<n> [notes=<text>]
        goal set domain=<id>:points=<n>[,domain=<id>:points=<n>...]
        goal log [domain=<id|name>] title=<text> content=<text> [public]

    Domains resolve by id or name (case-insensitive). Both ``goal set`` and
    ``goal add`` share the weekly revision limit (they route through the same
    ``set_character_goals`` service the web ``update_all`` uses): the first
    goal write sets allocations freely, but further writes within a week are
    rejected until the revision window reopens. ``goal add`` merges the chosen
    domain into your existing allocations (replacing that one domain if already
    set); ``goal set`` replaces all allocations at once.
    """

    key = "goal"
    aliases: list[str] = []
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        try:
            raw = (self.args or "").strip()
            if not raw or raw.lower() == _SUBVERB_LIST:
                self._show_allocations()
                return
            parts = raw.split(maxsplit=1)
            subverb = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""
            if subverb not in _VALID_SUBVERBS:
                self.msg(self._usage())
                return
            if subverb == _SUBVERB_ADD:
                self._add(rest)
            elif subverb == _SUBVERB_SET:
                self._set(rest)
            elif subverb == _SUBVERB_LOG:
                self._log(rest)
        except CommandError as err:
            self.msg(str(err))

    # -- write verbs ----------------------------------------------------------

    def _add(self, rest: str) -> None:
        kwargs, _flags = parse_kv_and_flags(
            rest, multiword_keys=_MULTIWORD_KEYS, known_flags=_KNOWN_FLAGS
        )
        domain = self._resolve_domain(kwargs.get(_KEY_DOMAIN))
        points = _require_int(kwargs.get(_KEY_POINTS), _KEY_POINTS)
        notes = kwargs.get(_KEY_NOTES, "")
        from world.goals.models import CharacterGoal  # noqa: PLC0415

        existing = {
            g.domain_id: g for g in CharacterGoal.objects.filter(character=self.caller.sheet_data)
        }
        goals = []
        for domain_id, goal in existing.items():
            goals.append({"domain": domain_id, "points": goal.points, "notes": goal.notes})
        # Replace the chosen domain's row, or append.
        goals = [g for g in goals if g["domain"] != domain.pk]
        goals.append({"domain": domain.pk, "points": points, "notes": notes})
        self._dispatch_set(goals)

    def _set(self, rest: str) -> None:
        rest = rest.strip()
        if not rest:
            msg = "Usage: goal set domain=<id>:points=<n>[,domain=<id>:points=<n>...]"
            raise CommandError(msg)
        goals: list[dict[str, Any]] = []
        for raw_chunk in rest.split(","):
            chunk = raw_chunk.strip()
            if not chunk or "=" not in chunk:
                msg = "Each goal is domain=<id>:points=<n>."
                raise CommandError(msg)
            domain_part, _, points_part = chunk.partition(":")
            _, _, domain_value = domain_part.partition("=")
            _, _, points_value = points_part.partition("=")
            domain = self._resolve_domain(domain_value)
            goals.append(
                {
                    "domain": domain.pk,
                    "points": _require_int(points_value, _KEY_POINTS),
                    "notes": "",
                }
            )
        self._dispatch_set(goals)

    def _log(self, rest: str) -> None:
        kwargs, flags = parse_kv_and_flags(
            rest, multiword_keys=_MULTIWORD_KEYS, known_flags=_KNOWN_FLAGS
        )
        from actions.registry import get_action  # noqa: PLC0415

        domain_value = kwargs.get(_KEY_DOMAIN)
        domain = self._resolve_domain(domain_value) if domain_value else None
        title = _require(kwargs.get(_KEY_TITLE), _KEY_TITLE)
        content = _require(kwargs.get(_KEY_CONTENT), _KEY_CONTENT)
        result = get_action("log_goal_progress").run(
            actor=self.caller,
            domain=domain,
            title=title,
            content=content,
            is_public=_FLAG_PUBLIC in flags,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_set(self, goals: list[dict[str, Any]]) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        result = get_action("set_character_goals").run(actor=self.caller, goals=goals)
        if result.message:
            self.msg(result.message)

    # -- read -----------------------------------------------------------------

    def _show_allocations(self) -> None:
        from world.goals.models import CharacterGoal  # noqa: PLC0415
        from world.goals.services import MAX_GOAL_POINTS  # noqa: PLC0415

        goals = list(
            CharacterGoal.objects.filter(character=self.caller.sheet_data).select_related("domain")
        )
        total = sum(g.points for g in goals)
        lines = [f"|wGoals: {total}/{MAX_GOAL_POINTS} points allocated|n"]
        if not goals:
            lines.append("No goals set.")
        else:
            for goal in goals:
                lines.append(f"  [{goal.domain.name}] {goal.points} pts")
                if goal.notes:
                    lines.append(f"      {goal.notes}")
        self.msg("\n".join(lines))

    # -- helpers --------------------------------------------------------------

    def _resolve_domain(self, value: str | None) -> Any:
        if value is None or value == "":
            msg = "domain is required (name or id)."
            raise CommandError(msg)
        from world.goals.serializers import get_goal_domains_queryset  # noqa: PLC0415

        qs = get_goal_domains_queryset()
        if value.isdigit():
            domain = qs.filter(pk=int(value)).first()
        else:
            domain = qs.filter(name__iexact=value).first()
        if domain is None:
            msg = f"No goal domain '{value}' found."
            raise CommandError(msg)
        return domain

    def _usage(self) -> str:
        return (
            "Usage: goal [list|add domain=<id|name> points=<n> [notes=<text>]|"
            "set domain=<id>:points=<n>[,...]|"
            "log [domain=<id|name>] title=<text> content=<text> [public]]"
        )
