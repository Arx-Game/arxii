"""Tiling a drawn footprint into even counties and grouping them into duchies (#4983
slice 2, #4986; bottom-up since #5029): pure geometry, no database."""

from __future__ import annotations

from django.test import SimpleTestCase

from world.societies.houses.partition import (
    Pip,
    centroid_land,
    farthest_pips,
    group,
    lay_out_land,
    tile,
)


def rectangle(width: int, height: int, *, at: Pip = (0, 0)) -> set[Pip]:
    ox, oy = at
    return {(ox + x, oy + y) for x in range(width) for y in range(height)}


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


def within(sizes: list[int], target: float, tolerance: float) -> bool:
    return all(abs(size - target) <= target * tolerance for size in sizes)


class TileTests(SimpleTestCase):
    def test_tiles_are_even_cover_the_footprint_and_hold_the_seat(self) -> None:
        pips = rectangle(20, 12)
        tiles = tile(pips, pips, 6, seed_hint=(3, 3), rng_seed=7)
        assert len(tiles) == 6
        assert set().union(*tiles) == pips
        assert sum(len(t) for t in tiles) == len(pips)
        assert (3, 3) in tiles[0]
        assert within([len(t) for t in tiles], 40, 0.25), [len(t) for t in tiles]
        for t in tiles:
            assert connected(t), t

    def test_an_offshore_island_joins_a_mainland_county(self) -> None:
        # the owner's Norbyria: a coast and an 8-pip island across a strait. On the
        # top-down split the island became a duchy of its own (#5029).
        mainland = rectangle(20, 10)
        strait = rectangle(3, 10, at=(20, 0))
        island = rectangle(4, 2, at=(23, 4))
        pips = mainland | strait | island
        land = mainland | island
        tiles = tile(pips, land, 6, seed_hint=(2, 2), rng_seed=3)
        assert len(tiles) == 6
        assert set().union(*tiles) == pips
        holders = {next(i for i, t in enumerate(tiles) if pip in t) for pip in island}
        assert len(holders) == 1, holders
        [holder] = holders
        assert tiles[holder] & mainland, "the island is part of a mainland county, not its own"
        assert within([len(t & land) for t in tiles], len(land) / 6, 0.3), [
            len(t & land) for t in tiles
        ]

    def test_a_landmass_the_size_of_a_county_stays_whole(self) -> None:
        big = rectangle(10, 10)
        small = rectangle(6, 6, at=(14, 2))
        water = rectangle(4, 10, at=(10, 0))
        pips = big | small | water
        land = big | small
        tiles = tile(pips, land, 4, seed_hint=(1, 1), rng_seed=5)
        assert len(tiles) == 4
        assert any(t & land == small for t in tiles), [sorted(t & land)[:3] for t in tiles]
        for t in tiles:
            if t & land != small:
                assert (t & land) <= big

    def test_two_counties_on_one_island_split_it_evenly(self) -> None:
        # two islands of 100 and three counties: one island carries two, and those two are
        # halves, not a centre piece and a corner (the round-2 challenge on #5032: 39/61)
        west = rectangle(10, 10)
        east = rectangle(10, 10, at=(20, 0))
        pips = rectangle(30, 10)
        land = west | east
        tiles = tile(pips, land, 3, seed_hint=None, rng_seed=5)
        assert len(tiles) == 3
        on_west = sorted(len(t & west) for t in tiles if t & west)
        on_east = sorted(len(t & east) for t in tiles if t & east)
        split, whole = (on_west, on_east) if len(on_west) == 2 else (on_east, on_west)
        assert whole == [100], (on_west, on_east)
        assert split[1] - split[0] <= 10, split

    def test_water_goes_to_the_tile_it_touches(self) -> None:
        pips = rectangle(20, 10)
        lake = rectangle(4, 2, at=(8, 4))
        land = pips - lake
        tiles = tile(pips, land, 2, seed_hint=(1, 1), rng_seed=1)
        assert set().union(*tiles) == pips
        for pip in lake:
            holder = next(t for t in tiles if pip in t)
            x, y = pip
            assert any(step in holder for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    def test_too_little_land_gives_fewer_tiles_and_no_land_gives_none(self) -> None:
        pips = {(0, 0), (1, 0), (2, 0)}
        tiles = tile(pips, pips, 5, seed_hint=None, rng_seed=0)
        assert len(tiles) == 3
        assert all(tiles)
        assert tile(rectangle(4, 4), set(), 2, seed_hint=None, rng_seed=0) == []

    def test_disconnected_land_is_covered_without_overlapping(self) -> None:
        land = rectangle(8, 4) | rectangle(3, 3, at=(12, 0))
        tiles = tile(land, land, 4, seed_hint=(0, 0), rng_seed=13)
        assert set().union(*tiles) == land
        assert sum(map(len, tiles)) == len(land)
        assert all(tiles)

    def test_determinism(self) -> None:
        pips = rectangle(15, 9)
        first = tile(pips, pips, 4, seed_hint=None, rng_seed=11)
        second = tile(pips, pips, 4, seed_hint=None, rng_seed=11)
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


class GroupTests(SimpleTestCase):
    def test_groups_hold_the_capital_tile_and_take_their_counts_from_neighbours(self) -> None:
        pips = rectangle(24, 12)
        tiles = tile(pips, pips, 8, seed_hint=(2, 2), rng_seed=2)
        groups = group(tiles, [4, 2, 2], pips)
        assert [len(g) for g in groups] == [4, 2, 2]
        assert 0 in groups[0]
        assert sorted(i for g in groups for i in g) == list(range(8))
        for g in groups:
            assert connected(set().union(*(tiles[i] for i in g))), g

    def test_counts_are_fitted_when_there_are_fewer_tiles(self) -> None:
        pips = rectangle(6, 1)
        tiles = tile(pips, pips, 3, seed_hint=None, rng_seed=0)
        groups = group(tiles, [4, 2, 2, 2], pips)
        assert len(groups) == 3
        assert all(len(g) == 1 for g in groups)


class LayOutLandTests(SimpleTestCase):
    def test_duchies_are_groups_of_even_counties_with_the_capital_largest(self) -> None:
        pips = rectangle(24, 12)
        duchies = lay_out_land(pips, pips, [4, 2, 2, 2], seed_hint=(2, 2), rng_seed=9)
        assert [len(d) for d in duchies] == [4, 2, 2, 2]
        sizes = [sum(len(c) for c in d) for d in duchies]
        assert sizes[0] > max(sizes[1:]), sizes
        assert set().union(*(c for d in duchies for c in d)) == pips
        assert (2, 2) in duchies[0][0]

    def test_an_archipelago_gets_duchies_sized_by_their_counties(self) -> None:
        # ten islands of 25 land each in a sea: Inferna's shape (#5029)
        islands = [rectangle(5, 5, at=(x * 8, y * 8)) for x in range(5) for y in range(2)]
        land = set().union(*islands)
        pips = rectangle(37, 13)
        assert land <= pips
        duchies = lay_out_land(pips, land, [4, 2, 2, 2], seed_hint=(1, 1), rng_seed=4)
        assert [len(d) for d in duchies] == [4, 2, 2, 2]
        owned = set().union(*(c for d in duchies for c in d))
        assert land <= owned
        sizes = [sum(len(c & land) for c in d) for d in duchies]
        assert within(sizes[:1], 100, 0.3), sizes
        assert within(sizes[1:], 50, 0.3), sizes
        for d in duchies:
            for county in d:
                assert county & land, "every county holds land"

    def test_duchies_follow_the_weights_in_land_where_whole_islands_allow(self) -> None:
        # eight islands of 100 and counties 4, 2, 2, 2: ten pieces, six whole islands and four
        # halves. Even pips first (owner): the capital takes wholes and halves toward 320, the
        # others toward 160, so no duchy sits at 100 while another holds 200 (#5032 round 3)
        cells = [(cx, cy) for cx in range(4) for cy in range(4) if (cx + cy) % 2 == 0]
        islands = [rectangle(10, 10, at=(cx * 10, cy * 10)) for cx, cy in cells]
        land = set().union(*islands)
        pips = rectangle(40, 40)
        duchies = lay_out_land(pips, land, [4, 2, 2, 2], seed_hint=(1, 1), rng_seed=5)
        sizes = [sum(len(c & land) for c in d) for d in duchies]
        assert [len(d) for d in duchies] == [4, 2, 2, 2]
        assert within(sizes[:1], 320, 0.15), sizes
        assert within(sizes[1:], 160, 0.15), sizes

    def test_too_little_land_gives_fewer_duchies_each_with_a_county(self) -> None:
        pips = {(0, 0), (1, 0), (2, 0)}
        duchies = lay_out_land(pips, pips, [2, 2, 2], seed_hint=None, rng_seed=0)
        assert 1 <= len(duchies) <= 3
        assert all(d and all(c for c in d) for d in duchies)
        assert lay_out_land(rectangle(4, 4), set(), [2, 2], seed_hint=None, rng_seed=0) == []
