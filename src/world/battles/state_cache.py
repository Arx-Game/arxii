"""Per-battle in-memory state cache (#1846).

BattleUnit/BattleParticipant/BattleSide/BattlePlace/Fortification/BattleVehicle
are all SharedMemoryModel -- once loaded, the live Python instance already
reflects current state (every mutation is followed by .save(), same as
before this cache existed). BattleStateCache exists to answer "which units
are on this side/place" without re-running a SQL WHERE clause every time --
a query the raw SharedMemoryModel identity map can't answer on its own,
because that map is keyed by pk across ALL battles, with no per-battle
membership index.

Never invalidated in production: built once (lazily, as a cold-start
fallback for a Battle instance that was evicted and reloaded -- e.g. after a
server restart) then maintained forever after by register_*() calls, which
BattleUnit/BattleParticipant/BattleSide/BattlePlace/Fortification/
BattleVehicle's own save() overrides call automatically on creation --
regardless of whether the row was created via a services.py function, a
factory, or the admin. No unregister_*() -- nothing hard-deletes these rows
(see #1846 spec, Decision 4). Index buckets key only on immutable structural
FKs (side_id, place_id); status filtering happens as an in-memory scan at
read time over already-current objects, so a status change never needs to
move an entry between buckets.

The one FK that DOES change post-creation is place (BattleUnit/
BattleParticipant.place is nulled by
world.battles.services.eject_vehicle_occupants when a vehicle's hull
breaches or a mount unit is destroyed) -- that explicit, known mutation
calls move_unit_place()/move_participant_place() alongside its own .save().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.battles.models import (
        Battle,
        BattleParticipant,
        BattlePlace,
        BattleSide,
        BattleUnit,
        BattleVehicle,
        Fortification,
    )


class BattleStateCache:
    """Per-battle roster index: units/participants/sides/places/fortifications/vehicles.

    One instance per live Battle, exposed via Battle.state_cache.
    """

    def __init__(self, battle: Battle) -> None:
        self._battle = battle
        self._loaded = False
        self._units_by_pk: dict[int, BattleUnit] = {}
        self._units_by_side: dict[int, list[BattleUnit]] = {}
        self._units_by_place: dict[int, list[BattleUnit]] = {}
        self._participants_by_pk: dict[int, BattleParticipant] = {}
        self._participants_by_side: dict[int, list[BattleParticipant]] = {}
        self._participants_by_place: dict[int, list[BattleParticipant]] = {}
        self._sides_by_pk: dict[int, BattleSide] = {}
        self._places_by_pk: dict[int, BattlePlace] = {}
        self._fortifications_by_place: dict[int, list[Fortification]] = {}
        self._vehicles_by_unit: dict[int, BattleVehicle] = {}
        self._vehicles_by_place: dict[int, BattleVehicle] = {}

    def _ensure_loaded(self) -> None:
        """Cold-start fallback: bulk-load this battle's rows once.

        Only fires for a BattleStateCache instance that has never run this
        method -- e.g. right after a server restart evicted the identity map
        and a Battle instance's .state_cache property builds a fresh
        BattleStateCache. In the common case (battle created and played out
        within one process lifetime), every row already arrived via
        register_*() from a save() override, and this loop finds the same
        rows again (each _index_* call is idempotent).
        """
        if self._loaded:
            return
        from world.battles.models import (  # noqa: PLC0415
            BattleParticipant,
            BattlePlace,
            BattleSide,
            BattleUnit,
            BattleVehicle,
            Fortification,
        )

        for side in BattleSide.objects.filter(battle=self._battle):
            self._index_side(side)
        for place in BattlePlace.objects.filter(battle=self._battle):
            self._index_place(place)
        for unit in BattleUnit.objects.filter(battle=self._battle):
            self._index_unit(unit)
        for participant in BattleParticipant.objects.filter(battle=self._battle):
            self._index_participant(participant)
        for fortification in Fortification.objects.filter(place__battle=self._battle):
            self._index_fortification(fortification)
        for vehicle in BattleVehicle.objects.filter(unit__battle=self._battle):
            self._index_vehicle(vehicle)
        self._loaded = True

    def _index_side(self, side: BattleSide) -> None:
        self._sides_by_pk[side.pk] = side

    def _index_place(self, place: BattlePlace) -> None:
        self._places_by_pk[place.pk] = place

    def _index_unit(self, unit: BattleUnit) -> None:
        self._units_by_pk[unit.pk] = unit
        bucket = self._units_by_side.setdefault(unit.side_id, [])
        if unit not in bucket:
            bucket.append(unit)
        if unit.place_id is not None:
            place_bucket = self._units_by_place.setdefault(unit.place_id, [])
            if unit not in place_bucket:
                place_bucket.append(unit)

    def _index_participant(self, participant: BattleParticipant) -> None:
        self._participants_by_pk[participant.pk] = participant
        bucket = self._participants_by_side.setdefault(participant.side_id, [])
        if participant not in bucket:
            bucket.append(participant)
        if participant.place_id is not None:
            place_bucket = self._participants_by_place.setdefault(participant.place_id, [])
            if participant not in place_bucket:
                place_bucket.append(participant)

    def _index_fortification(self, fortification: Fortification) -> None:
        bucket = self._fortifications_by_place.setdefault(fortification.place_id, [])
        if fortification not in bucket:
            bucket.append(fortification)

    def _index_vehicle(self, vehicle: BattleVehicle) -> None:
        self._vehicles_by_unit[vehicle.unit_id] = vehicle
        self._vehicles_by_place[vehicle.place_id] = vehicle

    # -- registration (called from model save() overrides on creation) --

    def register_side(self, side: BattleSide) -> None:
        self._ensure_loaded()
        self._index_side(side)

    def register_place(self, place: BattlePlace) -> None:
        self._ensure_loaded()
        self._index_place(place)

    def register_unit(self, unit: BattleUnit) -> None:
        self._ensure_loaded()
        self._index_unit(unit)

    def register_participant(self, participant: BattleParticipant) -> None:
        self._ensure_loaded()
        self._index_participant(participant)

    def register_fortification(self, fortification: Fortification) -> None:
        self._ensure_loaded()
        self._index_fortification(fortification)

    def register_vehicle(self, vehicle: BattleVehicle) -> None:
        self._ensure_loaded()
        self._index_vehicle(vehicle)

    # -- explicit maintenance for the one FK that changes post-creation --

    def move_unit_place(self, unit: BattleUnit, *, old_place_id: int | None) -> None:
        """Re-bucket *unit* after its .place FK changed (e.g. vehicle ejection).

        Call this right after unit.save(update_fields=["place"]) -- unit.place_id
        must already hold the NEW value when this is called.
        """
        self._ensure_loaded()
        if old_place_id is not None:
            bucket = self._units_by_place.get(old_place_id)
            if bucket is not None and unit in bucket:
                bucket.remove(unit)
        if unit.place_id is not None:
            self._units_by_place.setdefault(unit.place_id, []).append(unit)

    def move_participant_place(
        self, participant: BattleParticipant, *, old_place_id: int | None
    ) -> None:
        """Re-bucket *participant* after its .place FK changed (vehicle ejection)."""
        self._ensure_loaded()
        if old_place_id is not None:
            bucket = self._participants_by_place.get(old_place_id)
            if bucket is not None and participant in bucket:
                bucket.remove(participant)
        if participant.place_id is not None:
            self._participants_by_place.setdefault(participant.place_id, []).append(participant)

    # -- reads --

    def units_on_side(
        self, side_id: int, *, statuses: tuple[str, ...] | None = None
    ) -> list[BattleUnit]:
        self._ensure_loaded()
        units = self._units_by_side.get(side_id, [])
        return [u for u in units if statuses is None or u.status in statuses]

    def units_on_place(
        self, place_id: int, *, statuses: tuple[str, ...] | None = None
    ) -> list[BattleUnit]:
        self._ensure_loaded()
        units = self._units_by_place.get(place_id, [])
        return [u for u in units if statuses is None or u.status in statuses]

    def participants_on_side(
        self, side_id: int, *, statuses: tuple[str, ...] | None = None
    ) -> list[BattleParticipant]:
        self._ensure_loaded()
        participants = self._participants_by_side.get(side_id, [])
        return [p for p in participants if statuses is None or p.status in statuses]

    def participants_on_place(
        self, place_id: int, *, statuses: tuple[str, ...] | None = None
    ) -> list[BattleParticipant]:
        self._ensure_loaded()
        participants = self._participants_by_place.get(place_id, [])
        return [p for p in participants if statuses is None or p.status in statuses]

    def vehicle_at_place(self, place_id: int) -> BattleVehicle | None:
        self._ensure_loaded()
        return self._vehicles_by_place.get(place_id)

    def vehicle_for_unit(self, unit_id: int) -> BattleVehicle | None:
        self._ensure_loaded()
        return self._vehicles_by_unit.get(unit_id)
