"""Shared runtime check for the "no em/en dash in an identifier" rule (#3890).

A name is a lookup key in this codebase (CLAUDE.md): the dominant pattern is an
exact ``Model.objects.get(name=...)``, and an em or en dash is not on anyone's
keyboard, so a name containing one becomes unfindable by search while
``get_or_create`` on the hyphenated spelling silently mints a duplicate.

``tools/lint_identifier_dashes.py`` enforces this at commit time over literal
``name=``/``key=`` assignments in source and fixtures. This module is the
runtime counterpart for text a *player or staff member types* — there is no
commit-time literal to lint there. Named by code point, not written literally,
so no importer's source carries the dash character itself (#4099 promoted this
out of two private copies — ``web/admin/authoring/contributors.py`` and
``web/admin/authoring/views.py`` — rather than adding a third in
``world/magic/services/technique_personalization.py``).
"""

from __future__ import annotations

#: En dash, em dash.
DASH_CHARACTERS = ("–", "—")


def contains_dash(value: str) -> bool:
    """True if ``value`` contains an em or en dash."""
    return any(dash in value for dash in DASH_CHARACTERS)
