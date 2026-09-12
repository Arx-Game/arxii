"""Per-character attention counting for the top bar's unread badges (#3774).

Answers "what is waiting for each of this account's characters" so the badge
survives a change of device. Deliberately does NOT call
`InteractionQuerySet.visible_to`: its staff branch returns the whole game and
its player branch includes every public room-heard pose game-wide, either of
which would make a badge meaningless and disclose volume. The count is built
from rows that are already this account's own instead, which is both correctly
bounded and cheaper.

Five queries, none per character and none per row:
1. Directed unread across both directed-message through tables
   (`InteractionReceiver` and `InteractionTargetPersona`), combined with a
   single SQL UNION.
2. Which scenes the account still participates in (open, active), plus each
   scene's location id in the same query (needed for attribution query 3b).
3a. Which of the account's own characters actually posed in one of those
    scenes (attribution - `SceneParticipation` is account-scoped, not
    character-scoped, so pose authorship is one way to know which character
    an ambient scene belongs to).
3b. Which of the account's own characters are physically standing in one of
    those scenes' rooms right now, even if they never posed
    (`CharacterSheet` shares `ObjectDB`'s primary key, so `sheet_ids` are
    already `ObjectDB` pks - a plain `db_location_id__in` filter finds them
    with no extra lookup). This is a real gap posing-only attribution misses:
    a character who is present when a scene opens (or joins a combat
    encounter) gets a `SceneParticipation` row with zero posing required
    (`add_present_as_co_owners`, `ensure_scene_participation`), so a silent
    participant would otherwise never see the ambient badge that scene
    produces. The two attribution paths are UNIONed in Python; a scene with
    no location contributes only the pose-derived path.
4. Room-heard, unread, not-our-own poses in those scenes, one row per scene
   (a boolean plus a watermark, never the whole backlog).

Every filter below joins through `persona__character_sheet_id` directly
rather than resolving persona ids first, so no separate persona-lookup query
is needed, and the result rows already carry the exact key `by_character` is
keyed by.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import Exists, Max, OuterRef
from django.utils import timezone

from world.scenes.constants import DIRECTED_UNREAD_DAYS
from world.scenes.types import AccountAttention, CharacterAttention

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.roster.models import RosterEntry


def _presence_derived_attribution(
    *, open_scene_rows: list[tuple[int, int | None]], sheet_ids: Sequence[int]
) -> dict[int, set[int]]:
    """Which of our characters are standing in one of these scenes' rooms.

    Query 3b (Finding 1, #3774 final review): `add_present_as_co_owners()`
    (`scene_admin_services.py`) and `ensure_scene_participation()`
    (`interaction_services.py`, also called from combat-encounter join) both
    create a `SceneParticipation` row for everyone physically present, with
    zero posing required - so pose-only attribution (query 3a) silently drops
    the character who never posed, exactly the quiet one most likely to have
    something unread. `sheet_ids` are `ObjectDB` pks (`CharacterSheet` shares
    `ObjectDB`'s primary key), so this is a plain location filter, not a
    separate character lookup. A scene with no location contributes nothing.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    location_to_scenes: defaultdict[int, set[int]] = defaultdict(set)
    for scene_id, location_id in open_scene_rows:
        if location_id is not None:
            location_to_scenes[location_id].add(scene_id)
    if not location_to_scenes:
        return {}

    scene_to_sheets: defaultdict[int, set[int]] = defaultdict(set)
    present_rows = ObjectDB.objects.filter(
        id__in=sheet_ids, db_location_id__in=location_to_scenes.keys()
    ).values_list("id", "db_location_id")
    for sheet_id, location_id in present_rows:
        for scene_id in location_to_scenes[location_id]:
            scene_to_sheets[scene_id].add(sheet_id)
    return scene_to_sheets


def account_attention(*, account: AccountDB, entries: Sequence[RosterEntry]) -> AccountAttention:
    """What is waiting for each character in `entries`, for `account`.

    `entries` are the account's own roster entries; the caller
    (`RosterEntryViewSet.mine`) already resolves them, so this stays the one
    place that counts and never the place that decides who you play.
    """
    from world.scenes.managers import room_heard_q  # noqa: PLC0415
    from world.scenes.models import (  # noqa: PLC0415
        Interaction,
        InteractionReadReceipt,
        InteractionTargetPersona,
        SceneParticipation,
    )
    from world.scenes.place_models import InteractionReceiver  # noqa: PLC0415

    sheet_ids = [entry.character_sheet_id for entry in entries]
    if not sheet_ids:
        return AccountAttention(by_character={}, as_of_id=0)

    floor = timezone.now() - timedelta(days=DIRECTED_UNREAD_DAYS)

    # 1. Directed unread, across both directed-message through tables. Both
    # carry a denormalized `timestamp`, so the window applies without joining
    # the partitioned Interaction table. A single `.union()` executes as one
    # SQL query and dedupes any (character, interaction) pair the two tables
    # might agree on.
    receiver_rows = (
        InteractionReceiver.objects.filter(
            persona__character_sheet_id__in=sheet_ids, timestamp__gte=floor
        )
        .exclude(interaction__persona__character_sheet_id__in=sheet_ids)
        .filter(
            ~Exists(
                InteractionReadReceipt.objects.filter(
                    interaction_id=OuterRef("interaction_id"), account=account
                )
            )
        )
        .values_list("persona__character_sheet_id", "interaction_id")
    )
    target_rows = (
        InteractionTargetPersona.objects.filter(
            persona__character_sheet_id__in=sheet_ids, timestamp__gte=floor
        )
        .exclude(interaction__persona__character_sheet_id__in=sheet_ids)
        .filter(
            ~Exists(
                InteractionReadReceipt.objects.filter(
                    interaction_id=OuterRef("interaction_id"), account=account
                )
            )
        )
        .values_list("persona__character_sheet_id", "interaction_id")
    )
    direct_ids: defaultdict[int, set[int]] = defaultdict(set)
    for sheet_id, interaction_id in receiver_rows.union(target_rows):
        direct_ids[sheet_id].add(interaction_id)

    # 2. Scenes this account is still party to, with each scene's location id
    # carried along in the same query so query 3b needs no separate lookup.
    open_scene_rows = list(
        SceneParticipation.objects.filter(
            account=account, left_at__isnull=True, scene__is_active=True
        ).values_list("scene_id", "scene__location_id")
    )
    open_scene_ids = [scene_id for scene_id, _location_id in open_scene_rows]

    ambient_sheets: set[int] = set()
    as_of_id = 0
    if open_scene_ids:
        # 3a. Which of our characters actually posed in one of those scenes.
        # `SceneParticipation` is account-scoped, not character-scoped, so
        # this is one way to attribute an open scene to a specific character.
        scene_to_sheets: defaultdict[int, set[int]] = defaultdict(set)
        for scene_id, sheet_id in (
            Interaction.objects.filter(
                scene_id__in=open_scene_ids, persona__character_sheet_id__in=sheet_ids
            )
            .values_list("scene_id", "persona__character_sheet_id")
            .distinct()
        ):
            scene_to_sheets[scene_id].add(sheet_id)

        # 3b. Which of our characters are standing in one of those scenes'
        # rooms right now, even if they never posed (Finding 1, #3774 final
        # review). UNIONed into the same pose-derived map.
        presence_attribution = _presence_derived_attribution(
            open_scene_rows=open_scene_rows, sheet_ids=sheet_ids
        )
        for scene_id, present_sheet_ids in presence_attribution.items():
            scene_to_sheets[scene_id].update(present_sheet_ids)

        # 4. Room-heard, unread, not-our-own poses in those scenes - one row
        # per scene rather than one per pose (Ruling 1, #3774 task-2 brief):
        # a scene with a long backlog would otherwise stream thousands of
        # rows just to compute a boolean and a watermark. `room_heard_q()`
        # excludes any interaction with receiver rows or a place, and any
        # non-DEFAULT visibility, so a private aside in the same scene never
        # reaches this query.
        ambient_rows = (
            Interaction.objects.filter(room_heard_q(), scene_id__in=open_scene_ids)
            .exclude(persona__character_sheet_id__in=sheet_ids)
            .filter(
                ~Exists(
                    InteractionReadReceipt.objects.filter(
                        interaction_id=OuterRef("id"), account=account
                    )
                )
            )
            .values("scene_id")
            .annotate(newest=Max("id"))
        )
        for row in ambient_rows:
            as_of_id = max(as_of_id, row["newest"])
            ambient_sheets.update(scene_to_sheets.get(row["scene_id"], ()))

    for interaction_ids in direct_ids.values():
        as_of_id = max(as_of_id, max(interaction_ids, default=0))

    by_character = {
        sheet_id: CharacterAttention(
            direct=len(direct_ids.get(sheet_id, ())),
            ambient=sheet_id in ambient_sheets,
        )
        for sheet_id in sheet_ids
    }
    return AccountAttention(by_character=by_character, as_of_id=as_of_id)
