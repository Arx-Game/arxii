"""Realm reads (#3725).

The realm page is a read surface: nothing here writes. ``realm_by_slug`` is the one
lookup the route, the roster filter and the tests share; the slug is derived from the
name over a handful of rows, so there is no stored slug column to keep in step.
"""

from __future__ import annotations

from world.realms.models import Realm


def realm_by_slug(slug: str) -> Realm | None:
    """The realm whose ``slug`` (slugified name) is ``slug``, or None."""
    for realm in Realm.objects.all():
        if realm.slug == slug:
            return realm
    return None
