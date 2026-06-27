"""Journal authoring telnet command — the ``journal <subverb>`` namespace (#1350).

A single ``ArxCommand`` routes the journal write verbs through ``action.run()``
— the same seam the web ``JournalEntryViewSet`` now uses. Subverbs:

- ``journal write title=<text> body=<text> [public] [tags=a,b,c]``
- ``journal respond <id|#> type=praise|retort title=<text> body=<text>``
- ``journal edit <id|#> [title=<text>] [body=<text>]``

Long-form authoring is web-first; this thin surface keeps the authoring loop
integration-testable. Bare ``journal`` lists the caller's recent entries.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags

# Subverbs.
_SUBVERB_WRITE = "write"
_SUBVERB_RESPOND = "respond"
_SUBVERB_EDIT = "edit"
_SUBVERB_LIST = "list"
# Telnet key=value argument keys.
_KEY_TYPE = "type"
_KEY_TITLE = "title"
_KEY_BODY = "body"
_KEY_TAGS = "tags"
_FLAG_PUBLIC = "public"

# Multi-word value keys — their value runs until the next ``key=`` token or a
# known bare flag (so ``body=Hello public`` does not swallow ``public``).
_MULTIWORD_KEYS = frozenset({_KEY_TITLE, _KEY_BODY})

# Bare-token flags — a multi-word value terminates when one appears.
_KNOWN_FLAGS = frozenset({_FLAG_PUBLIC})


def _require(value: str | None, name: str) -> str:
    if value is None or value == "":
        msg = f"{name} is required."
        raise CommandError(msg)
    return value


class CmdJournal(ArxCommand):
    """Write and respond to journal entries.

    Usage:
        journal                         — list your recent entries
        journal list                    — same as bare ``journal``
        journal write title=<text> body=<text> [public] [tags=a,b,c]
        journal respond <id|#> type=praise|retort title=<text> body=<text>
        journal edit <id|#> [title=<text>] [body=<text>]

    ``title`` / ``body`` are free text — their values run to the next
    ``key=`` token. ``public`` is a bare flag (entries are private by default).
    """

    key = "journal"
    aliases: list[str] = []
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        try:
            raw = (self.args or "").strip()
            if not raw or raw.lower() == _SUBVERB_LIST:
                self._show_recent()
                return
            parts = raw.split(maxsplit=1)
            subverb = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""
            if subverb == _SUBVERB_WRITE:
                self._write(rest)
            elif subverb == _SUBVERB_RESPOND:
                self._respond(rest)
            elif subverb == _SUBVERB_EDIT:
                self._edit(rest)
            else:
                self.msg(self._usage())
        except CommandError as err:
            self.msg(str(err))

    # -- write verbs ----------------------------------------------------------

    def _write(self, rest: str) -> None:
        kwargs, flags = parse_kv_and_flags(
            rest, multiword_keys=_MULTIWORD_KEYS, known_flags=_KNOWN_FLAGS
        )
        from actions.registry import get_action  # noqa: PLC0415

        title = _require(kwargs.get(_KEY_TITLE), _KEY_TITLE)
        body = _require(kwargs.get(_KEY_BODY), _KEY_BODY)
        tags_raw = kwargs.get(_KEY_TAGS)
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

        result = get_action("create_journal_entry").run(
            actor=self.caller,
            title=title,
            body=body,
            is_public=_FLAG_PUBLIC in flags,
            tags=tags,
        )
        if result.message:
            self.msg(result.message)

    def _respond(self, rest: str) -> None:
        target_id, kwargs = self._split_positional_and_kwargs(rest)
        if target_id is None:
            msg = "Usage: journal respond <id|#> type=praise|retort title=<text> body=<text>"
            raise CommandError(msg)
        from actions.registry import get_action  # noqa: PLC0415

        response_type = _require(kwargs.get(_KEY_TYPE), _KEY_TYPE)
        title = _require(kwargs.get(_KEY_TITLE), _KEY_TITLE)
        body = _require(kwargs.get(_KEY_BODY), _KEY_BODY)
        result = get_action("respond_to_journal").run(
            actor=self.caller,
            parent_id=target_id,
            response_type=response_type,
            title=title,
            body=body,
        )
        if result.message:
            self.msg(result.message)

    def _edit(self, rest: str) -> None:
        target_id, kwargs = self._split_positional_and_kwargs(rest)
        if target_id is None:
            msg = "Usage: journal edit <id|#> [title=<text>] [body=<text>]"
            raise CommandError(msg)
        from actions.registry import get_action  # noqa: PLC0415

        if _KEY_TITLE not in kwargs and _KEY_BODY not in kwargs:
            msg = "Provide at least one of title or body to edit."
            raise CommandError(msg)
        result = get_action("edit_journal_entry").run(
            actor=self.caller,
            entry_id=target_id,
            title=kwargs.get(_KEY_TITLE),
            body=kwargs.get(_KEY_BODY),
        )
        if result.message:
            self.msg(result.message)

    # -- read -----------------------------------------------------------------

    def _show_recent(self) -> None:
        from world.journals.models import JournalEntry  # noqa: PLC0415

        sheet = self._actor_sheet(self.caller)
        entries = list(
            JournalEntry.objects.filter(author=sheet, parent__isnull=True).order_by("-created_at")[
                :5
            ]
        )
        if not entries:
            self.msg("You have written no journal entries.")
            return
        lines = ["|wYour recent journal entries:|n"]
        lines.extend(f"  [#{e.pk}] {e.title}" for e in entries)
        lines.append("Use 'journal edit <id>' to revise one.")
        self.msg("\n".join(lines))

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _split_positional_and_kwargs(rest: str) -> tuple[int | None, dict[str, str]]:
        """Pull a leading positional ``<id>`` / ``#<id>`` off the front, then parse kwargs."""
        tokens = rest.split(maxsplit=1)
        if not tokens:
            return None, {}
        first = tokens[0].lstrip("#")
        if not first.isdigit():
            return None, {}
        remaining = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            remaining, multiword_keys=_MULTIWORD_KEYS, known_flags=_KNOWN_FLAGS
        )
        return int(first), kwargs

    @staticmethod
    def _actor_sheet(caller: Any) -> Any:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            sheet = caller.sheet_data
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = "No active character."
            raise CommandError(msg) from exc
        if sheet is None:
            msg = "No active character."
            raise CommandError(msg)
        return sheet

    def _usage(self) -> str:
        return (
            "Usage: journal [list|write title=<text> body=<text> [public] [tags=...]|"
            "respond <id|#> type=praise|retort title=<text> body=<text>|"
            "edit <id|#> [title=<text>] [body=<text>]]"
        )
