"""Inventory mutation service functions.

Used by both telnet commands and the WebSocket ``inventory_action``
inputfunc. All mutations run inside ``transaction.atomic`` so partial
failures roll back fully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.items.constants import OwnershipEventType
from world.items.exceptions import (
    ContainerAccessDenied,
    ContainerClosed,
    ContainerFull,
    ItemTooLarge,
    NoDropLocation,
    NotAContainer,
    NotEquipped,
    NotInContainer,
    NotInPossession,
    NotReachable,
    OwnedByAnother,
    RecipientNotAdjacent,
    TheftNotPermitted,
)
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services import equip_item, unequip_item

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.justice.models import CrimeKind
    from world.roster.models import RosterTenure
    from world.societies.models import LegendSourceType


def _active_tenure_for_sheet(sheet: CharacterSheet) -> RosterTenure | None:
    """Return ``sheet``'s active ``RosterTenure`` (end_date null), or None for NPCs (#1909).

    Mirrors the dispatch layer's sheet→active-tenure resolution
    (``actions.player_interface``). An NPC-owned sheet has no live tenure.
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet=sheet,
        end_date__isnull=True,
    ).first()


def _container_policy_denies(taker_sheet: CharacterSheet, container_instance: ItemInstance) -> bool:
    """True when the container's access policy bars ``taker_sheet`` from its contents.

    Only the IMMEDIATE ``contained_in`` container's policy governs — no ancestor
    chaining up nested containers (per the #1909 spec).
    """
    from world.items.constants import ContainerAccessPolicy  # noqa: PLC0415

    owner_sheet = container_instance.holder_character_sheet
    policy = container_instance.access_policy
    if policy == ContainerAccessPolicy.OPEN or owner_sheet is None:
        return False
    if owner_sheet.pk == taker_sheet.pk:
        return False
    if policy == ContainerAccessPolicy.OWNER_ONLY:
        return True
    # FRIENDS: resolve both sides to active tenures; NPC sides have none → deny.
    owner_tenure = _active_tenure_for_sheet(owner_sheet)
    taker_tenure = _active_tenure_for_sheet(taker_sheet)
    if owner_tenure is None or taker_tenure is None:
        return True
    from world.scenes.friend_services import is_friend  # noqa: PLC0415

    return not is_friend(owner_tenure=owner_tenure, friend_tenure=taker_tenure)


def take_requires_steal(taker_sheet: CharacterSheet | None, item_instance: ItemInstance) -> bool:
    """The one ownership/policy test (#1909): True → only ``steal`` may move it.

    Room item owned by someone else → steal. Container item: the container's
    policy decides; policy pass → plain take even if the item belongs to the
    container's owner (sanctioned borrowing).
    """
    if taker_sheet is None:
        # Sheet-less actors (GM/staff/companion tooling) keep legacy free-take
        # behavior — theft consequence machinery is sheet-anchored and cannot
        # apply to them.
        return False
    container = item_instance.contained_in
    if container is not None:
        return _container_policy_denies(taker_sheet, container)
    owner = item_instance.holder_character_sheet
    return owner is not None and owner.pk != taker_sheet.pk


def _fire_item_acquisition_triggers(acquirer: CharacterState, item: ItemState) -> None:
    """Fire passive item-acquisition clue triggers for ``acquirer`` after commit (#1160).

    Scheduled with ``transaction.on_commit`` so the transfer is durable first and a trigger
    hiccup can never roll it back; wrapped in ``run_safely`` so a failure is captured for
    staff (not swallowed) without surfacing as a broken give/pick-up. The clue service's own
    cheap "any triggers for this kind?" query short-circuits ordinary items.
    """
    character_obj = acquirer.obj
    instance = item.instance

    def _run() -> None:
        from world.clues.services import maybe_grant_item_acquisition_clues  # noqa: PLC0415
        from world.player_submissions.services import run_safely  # noqa: PLC0415

        run_safely(
            "item_acquisition_clue_triggers",
            lambda: maybe_grant_item_acquisition_clues(character_obj, instance),
            actor=character_obj,
        )

    transaction.on_commit(_run)


@transaction.atomic
def pick_up(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from its current location into ``character``'s possession.

    If the item is currently unowned (``holder_character_sheet`` is null),
    ``character``'s body (CharacterSheet) becomes the holder. Pre-existing
    ownership is preserved. If the item is in an open container in the
    room, ``contained_in`` is cleared so the item ends up plainly in the
    character's inventory.

    The #1909 ownership/policy gate runs before any mutation: a room item
    owned by someone else raises ``OwnedByAnother``; a container item barred
    by the container's access policy raises ``ContainerAccessDenied``. Steal
    (a later task) is the deliberate bypass.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    taker_sheet = getattr(character.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if take_requires_steal(taker_sheet, item.instance):
        if item.instance.contained_in is not None:
            raise ContainerAccessDenied
        raise OwnedByAnother
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
    previous_location = item.instance.game_object.location
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    # Sheet-less actors can't own things — skip the assignment (holder stays None).
    if item.instance.holder_character_sheet_id is None and taker_sheet is not None:
        item.instance.holder_character_sheet = taker_sheet
        item.instance.save(update_fields=["holder_character_sheet"])
    character.obj.carried_items.invalidate()
    # If the item came from another character (rare), invalidate that too.
    # Rooms/containers don't have ``carried_items`` — only characters do.
    if (
        previous_location is not None
        and previous_location.pk != character.obj.pk
        and hasattr(previous_location, "carried_items")
    ):
        previous_location.carried_items.invalidate()
    _fire_item_acquisition_triggers(character, item)


@transaction.atomic
def drop(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` from ``character``'s possession into their current room.

    If the item is currently equipped, all ``EquippedItem`` rows are
    removed first via ``world.items.services.unequip_item`` so the
    character's cached equipment handler is invalidated correctly. If the
    item is in a container in the character's inventory, ``contained_in``
    is cleared as part of the drop.
    """
    if not item.can_drop(dropper=character):
        raise NotInPossession
    if character.obj.location is None:
        raise NoDropLocation
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    for equipped in list(item.instance.equipped_slots.all()):
        unequip_item(equipped_item=equipped)
    if not item.instance.game_object.move_to(character.obj.location, quiet=True):
        raise NotReachable
    character.obj.carried_items.invalidate()


@transaction.atomic
def give(
    giver: CharacterState,
    recipient: CharacterState,
    item: ItemState,
) -> None:
    """Transfer ``item`` from ``giver`` to ``recipient``.

    Writes an ``OwnershipEvent(GIVEN)`` row, transfers the holder
    (CharacterSheet — the body), and moves the underlying ``ObjectDB``
    to the recipient. Auto-unequips if the item is currently equipped.
    The OwnershipEvent also snapshots each side's presented persona for
    IC-narrative purposes; the audit truth is the CharacterSheet pair.
    """
    if not item.can_give(giver=giver, recipient=recipient):
        raise NotInPossession
    if recipient.obj.location != giver.obj.location:
        raise RecipientNotAdjacent

    previous_holder_sheet = item.instance.holder_character_sheet
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    for equipped in list(item.instance.equipped_slots.all()):
        unequip_item(equipped_item=equipped)

    if not item.instance.game_object.move_to(recipient.obj, quiet=True):
        raise NotReachable
    recipient_sheet = recipient.obj.sheet_data
    item.instance.holder_character_sheet = recipient_sheet
    item.instance.save(update_fields=["holder_character_sheet"])
    # Snapshot the IC face each side is wearing at the transfer moment.
    # Null falls back to the sheet's primary_persona at render time.
    giver_persona = (
        previous_holder_sheet.primary_persona if previous_holder_sheet is not None else None
    )
    OwnershipEvent.objects.create(
        item_instance=item.instance,
        event_type=OwnershipEventType.GIVEN,
        from_character_sheet=previous_holder_sheet,
        to_character_sheet=recipient_sheet,
        from_persona_display=giver_persona,
        to_persona_display=recipient_sheet.primary_persona,
    )
    giver.obj.carried_items.invalidate()
    recipient.obj.carried_items.invalidate()
    _fire_item_acquisition_triggers(recipient, item)


@transaction.atomic
def equip(character: CharacterState, item: ItemState) -> None:
    """Equip ``item`` on ``character`` in every slot its template declares.

    For each declared slot, if the same (body_region, equipment_layer) is
    already occupied on this character by a different item, that item is
    unequipped first (auto-swap). Different layers at the same body region
    are left alone. Multi-region items create one row per region atomically.
    """
    if not item.can_equip(wearer=character):
        raise NotInPossession

    sheet = character.obj.sheet_data
    for slot in item.instance.template.cached_slots:
        existing = EquippedItem.objects.filter(
            character=character.obj,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        ).first()
        if existing is not None:
            if existing.item_instance == item.instance:
                # Already equipped here — re-equip is a silent no-op.
                continue
            unequip_item(equipped_item=existing)
        equip_item(
            character_sheet=sheet,
            item_instance=item.instance,
            body_region=slot.body_region,
            equipment_layer=slot.equipment_layer,
        )


@transaction.atomic
def unequip(character: CharacterState, item: ItemState) -> None:
    """Remove all ``EquippedItem`` rows for ``item`` on ``character``.

    Raises ``NotEquipped`` if the item has no equipped rows. The item
    stays in the character's inventory — its underlying ``ObjectDB``
    location is unchanged.
    """
    # Snapshot rows before iteration — unequip_item deletes them as we go.
    equipped_rows = list(item.instance.equipped_slots.filter(character=character.obj))
    if not equipped_rows:
        raise NotEquipped
    for row in equipped_rows:
        unequip_item(equipped_item=row)


@transaction.atomic
def put_in(
    character: CharacterState,
    item: ItemState,
    container: ItemState,
) -> None:
    """Move ``item`` into ``container`` (an item that is itself a container).

    Validates the container is reachable by ``character``, the container's
    template/state, and the item's possession by ``character``. Sets
    ``item.contained_in = container`` and moves the underlying ``ObjectDB``
    into the container's ``ObjectDB`` so Evennia's ``look``/contents traversal
    sees the item as being inside the container.
    """
    if not container.is_reachable_by(character.obj):
        raise NotReachable
    container_template = container.instance.template
    if not container_template.is_container:
        raise NotAContainer
    if container_template.supports_open_close and not container.instance.is_open:
        raise ContainerClosed
    if (
        container_template.container_capacity
        and container.instance.contents.count() >= container_template.container_capacity
    ):
        raise ContainerFull
    if (
        container_template.container_max_item_size
        and item.instance.template.size > container_template.container_max_item_size
    ):
        raise ItemTooLarge
    if item.instance.game_object.location != character.obj:
        raise NotInPossession

    item.instance.contained_in = container.instance
    item.instance.save(update_fields=["contained_in"])
    if not item.instance.game_object.move_to(container.instance.game_object, quiet=True):
        raise NotReachable
    # Item moved off the character (now nested in the container's game_object),
    # so the carried-items cache for the character is stale.
    character.obj.carried_items.invalidate()


@transaction.atomic
def take_out(character: CharacterState, item: ItemState) -> None:
    """Move ``item`` out of its container into ``character``'s possession.

    Validates the item is reachable (which walks the container chain and
    rejects closed containers) and that it actually has a ``contained_in``
    set. Clears ``contained_in`` and moves the underlying ``ObjectDB`` to
    the character.

    The #1909 gate runs before any mutation: if the container's access
    policy bars this taker, raises ``ContainerAccessDenied``. Steal (a
    later task) is the deliberate bypass.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    if item.instance.contained_in is None:
        raise NotInContainer
    taker_sheet = getattr(character.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if take_requires_steal(taker_sheet, item.instance):
        raise ContainerAccessDenied
    item.instance.contained_in = None
    item.instance.save(update_fields=["contained_in"])
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    # Item now located on character — invalidate so the next read sees it.
    character.obj.carried_items.invalidate()


def _theft_crime_kind() -> CrimeKind:
    """Lazy CrimeKind row (repo bans seed migrations; _instrument_template precedent)."""
    from world.justice.models import CrimeKind  # noqa: PLC0415

    kind, _ = CrimeKind.objects.get_or_create(
        slug="theft",
        defaults={"name": "Theft", "description": "Taking what belongs to another."},
    )
    return kind


def _theft_source_type() -> LegendSourceType:
    """Lazy ``LegendSourceType`` row for personal antagonistic acts (#1909).

    ``LegendSourceType`` has no fixed enum of members — rows are normally
    admin/fixture-seeded data (fixtures aren't in version control, ADR-0013
    bans seed migrations), so no committed "existing member" can be grepped.
    Mirrors the ``_theft_crime_kind`` / ``theft_category`` lazy-row idiom
    already established for this exact situation: get-or-create a general
    "Crime" bucket (deliberately not a bespoke "Theft" source type, so future
    non-theft misdeeds land in the same category instead of fragmenting it).
    """
    from world.societies.models import LegendSourceType  # noqa: PLC0415

    source_type, _ = LegendSourceType.objects.get_or_create(
        name="Crime",
        defaults={"description": "Personal antagonistic acts against another persona."},
    )
    return source_type


def _record_theft_deed(character: CharacterState, item: ItemState) -> None:
    """Birth the crime-tagged, concealed deed for a completed theft (#1909).

    Called synchronously inside ``steal``'s atomic transaction — matches
    ``create_solo_deed``'s own callers (e.g. ``societies/scandal.py``'s
    ``route_deed_reach``/``_tag_approach_crime``), none of which defer via
    ``transaction.on_commit``; ``create_solo_deed`` is itself fully
    synchronous (its own ``@transaction.atomic``), so there is nothing to
    protect by deferring here. No active scene at the room -> ``scene=None``
    and the theft spreads cold (spec behavior, #1909 Step 1c).
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    taker_sheet = character.obj.sheet_data
    persona = active_persona_for_sheet(taker_sheet)
    scene = get_active_scene(character.obj.location)
    create_solo_deed(
        persona,
        f"Theft of {item.instance.display_name}",
        _theft_source_type(),
        10,
        scene=scene,
        crime_kinds=[_theft_crime_kind()],
        concealed=True,
    )


def steal_permitted(taker_sheet: CharacterSheet | None, item_instance: ItemInstance) -> bool:
    """Target-side-only availability (#1909): NPC-owned always; players by consent."""
    if not take_requires_steal(taker_sheet, item_instance):
        return False
    # take_requires_steal returns False for a None sheet (checked above), so
    # taker_sheet is guaranteed non-None past this point — narrowed explicitly
    # for the type checker, which can't see across the function call.
    if taker_sheet is None:  # pragma: no cover - unreachable, narrows for ty
        return False
    owner_sheet = item_instance.holder_character_sheet
    guarded_sheet = owner_sheet
    if guarded_sheet is None and item_instance.contained_in is not None:
        guarded_sheet = item_instance.contained_in.holder_character_sheet
    if guarded_sheet is None:
        return True
    owner_tenure = _active_tenure_for_sheet(guarded_sheet)
    if owner_tenure is None:
        return True  # NPC/org holdings: always antagonism-allowed (spec decision 5)
    from world.consent.services import consent_blocks_targeting, theft_category  # noqa: PLC0415

    taker_tenure = _active_tenure_for_sheet(taker_sheet)
    return not consent_blocks_targeting(
        owner_tenure=owner_tenure, category=theft_category(), actor_tenure=taker_tenure
    )


@transaction.atomic
def steal(character: CharacterState, item: ItemState) -> None:
    """Take an item that plain take refuses (#1909) — with consequences.

    Ownership transfers (STOLEN provenance, never destroyed, #1025) and the
    act births a crime-tagged deed for the thief's presented persona;
    ``concealed=True`` rolls Stealth to shed witnesses (#1824), so an
    unwitnessed theft spreads cold until discovered.
    """
    if not item.can_take(taker=character):
        raise NotReachable
    # getattr, not direct access: sheet-less actors (GM/staff/companion tooling)
    # have no reverse CharacterSheet row and must reach ``steal_permitted`` with
    # None rather than raise DoesNotExist — steal_permitted then delegates to
    # take_requires_steal, which returns False for a None sheet, so a
    # sheet-less actor always ends up refused here (they free-take instead).
    taker_sheet = getattr(character.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if not steal_permitted(taker_sheet, item.instance):
        raise TheftNotPermitted
    previous_holder_sheet = item.instance.holder_character_sheet
    if item.instance.contained_in is not None:
        item.instance.contained_in = None
        item.instance.save(update_fields=["contained_in"])
    if not item.instance.game_object.move_to(character.obj, quiet=True):
        raise NotReachable
    item.instance.holder_character_sheet = taker_sheet
    item.instance.save(update_fields=["holder_character_sheet"])
    OwnershipEvent.objects.create(
        item_instance=item.instance,
        event_type=OwnershipEventType.STOLEN,
        from_character_sheet=previous_holder_sheet,
        to_character_sheet=taker_sheet,
        from_persona_display=(
            previous_holder_sheet.primary_persona if previous_holder_sheet else None
        ),
        to_persona_display=taker_sheet.primary_persona,
    )
    character.obj.carried_items.invalidate()
    _record_theft_deed(character, item)
    _fire_item_acquisition_triggers(character, item)


@transaction.atomic
def set_container_policy(character: CharacterState, container: ItemState, policy: str) -> None:
    """Owner-only: set who may take from this container (#1909)."""
    from world.items.constants import ContainerAccessPolicy  # noqa: PLC0415

    if not container.instance.template.is_container:
        raise NotAContainer
    owner = container.instance.holder_character_sheet
    if owner is None or owner.pk != character.obj.sheet_data.pk:
        raise NotInPossession
    container.instance.access_policy = ContainerAccessPolicy(policy)
    container.instance.save(update_fields=["access_policy"])
