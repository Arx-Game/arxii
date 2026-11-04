"""Split a drawn footprint into contiguous children (#4983 slice 2, #4986).

Pure geometry over pips, no database: the layout walk hands in a kingdom's footprint
and gets back one region per duchy (and again per county), each 4-connected on land,
the capital largest, water kept with the land it touches. The owner clips the result
with the map's Brush and Loop afterwards; this only has to be contiguous and sized,
never pretty.
"""

from __future__ import annotations

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


def _seeds(land: set[Pip], count: int, seed_hint: Pip | None, pips: set[Pip]) -> list[Pip]:
    """The capital seed, then ``count - 1`` more by farthest-point sampling."""
    first = capital_seed(pips, land, seed_hint)
    if first is None:
        return []
    return [first, *farthest_pips(land, first, count - 1)]


def _tie_key(pip: Pip, rng_seed: int) -> int:
    """A stable per-run order for the frontier: the same seed, the same split, with no
    pseudo-random state to carry (``random`` is not wanted here, see SonarCloud)."""
    return zlib.crc32(f"{rng_seed}:{pip[0]}:{pip[1]}".encode())


def _grow(land: set[Pip], seeds: list[Pip], weights: list[float], rng_seed: int) -> list[set[Pip]]:
    """Weighted multi-source region growing over 4-connected land. Each round every
    seed with a frontier takes a share of pips proportional to its weight."""
    regions = [{s} for s in seeds]
    owner: dict[Pip, int] = {s: i for i, s in enumerate(seeds)}
    frontiers: list[list[Pip]] = [
        [n for n in _neighbours(s) if n in land and n not in owner] for s in seeds
    ]
    unit = min(weights) or 1.0
    earned = [0.0] * len(seeds)
    while any(frontiers):
        for index in range(len(seeds)):
            if not frontiers[index]:
                # a frontier the other seeds ate from under this one is rebuilt from the
                # region's own edge, so a seed never starves while it still borders free land
                frontiers[index] = _boundary(regions[index], land, owner)
                if not frontiers[index]:
                    continue
            frontier = frontiers[index]
            # each round a seed earns weight/min(weight) pips and spends whole ones, so the
            # ratio between seeds survives however many there are
            earned[index] += weights[index] / unit
            share = int(earned[index])
            if share < 1:
                continue
            earned[index] -= share
            frontier.sort(key=lambda p: _tie_key(p, rng_seed), reverse=True)
            taken = 0
            next_frontier: list[Pip] = []
            while frontier and taken < share:
                pip = frontier.pop()
                if pip in owner:
                    continue
                owner[pip] = index
                regions[index].add(pip)
                taken += 1
                next_frontier.extend(n for n in _neighbours(pip) if n in land and n not in owner)
            rebuilt = [p for p in frontier + next_frontier if p not in owner]
            frontiers[index] = rebuilt or _boundary(regions[index], land, owner)
    return regions


def _boundary(region: set[Pip], land: set[Pip], owner: dict[Pip, int]) -> list[Pip]:
    """The free land pips next to ``region``."""
    return [n for p in region for n in _neighbours(p) if n in land and n not in owner]


def _connected_without(region: set[Pip], pip: Pip) -> bool:
    """Whether ``region`` stays 4-connected once ``pip`` leaves it."""
    rest = region - {pip}
    if not rest:
        return False
    start = next(iter(rest))
    seen = {start}
    frontier = [start]
    while frontier:
        p = frontier.pop()
        for n in _neighbours(p):
            if n in rest and n not in seen:
                seen.add(n)
                frontier.append(n)
    return len(seen) == len(rest)


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


def partition(  # noqa: PLR0913 - one argument per fact the split needs
    pips: set[Pip],
    land: set[Pip],
    count: int,
    weights: list[float],
    seed_hint: Pip | None,
    rng_seed: int,
) -> list[set[Pip]]:
    """Split ``pips`` into up to ``count`` regions. Region 0 is the capital's (its seed is
    ``seed_hint`` when that lies on land, else the land nearest the centroid); the rest
    are seeded by farthest-point sampling and grown in weighted rounds over 4-connected
    land; unreachable land joins the nearest region; water goes to the region it touches
    most. Fewer regions come back when the land has fewer pips than ``count``; none
    when there is no land. Every region is non-empty."""
    land_in = pips & land
    if not land_in or count < 1:
        return []
    count = min(count, len(land_in))
    weights = list(weights[:count]) + [1.0] * max(0, count - len(weights))
    seeds = _seeds(land_in, count, seed_hint, pips)
    regions = _grow(land_in, seeds, weights, rng_seed)
    _rebalance(regions, weights, rng_seed)
    _attach_islands(regions, land_in)
    _attach_water(regions, pips, land_in)
    return [r for r in regions if r]
