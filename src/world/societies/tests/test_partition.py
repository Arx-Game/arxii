"""Partitioning a drawn footprint into contiguous children (#4983 slice 2, #4986):
pure geometry, no database."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.societies.houses.partition import (
    Pip,
    centroid_land,
    farthest_pips,
    partition,
)


def rectangle(width: int, height: int) -> set[Pip]:
    return {(x, y) for x in range(width) for y in range(height)}


def connected(pips: set[Pip]) -> bool:
    """4-connected: every pip reachable from the first by orthogonal steps."""
    if not pips:
        return True
    start = next(iter(pips))
    seen = {start}
    frontier = [start]
    while frontier:
        x, y = frontier.pop()
        for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if step in pips and step not in seen:
                seen.add(step)
                frontier.append(step)
    return seen == pips


class PartitionTests(SimpleTestCase):
    def test_regions_are_contiguous_and_cover_the_footprint(self) -> None:
        pips = rectangle(20, 12)
        regions = partition(pips, pips, 3, [2.0, 1.0, 1.0], seed_hint=(3, 3), rng_seed=7)
        assert len(regions) == 3
        assert set().union(*regions) == pips
        assert sum(len(r) for r in regions) == len(pips)
        for region in regions:
            assert connected(region), region
        assert (3, 3) in regions[0]
        assert len(regions[0]) > max(len(regions[1]), len(regions[2]))

    def test_water_goes_to_the_region_it_touches_most(self) -> None:
        pips = rectangle(20, 10)
        lake = {(x, y) for x in range(8, 12) for y in range(4, 6)}
        land = pips - lake
        regions = partition(pips, land, 2, [1.0, 1.0], seed_hint=(1, 1), rng_seed=1)
        assert set().union(*regions) == pips
        for region in regions:
            assert connected(region & land)
        for pip in lake:
            holder = next(r for r in regions if pip in r)
            x, y = pip
            touching = sum(
                step in holder for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            )
            assert touching >= 1

    def test_two_islands_stay_contiguous(self) -> None:
        west = rectangle(6, 6)
        east = {(x + 12, y) for (x, y) in rectangle(6, 6)}
        strait = {(x, y) for x in range(6, 12) for y in range(6)}
        pips = west | east | strait
        land = west | east
        regions = partition(pips, land, 2, [1.0, 1.0], seed_hint=(0, 0), rng_seed=3)
        assert set().union(*regions) == pips
        for region in regions:
            assert connected(region & land), region & land
        assert {frozenset(r & land) for r in regions} == {frozenset(west), frozenset(east)}

    def test_too_little_land_gives_fewer_regions(self) -> None:
        pips = {(0, 0), (1, 0), (2, 0)}
        regions = partition(pips, pips, 5, [1.0] * 5, seed_hint=None, rng_seed=0)
        assert len(regions) == 3
        assert all(regions)

    def test_no_land_gives_no_regions(self) -> None:
        pips = rectangle(4, 4)
        assert partition(pips, set(), 2, [1.0, 1.0], seed_hint=None, rng_seed=0) == []

    def test_determinism(self) -> None:
        pips = rectangle(15, 9)
        first = partition(pips, pips, 4, [1.5, 1.0, 1.0, 1.0], seed_hint=None, rng_seed=11)
        second = partition(pips, pips, 4, [1.5, 1.0, 1.0, 1.0], seed_hint=None, rng_seed=11)
        assert first == second

    def test_centroid_and_farthest_pips(self) -> None:
        pips = rectangle(9, 9)
        assert centroid_land(pips, pips) == (4, 4)
        assert centroid_land(pips, set()) is None
        far = farthest_pips(pips, (0, 0), 2)
        assert far[0] == (8, 8)
        assert len(far) == 2
        assert far[1] != far[0]
        assert farthest_pips({(0, 0)}, (0, 0), 3) == []
