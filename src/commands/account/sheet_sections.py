"""Telnet ``sheet/<section>`` views (#1334+) — the sheet's sections, mirroring the web tabs.

The character sheet is the hub; each **section** is a part of a character you reference off it
(secrets first; renown, relationships, society/org standings, covenant, magic etc. as they're
built). A section is a renderer ``(command) -> list[str]``; register it in ``SHEET_SECTIONS``
keyed by its switch name. Each section reads the same services as its web tab, so the two faces
can't drift. ``CmdSheet`` dispatches ``sheet/<section>`` here; bare ``sheet`` shows the overview.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia import Command

    from world.character_sheets.models import CharacterSheet
    from world.secrets.models import Secret, SecretKnowledge

_UNKNOWN = "Unknown"
_NO_IDENTITY = "You have no active character to view sections with."


def _viewer_sheet(command: Command) -> CharacterSheet:
    """The active character's sheet (the viewer). Raises ``CommandError`` if there's no puppet."""
    try:
        return command.caller.puppet.sheet_data
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise CommandError(_NO_IDENTITY) from exc


def _resolve_target_sheet(command: Command, name: str) -> CharacterSheet | None:
    """Resolve a named character to its sheet; None when the search fails (already notified)."""
    target = command.caller.search(name, global_search=True)
    if target is None:
        return None
    try:
        return target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        command.caller.msg(f"{target} is not a character.")
        return None


def _render_secret_section(command: Command) -> list[str]:
    """The secrets section: your own secrets, or the ones you know about another character (#1334).

    Mirrors the web Secrets tab. Your own show in full; secrets about others render any layer you
    haven't uncovered as "Unknown". Scoped to the active (viewing) character.
    """
    from world.secrets.services import known_secrets_for, secrets_owned_by  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    arg = (command.args or "").strip()
    if not arg:
        return _render_own(secrets_owned_by(viewer))
    entry = viewer.roster_entry
    if entry is None:
        raise CommandError(_NO_IDENTITY)
    target_sheet = _resolve_target_sheet(command, arg)
    if target_sheet is None:
        return []
    return _render_known(known_secrets_for(entry, subject_sheet=target_sheet))


def _render_own(secrets: QuerySet[Secret]) -> list[str]:
    rows = list(secrets)
    if not rows:
        return ["You have no secrets of your own."]
    lines = ["|wYour secrets:|n"]
    for secret in rows:
        category = secret.category.name if secret.category_id else _UNKNOWN
        lines.append(f"  |c[{secret.get_level_display()}]|n {secret.content}")
        lines.append(
            f"      Category: {category} | Consequences: {secret.consequences or _UNKNOWN}"
        )
    return lines


def _render_known(held_rows: QuerySet[SecretKnowledge]) -> list[str]:
    rows = list(held_rows)
    if not rows:
        return ["You know none of their secrets."]
    lines = ["|wSecrets you know:|n"]
    for held in rows:
        secret = held.secret
        category = (
            secret.category.name if (held.knows_category and secret.category_id) else _UNKNOWN
        )
        consequences = (
            secret.consequences if (held.knows_consequences and secret.consequences) else _UNKNOWN
        )
        lines.append(f"  |c[{secret.get_level_display()}]|n {secret.content}")
        lines.append(f"      Category: {category} | Consequences: {consequences}")
    return lines


# Switch name → renderer. Add a section by writing a renderer and registering it here (and in
# SECTION_NAMES for the overview footer). Aliases (secret/secrets) map to the same renderer.
SHEET_SECTIONS: dict[str, Callable[..., list[str]]] = {
    "secret": _render_secret_section,
    "secrets": _render_secret_section,
}

# Canonical section names shown in the bare-``sheet`` footer (deduped; one per real section).
SECTION_NAMES: tuple[str, ...] = ("secret",)
