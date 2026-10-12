"""Bulk primary-level lookup for characters."""

from __future__ import annotations


def _bulk_primary_levels(char_ids: list[int]) -> dict[int, int]:
    """Return {character_id: level} for each id in *char_ids* using at most two queries.

    Mirrors the fallback chain in ``get_character_path_level``:
    primary row → highest row → 1.  Characters with no CharacterClassLevel at
    all are omitted from the dict (callers use ``.get(cid, 1)`` for the final
    fallback).
    """
    from world.classes.models import CharacterClassLevel  # noqa: PLC0415

    level_map: dict[int, int] = dict(
        CharacterClassLevel.objects.filter(
            character_id__in=char_ids,
            is_primary=True,
        ).values_list("character_id", "level")
    )

    without_primary = [cid for cid in char_ids if cid not in level_map]
    if without_primary:
        seen: set[int] = set()
        for char_id, lvl in (
            CharacterClassLevel.objects.filter(character_id__in=without_primary)
            .order_by("character_id", "-level")
            .values_list("character_id", "level")
        ):
            if char_id not in seen:
                level_map[char_id] = lvl
                seen.add(char_id)
    return level_map
