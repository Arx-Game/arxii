"""Shared justice-test helpers (#1825)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Bypass Evennia's at_db_location_postsave hook.

    Keeps setUpTestData attributes deepcopy-safe — a full ``.save()`` stashes an
    un-deepcopyable ``DbHolder`` on the identity-mapped instance, and Django's
    TestData descriptor deep-copies class attributes per test (shard-order
    dependent: passes alone, fails when earlier suites warm the cache). Mirrors
    ``actions.tests.test_dispatch_scene_tick._set_character_location``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    character.db_location = room
    return character
