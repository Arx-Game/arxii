"""Tile a drawn footprint into even counties and group them into duchies (#4983 slice 2,
#4986; built bottom-up since #5029).

Pure geometry over pips, no database: the layout walk hands in a kingdom's footprint and
how many counties each duchy takes, and gets back one group of county regions per duchy.
Counties are even in pips, so a duchy is never smaller than its county count says; a county
or a duchy may span water when the land does (an island too small to be a county joins the
nearest one, a landmass about a county's size stays whole), and the capital's county holds
the seat. The owner clips the result with the map's Brush, Loop and Adjust afterwards; this
only has to be even and sensible, never pretty. The top-down split it replaces made an
8-pip island a duchy of its own, because farthest-point seeding ignored landmass size and
growth never crossed water (#5029).
"""

from __future__ import annotations

from collections import defaultdict
import zlib

Pip = tuple[int, int]


def _neighbours(pip: Pip) -> tuple[Pip, Pip, Pip, Pip]:
    x, y = pip
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def centroid_land(pips: set[Pip], land: set[Pip]) -> Pip | None:
    """The land pip nearest the footprint's centroid; None when there is no land."""
    candidates = pips & land
    if not candidates:
        return None
    cx = sum(x for x, _ in pips) / len(pips)
    cy = sum(y for _, y in pips) / len(pips)
    return min(candidates, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p))


def capital_seed(pips: set[Pip], land: set[Pip], seed_hint: Pip | None) -> Pip | None:
    """Where the capital's region starts: ``seed_hint`` when it lies on land inside the
    footprint, else the land nearest the centroid. The same rule ``partition`` uses."""
    if seed_hint is not None and seed_hint in pips and seed_hint in land:
        return seed_hint
    return centroid_land(pips, land)


def farthest_pips(region: set[Pip], seat: Pip, count: int) -> list[Pip]:
    """``count`` pips of ``region`` other than ``seat``, farthest first, each as far as
    it can be from the seat and from the ones already picked (farthest-point sampling)."""
    picked: list[Pip] = []
    pool = {p for p in region if p != seat}
    while pool and len(picked) < count:
        anchors = [seat, *picked]
        best = max(
            pool,
            key=lambda p: (min(_distance(p, a) for a in anchors), p),
        )
        picked.append(best)
        pool.discard(best)
    return picked


def _distance(a: Pip, b: Pip) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _components(land: set[Pip]) -> list[set[Pip]]:
    """4-connected components of ``land``, largest first."""
    remaining = set(land)
    out: list[set[Pip]] = []
    while remaining:
        start = next(iter(remaining))
        seen = {start}
        frontier = [start]
        while frontier:
            pip = frontier.pop()
            for step in _neighbours(pip):
                if step in remaining and step not in seen:
                    seen.add(step)
                    frontier.append(step)
        remaining -= seen
        out.append(seen)
    out.sort(key=lambda c: (-len(c), min(c)))
    return out


def _allot(sizes: list[int], count: int, target: float, must: int) -> list[int]:
    """Seeds per landmass: in proportion to size, none for a landmass under half a county
    (unless it is ``must``, the one holding the seat, or the only one), never more than a
    landmass has pips, the remainder by largest fraction."""
    eligible = [i for i, size in enumerate(sizes) if size >= target / 2 or i == must]
    if not eligible:
        eligible = [0]
    raw = {i: sizes[i] / target for i in eligible}
    allot = {i: min(sizes[i], max(1, int(raw[i]))) for i in eligible}
    while sum(allot.values()) > count:
        # too many: trim the landmass with the smallest share above one, else drop the
        # smallest landmass that is not the seat's
        above = [i for i in eligible if allot[i] > 1]
        if above:
            allot[min(above, key=lambda i: (raw[i] - allot[i], -i))] -= 1
            continue
        droppable = [i for i in eligible if i != must and allot[i] > 0]
        if not droppable:
            break
        allot[max(droppable, key=lambda i: (-sizes[i], i))] = 0
    while sum(allot.values()) < count:
        room = [i for i in eligible if allot[i] < sizes[i]]
        if not room:
            break
        allot[max(room, key=lambda i: (raw[i] - allot[i], -i))] += 1
    return [allot.get(i, 0) for i in range(len(sizes))]


def _seeds(land: set[Pip], count: int, seed_hint: Pip | None, pips: set[Pip]) -> list[Pip]:
    """The capital seed first, then the rest spread over the landmasses in proportion to
    their size, each landmass's seeds by farthest-point sampling within it."""
    first = capital_seed(pips, land, seed_hint)
    if first is None:
        return []
    components = _components(land)
    home = next(i for i, c in enumerate(components) if first in c)
    allot = _allot([len(c) for c in components], count, len(land) / count, home)
    seeds = [first]
    for index, component in enumerate(components):
        wanted = allot[index]
        if index == home:
            seeds.extend(farthest_pips(component, first, wanted - 1))
            continue
        if wanted < 1:
            continue
        anchor = centroid_land(component, component)
        if anchor is None:
            continue
        seeds.append(anchor)
        seeds.extend(farthest_pips(component, anchor, wanted - 1))
    return seeds


def _tie_key(pip: Pip, rng_seed: int) -> int:
    """A stable per-run order for the frontier: the same seed, the same split, with no
    pseudo-random state to carry (``random`` is not wanted here, see SonarCloud)."""
    return zlib.crc32(f"{rng_seed}:{pip[0]}:{pip[1]}".encode())


def _grow(land: set[Pip], seeds: list[Pip], weights: list[float], rng_seed: int) -> list[set[Pip]]:
    """Weighted multi-source region growing over 4-connected land. Each round every
    seed with a frontier takes a share of pips proportional to its weight. A region
    walled in (its landmass all owned) while free land remains hops the water to the
    nearest free landmass, but only when it is the region nearest that landmass, so an
    island goes to the coast it faces (#5029)."""
    regions = [{s} for s in seeds]
    owner: dict[Pip, int] = {s: i for i, s in enumerate(seeds)}
    free = set(land) - set(owner)
    frontiers: list[list[Pip]] = [[n for n in _neighbours(s) if n in free] for s in seeds]
    unit = min(weights) or 1.0
    earned = [0.0] * len(seeds)
    while free:
        progress = False
        for index in range(len(seeds)):
            if not frontiers[index]:
                # a frontier the other seeds ate from under this one is rebuilt from the
                # region's own edge, so a seed never starves while it still borders free land
                frontiers[index] = _boundary(regions[index], land, owner)
            if not frontiers[index]:
                hop = _hop(index, regions, free) if free else None
                if hop is None:
                    continue
                frontiers[index] = [hop]
            # each round a seed earns weight/min(weight) pips and spends whole ones, so the
            # ratio between seeds survives however many there are
            earned[index] += weights[index] / unit
            share = int(earned[index])
            if share < 1:
                continue
            earned[index] -= share
            frontier = frontiers[index]
            frontier.sort(key=lambda p: _tie_key(p, rng_seed), reverse=True)
            taken = 0
            next_frontier: list[Pip] = []
            while frontier and taken < share:
                pip = frontier.pop()
                if pip in owner:
                    continue
                owner[pip] = index
                regions[index].add(pip)
                free.discard(pip)
                taken += 1
                progress = True
                next_frontier.extend(n for n in _neighbours(pip) if n in free)
            frontiers[index] = [p for p in frontier + next_frontier if p not in owner]
        if not progress:
            break
    return regions


def _nearest(pip: Pip, region: set[Pip]) -> int:
    return min(_distance(pip, p) for p in region)


def _component_of(pip: Pip, within: set[Pip]) -> set[Pip]:
    seen = {pip}
    frontier = [pip]
    while frontier:
        p = frontier.pop()
        for n in _neighbours(p):
            if n in within and n not in seen:
                seen.add(n)
                frontier.append(n)
    return seen


def _hop(index: int, regions: list[set[Pip]], free: set[Pip]) -> Pip | None:
    """The free land pip nearest region ``index``, when no other region lies nearer to
    the landmass it is on; else None and the region stays put this round."""
    region = regions[index]
    target = min(free, key=lambda p: (_nearest(p, region), p))
    landmass = _component_of(target, free)
    nearest = min(
        range(len(regions)),
        key=lambda i: (min(_nearest(p, regions[i]) for p in landmass), i),
    )
    return target if nearest == index else None


def _boundary(region: set[Pip], land: set[Pip], owner: dict[Pip, int]) -> list[Pip]:
    """The free land pips next to ``region``."""
    return [n for p in region for n in _neighbours(p) if n in land and n not in owner]


def _connected_without(region: set[Pip], pip: Pip) -> bool:
    """Whether nothing in ``region`` is cut off once ``pip`` leaves it: the region's pips
    around ``pip`` still reach one another. Local to the landmass ``pip`` is on, since a
    region may span water (#5029)."""
    rest = region - {pip}
    if not rest:
        return False
    around = [n for n in _neighbours(pip) if n in rest]
    if len(around) <= 1:
        return True
    wanted = set(around)
    seen = {around[0]}
    frontier = [around[0]]
    while frontier and not wanted <= seen:
        p = frontier.pop()
        for n in _neighbours(p):
            if n in rest and n not in seen:
                seen.add(n)
                frontier.append(n)
    return wanted <= seen


def _rebalance(regions: list[set[Pip]], weights: list[float], rng_seed: int) -> None:
    """Growth alone can wall a seed in (a central seed closes the land behind a corner
    one), so afterwards boundary pips move from regions above their weighted share to
    neighbours below it, one at a time, never breaking either region's connection."""
    if not regions[1:]:
        return
    owner: dict[Pip, int] = {p: i for i, region in enumerate(regions) for p in region}
    total = sum(weights)
    owned = len(owner)
    targets = [owned * w / total for w in weights]
    for _ in range(owned):
        excess = [len(r) - t for r, t in zip(regions, targets, strict=True)]
        donor = max(range(len(regions)), key=lambda i: excess[i])
        if excess[donor] < 1:
            return
        candidates: list[tuple[float, int, Pip]] = []
        for pip in regions[donor]:
            for n in _neighbours(pip):
                taker = owner.get(n)
                if taker is None or taker == donor or excess[taker] >= -1:
                    continue
                candidates.append((excess[taker], _tie_key(pip, rng_seed), pip))
        moved = False
        for _deficit, _key, pip in sorted(candidates):
            taker = next(owner[n] for n in _neighbours(pip) if owner.get(n) not in (None, donor))
            if not _connected_without(regions[donor], pip):
                continue
            regions[donor].discard(pip)
            regions[taker].add(pip)
            owner[pip] = taker
            moved = True
            break
        if not moved:
            return


def _attach_islands(regions: list[set[Pip]], land: set[Pip]) -> None:
    """Land no seed could reach (another island) joins the nearest region."""
    owned = set().union(*regions) if regions else set()
    for component in _components(land - owned):
        anchor = min(component)
        nearest = min(
            range(len(regions)),
            key=lambda i: (min(_distance(anchor, p) for p in regions[i]), i),
        )
        regions[nearest] |= component


def _attach_water(regions: list[set[Pip]], pips: set[Pip], land: set[Pip]) -> None:
    """Water inside the outline goes to the region it touches most, spreading outward
    so a lake or strait fills in from its shores (ties: the lower index)."""
    water = pips - land
    owner: dict[Pip, int] = {p: i for i, region in enumerate(regions) for p in region}
    pending = set(water)
    while pending:
        placed = False
        for pip in sorted(pending):
            touches = [owner[n] for n in _neighbours(pip) if n in owner]
            if not touches:
                continue
            best = min(set(touches), key=lambda i: (-touches.count(i), i))
            owner[pip] = best
            regions[best].add(pip)
            pending.discard(pip)
            placed = True
        if not placed:
            # water touching nothing owned (a detached pool): nearest region by distance
            pip = min(pending)
            nearest = min(
                range(len(regions)),
                key=lambda i: (min(_distance(pip, p) for p in regions[i]), i),
            )
            owner[pip] = nearest
            regions[nearest].add(pip)
            pending.discard(pip)


def _centroid(pips: set[Pip]) -> Pip:
    return (
        round(sum(x for x, _ in pips) / len(pips)),
        round(sum(y for _, y in pips) / len(pips)),
    )


def tile(
    pips: set[Pip], land: set[Pip], count: int, seed_hint: Pip | None, rng_seed: int
) -> list[set[Pip]]:
    """Split ``pips`` into up to ``count`` even tiles, the counties. Tile 0 holds the
    capital's seed (``seed_hint`` when that lies on land, else the land nearest the
    centroid); seeds go to landmasses in proportion to their size, none to a landmass
    under half a tile; tiles grow over 4-connected land and hop water when walled in;
    land no tile reached joins the nearest; water goes to the tile it touches most.
    Fewer tiles come back when the land has fewer pips than ``count``; none when there
    is no land. Every tile is non-empty. No ``random``: ties break on a crc32 of the seed
    and the pip."""
    land_in = pips & land
    if not land_in or count < 1:
        return []
    count = min(count, len(land_in))
    seeds = _seeds(land_in, count, seed_hint, pips)
    weights = [1.0] * len(seeds)
    regions = _grow(land_in, seeds, weights, rng_seed)
    _rebalance(regions, weights, rng_seed)
    _attach_islands(regions, land_in)
    _attach_water(regions, pips, land_in)
    return [r for r in regions if r]


def _fit_counts(counts: list[int], total: int) -> list[int]:
    """``counts`` scaled to sum to ``total`` tiles, at least one each; fewer groups when
    there are fewer tiles than groups, the first groups kept."""
    if total < 1 or not counts:
        return []
    counts = [max(1, c) for c in counts[: min(len(counts), total)]]
    if sum(counts) == total:
        return counts
    scale = total / sum(counts)
    raw = [c * scale for c in counts]
    fitted = [max(1, int(r)) for r in raw]
    while sum(fitted) > total:
        above = [i for i in range(len(fitted)) if fitted[i] > 1]
        fitted[max(above, key=lambda i: (fitted[i] - raw[i], i))] -= 1
    while sum(fitted) < total:
        fitted[max(range(len(fitted)), key=lambda i: (raw[i] - fitted[i], -i))] += 1
    return fitted


def _shared_borders(tiles: list[set[Pip]]) -> list[dict[int, int]]:
    """``shared[i][j]``: how many pip edges tile ``i`` shares with tile ``j``."""
    owner_tile = {p: i for i, t in enumerate(tiles) for p in t}
    shared: list[dict[int, int]] = [defaultdict(int) for _ in tiles]
    for i, t in enumerate(tiles):
        for p in t:
            for n in _neighbours(p):
                j = owner_tile.get(n)
                if j is not None and j != i:
                    shared[i][j] += 1
    return shared


def _spread_seeds(centroids: list[Pip], count: int) -> list[int]:
    """Tile 0, then ``count - 1`` more tiles by farthest-point over the centroids."""
    seeds = [0]
    while len(seeds) < count:
        seeds.append(
            max(
                (i for i in range(len(centroids)) if i not in seeds),
                key=lambda i: (min(_distance(centroids[i], centroids[s]) for s in seeds), -i),
            )
        )
    return seeds


def group(tiles: list[set[Pip]], counts: list[int]) -> list[list[int]]:
    """Group tiles into duchies, as tile indices. Group 0 holds tile 0 (the capital's
    county); each group takes ``counts[i]`` tiles, a free neighbour first (the most shared
    border, then the nearest to the group's seed), and the nearest free tile when it has
    no free neighbour (an archipelago). The other groups' seeds spread by farthest-point
    over the tiles' centroids. ``counts`` is fitted to the tiles there are."""
    if not tiles:
        return []
    counts = _fit_counts(counts, len(tiles))
    centroids = [_centroid(t) for t in tiles]
    shared = _shared_borders(tiles)
    seeds = _spread_seeds(centroids, len(counts))
    groups = [[s] for s in seeds]
    taken = set(seeds)
    while len(taken) < len(tiles):
        order = sorted(range(len(groups)), key=lambda g: (len(groups[g]) / counts[g], g))
        progress = False
        for g in order:
            free = [i for i in range(len(tiles)) if i not in taken]
            if len(groups[g]) >= counts[g] or not free:
                continue
            pick = _pick_tile(groups[g], seeds[g], free, shared, centroids)
            groups[g].append(pick)
            taken.add(pick)
            progress = True
        if not progress:
            # every group is full (counts fell short of the tiles): the rest join the
            # group with the nearest tile
            for i in [i for i in range(len(tiles)) if i not in taken]:
                groups[_nearest_group(i, groups, centroids)].append(i)
                taken.add(i)
    return groups


def _pick_tile(
    members: list[int],
    seed: int,
    free: list[int],
    shared: list[dict[int, int]],
    centroids: list[Pip],
) -> int:
    """The free tile a group takes next: the most shared border with its members, then
    the nearest to its seed; any free tile when none borders it."""
    border = {i: sum(shared[m][i] for m in members) for i in free}
    pool = [i for i in free if border[i] > 0] or free
    return max(pool, key=lambda i: (border[i], -_distance(centroids[i], centroids[seed]), -i))


def _nearest_group(index: int, groups: list[list[int]], centroids: list[Pip]) -> int:
    return min(
        range(len(groups)),
        key=lambda g: (min(_distance(centroids[index], centroids[m]) for m in groups[g]), g),
    )


def lay_out_land(
    pips: set[Pip], land: set[Pip], counts: list[int], seed_hint: Pip | None, rng_seed: int
) -> list[list[set[Pip]]]:
    """A kingdom's land as duchies of counties: ``counts[i]`` counties for duchy ``i``,
    duchy 0 the capital's (its first county holds the seat). The counties are even tiles
    of the whole footprint, grouped by adjacency, so no duchy is smaller than its count
    says and a small island is part of a county rather than a duchy of its own (#5029)."""
    tiles = tile(pips, land, sum(counts), seed_hint, rng_seed)
    return [[tiles[i] for i in g] for g in group(tiles, counts)]
