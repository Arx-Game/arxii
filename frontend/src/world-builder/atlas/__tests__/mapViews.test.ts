import { describe, expect, it } from 'vitest';

import type { RegionMapFootprint } from '../../types';
import { PIP_PX } from '../regionMapCanvas';
import {
  borderWidths,
  DEFAULT_MAP_TIERS,
  MAP_TIER_LABELS,
  MAP_TIERS,
  MAP_VIEW_LABELS,
  MAP_VIEWS,
  markerRadius,
  placeNames,
  rootsOf,
  seatMarkers,
  visibleFootprints,
  type MapTier,
} from '../mapViews';

const DEFAULT = new Set<MapTier>(DEFAULT_MAP_TIERS);
const tiersOf = (...tiers: MapTier[]) => new Set<MapTier>(tiers);

function footprint(
  overrides: Partial<RegionMapFootprint> & Pick<RegionMapFootprint, 'area_id' | 'level'>
): RegionMapFootprint {
  return {
    name: `area ${overrides.area_id}`,
    level_display: '',
    parent_id: null,
    realm_id: 1,
    holder_org_id: null,
    holder_name: '',
    title_id: overrides.area_id,
    seat: null,
    pips: [[0, 0]],
    charters: [],
    ...overrides,
  };
}

function block(x0: number, y0: number, w: number, h: number): [number, number][] {
  const out: [number, number][] = [];
  for (let x = x0; x < x0 + w; x += 1) for (let y = y0; y < y0 + h; y += 1) out.push([x, y]);
  return out;
}

// an empire over two kingdoms; the west kingdom has a duchy with a county and a barony
const empire = footprint({
  area_id: 1,
  level: 90,
  name: 'The Umbral Empire',
  pips: block(0, 0, 40, 20),
});
const west = footprint({
  area_id: 2,
  level: 80,
  parent_id: 1,
  name: 'Vestyr',
  pips: block(0, 0, 20, 20),
});
const east = footprint({
  area_id: 3,
  level: 80,
  parent_id: 1,
  name: 'Norbyria',
  pips: block(20, 0, 20, 20),
  realm_id: 1,
});
const duchy = footprint({
  area_id: 4,
  level: 70,
  parent_id: 2,
  name: 'Carradyn',
  pips: block(0, 0, 10, 20),
});
const county = footprint({
  area_id: 5,
  level: 53,
  parent_id: 4,
  name: 'Aberwen',
  pips: block(0, 0, 10, 10),
});
const barony = footprint({
  area_id: 6,
  level: 40,
  parent_id: 5,
  name: 'Seat',
  pips: [[2, 2]],
  seat: [2, 2],
});
const otherRealm = footprint({
  area_id: 7,
  level: 80,
  name: 'Luxen',
  realm_id: 2,
  pips: block(50, 0, 10, 10),
});
const all = [barony, county, duchy, west, east, empire, otherRealm];

describe('mapViews: the four views (#5030)', () => {
  it("names the views in the owner's words, All last", () => {
    expect(MAP_VIEWS).toEqual(['geography', 'domain', 'domain-vassal', 'all']);
    expect(MAP_VIEWS.map((v) => MAP_VIEW_LABELS[v])).toEqual([
      'Geography',
      'Domain',
      'Domain-Vassal',
      'All',
    ]);
  });

  it("finds a realm's roots: footprints whose parent is not on the map", () => {
    expect(rootsOf(all, 1).map((f) => f.name)).toEqual(['The Umbral Empire']);
    expect(rootsOf(all, 2).map((f) => f.name)).toEqual(['Luxen']);
    expect(
      rootsOf(all, null)
        .map((f) => f.name)
        .sort()
    ).toEqual(['Luxen', 'The Umbral Empire']);
    // with the empire gone the kingdoms are the roots
    expect(
      rootsOf(
        all.filter((f) => f !== empire),
        1
      )
        .map((f) => f.name)
        .sort()
    ).toEqual(['Norbyria', 'Vestyr']);
  });

  it('Geography shows nothing political', () => {
    expect(visibleFootprints('geography', all, [west])).toEqual([]);
  });

  it('Domain shows the anchors and the tier below them (#5056)', () => {
    expect(
      visibleFootprints('domain', all, [west])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Carradyn', 'Vestyr']);
    expect(
      visibleFootprints('domain', all, [duchy])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Aberwen', 'Carradyn']);
    // a kingdom with nothing beneath it is drawn alone
    expect(
      visibleFootprints('domain', all, [west, east])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Carradyn', 'Norbyria', 'Vestyr']);
  });

  it('Domain draws a border on the tier below; Domain-Vassal on every tier, lighter as it goes down (#5056)', () => {
    expect(borderWidths('domain', all, [west], DEFAULT)).toEqual(new Map([[duchy.area_id, 2]]));
    expect(borderWidths('domain-vassal', all, [west], tiersOf(...MAP_TIERS))).toEqual(
      new Map([
        [duchy.area_id, 2],
        [county.area_id, 1],
        [barony.area_id, 0.5],
      ])
    );
    expect(borderWidths('all', all, [west], DEFAULT)).toEqual(new Map());
    expect(borderWidths('geography', all, [west], DEFAULT)).toEqual(new Map());
  });

  it('Domain-Vassal shows the anchor and everything beneath it, at every tier', () => {
    expect(
      visibleFootprints('domain-vassal', all, [west])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Aberwen', 'Carradyn', 'Seat', 'Vestyr']);
    expect(
      visibleFootprints('domain-vassal', all, [county])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Aberwen', 'Seat']);
  });

  it('All shows every footprint', () => {
    expect(visibleFootprints('all', all, [west])).toHaveLength(all.length);
  });
});

describe('mapViews: names that do not stack (#5030)', () => {
  // project a pip to the screen at a given zoom with no pan; measure a name at 7 px a letter
  const project =
    (zoom: number) =>
    (x: number, y: number): [number, number] => [
      (x + 0.5) * PIP_PX * zoom,
      (y + 0.5) * PIP_PX * zoom,
    ];
  const measure = (text: string) => text.length * 7;

  it('All names only what fits, top tiers first, and never over a placed name', () => {
    // at zoom 1 the empire's name (127 px wide, centred at x 120) covers both kingdoms'
    // centres, so the parent wins; the short-named county "Aberwen" (57 px) fits its 60 px
    // footprint and sits clear of the empire's row, so it is named while "Carradyn" is not
    const close = placeNames('all', all, [], project(1), measure, DEFAULT).map((l) => l.text);
    expect(close).toEqual(['The Umbral Empire', 'Luxen', 'Aberwen']);
    // at zoom 2 the empire (480 px wide) and the kingdoms (240 px) fit side by side; the
    // 10-pip duchy (120 px) does not fit "Carradyn" (56 + padding) over its parent's name;
    // the seat never fits
    const labels = placeNames('all', all, [], project(2), measure, DEFAULT);
    const names = labels.map((l) => l.text);
    expect(names).toContain('The Umbral Empire');
    expect(names).toContain('Vestyr');
    expect(names).toContain('Norbyria');
    expect(names).not.toContain('Seat');
    const boxes = labels.map((l) => [l.x - l.w / 2, l.x + l.w / 2, l.y - l.h / 2, l.y + l.h / 2]);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const [ax0, ax1, ay0, ay1] = boxes[i];
        const [bx0, bx1, by0, by1] = boxes[j];
        const overlap = ax0 < bx1 && bx0 < ax1 && ay0 < by1 && by0 < ay1;
        expect(overlap).toBe(false);
      }
    }
  });

  it('zooming in lets the lower tiers fit', () => {
    const far = placeNames('all', all, [], project(0.2), measure, DEFAULT).map((l) => l.text);
    const near = placeNames('all', all, [], project(4), measure, DEFAULT).map((l) => l.text);
    expect(far).not.toContain('Carradyn');
    expect(near).toContain('Carradyn');
    expect(near).toContain('Aberwen');
  });

  it('Domain names the tier below the anchor whatever its size, and the anchor only when nothing is beneath it; Domain-Vassal names the children, not the anchor', () => {
    expect(
      placeNames('domain', [barony], [barony], project(0.2), measure, DEFAULT).map((l) => l.text)
    ).toEqual(['Seat']);
    const domain = placeNames('domain', all, [west], project(0.2), measure, DEFAULT).map(
      (l) => l.text
    );
    expect(domain).toEqual(['Carradyn']);
    const vassal = placeNames('domain-vassal', all, [west], project(0.2), measure, DEFAULT).map(
      (l) => l.text
    );
    expect(vassal).not.toContain('Vestyr');
    expect(vassal).toContain('Carradyn'); // a direct child is named even where it would not fit
    expect(vassal).not.toContain('Aberwen'); // a grandchild still has to fit
  });

  it('places a name on a very large footprint without exhausting the argument stack', () => {
    const large = {
      ...west,
      pips: Array.from({ length: 150000 }, (_, x) => [x, 0] as [number, number]),
    };
    expect(
      placeNames('all', [large], [], project(1), measure, DEFAULT).map((label) => label.text)
    ).toEqual([west.name]);
  });

  it('Geography names nothing', () => {
    expect(placeNames('geography', all, [west], project(1), measure, DEFAULT)).toEqual([]);
  });
});

// a kingdom of two duchies on the real ladder levels; every domain's seat is its capital
// barony's pip, and each county holds one more barony that is nobody's capital
const crown = footprint({
  area_id: 10,
  level: 60,
  name: 'Vestyr',
  pips: block(0, 0, 40, 20),
  seat: [5, 5],
});
const northDuchy = footprint({
  area_id: 11,
  level: 56,
  parent_id: 10,
  name: 'Carradyn',
  pips: block(0, 0, 20, 20),
  seat: [5, 5],
});
const southDuchy = footprint({
  area_id: 12,
  level: 56,
  parent_id: 10,
  name: 'Hollin',
  pips: block(20, 0, 20, 20),
  seat: [30, 5],
});
const aldmere = footprint({
  area_id: 13,
  level: 53,
  parent_id: 11,
  name: 'Aldmere',
  pips: block(0, 0, 20, 10),
  seat: [5, 5],
});
const brack = footprint({
  area_id: 14,
  level: 53,
  parent_id: 11,
  name: 'Brack',
  pips: block(0, 10, 20, 10),
  seat: [5, 15],
});
const corwen = footprint({
  area_id: 15,
  level: 53,
  parent_id: 12,
  name: 'Corwen',
  pips: block(20, 0, 20, 20),
  seat: [30, 5],
});
const seatOf = (area_id: number, parent_id: number, name: string, pip: [number, number]) =>
  footprint({ area_id, level: 40, parent_id, name, pips: [pip], seat: pip });
const kingsport = seatOf(20, 13, 'Kingsport', [5, 5]);
const lowfen = seatOf(21, 13, 'Lowfen', [15, 3]);
const marrow = seatOf(22, 14, 'Marrow', [5, 15]);
const nettle = seatOf(23, 14, 'Nettle', [15, 17]);
const oxgate = seatOf(24, 15, 'Oxgate', [30, 5]);
const pell = seatOf(25, 15, 'Pell', [35, 15]);
const ladder = [
  crown,
  northDuchy,
  southDuchy,
  aldmere,
  brack,
  corwen,
  kingsport,
  lowfen,
  marrow,
  nettle,
  oxgate,
  pell,
];

describe('mapViews: tiers, capitals and baronies (#5157)', () => {
  const project =
    (zoom: number) =>
    (x: number, y: number): [number, number] => [
      (x + 0.5) * PIP_PX * zoom,
      (y + 0.5) * PIP_PX * zoom,
    ];
  const measure = (text: string) => text.length * 7;
  const ranks = (markers: ReturnType<typeof seatMarkers>) =>
    Object.fromEntries(markers.map((m) => [m.name, m.rank]));
  const names = (labels: ReturnType<typeof placeNames>) => labels.map((l) => l.text).sort();

  it('offers four tiers, top first, with Barony off to start', () => {
    expect(MAP_TIERS.map((t) => MAP_TIER_LABELS[t])).toEqual([
      'Kingdom',
      'Duchy',
      'County',
      'Barony',
    ]);
    expect(DEFAULT_MAP_TIERS).toEqual(['kingdom', 'duchy', 'county']);
  });

  it('marks a capital by the highest tier seated there that is on, and a plain barony only with Barony on', () => {
    expect(ranks(seatMarkers('all', ladder, [], DEFAULT))).toEqual({
      Kingsport: 3,
      Oxgate: 2,
      Marrow: 1,
    });
    expect(ranks(seatMarkers('all', ladder, [], tiersOf('county', 'barony')))).toEqual({
      Kingsport: 1,
      Oxgate: 1,
      Marrow: 1,
      Lowfen: 0,
      Nettle: 0,
      Pell: 0,
    });
    const onlyBaronies = seatMarkers('all', ladder, [], tiersOf('barony'));
    expect(onlyBaronies).toHaveLength(6);
    expect(onlyBaronies.every((m) => m.rank === 0)).toBe(true);
    expect(seatMarkers('all', ladder, [], tiersOf())).toEqual([]);
    expect(seatMarkers('geography', ladder, [], DEFAULT)).toEqual([]);
    expect(markerRadius(3)).toBeGreaterThan(markerRadius(2));
    expect(markerRadius(1)).toBeGreaterThan(markerRadius(0));
  });

  it("Domain on a duchy names the duchy's capital and each county's, with Barony off, and no other barony", () => {
    const labels = placeNames('domain', ladder, [northDuchy], project(4), measure, DEFAULT);
    expect(names(labels)).toEqual(['Aldmere', 'Brack', 'Kingsport', 'Marrow']);
    expect(ranks(seatMarkers('domain', ladder, [northDuchy], DEFAULT))).toEqual({
      Kingsport: 2,
      Marrow: 1,
    });
    // a capital's name sits under its marker, never on it
    const capital = labels.find((l) => l.text === 'Kingsport')!;
    const [x, y] = project(4)(5, 5);
    expect(capital.x).toBe(x);
    expect(capital.y).toBe(y + markerRadius(2) + capital.h / 2);
    expect(capital.areaId).toBe(kingsport.area_id);
  });

  it('a selected county shows every barony in it whatever the Barony toggle says', () => {
    for (const view of ['domain', 'domain-vassal'] as const) {
      expect(names(placeNames(view, ladder, [aldmere], project(4), measure, DEFAULT))).toEqual([
        'Kingsport',
        'Lowfen',
      ]);
      expect(ranks(seatMarkers(view, ladder, [aldmere], DEFAULT))).toEqual({
        Kingsport: 1,
        Lowfen: 0,
      });
      expect([...borderWidths(view, ladder, [aldmere], DEFAULT).keys()].sort()).toEqual([20, 21]);
    }
    // a duchy's baronies are not its own children, so they wait for the toggle
    const vassal = placeNames('domain-vassal', ladder, [northDuchy], project(4), measure, DEFAULT);
    expect(names(vassal)).not.toContain('Lowfen');
  });

  it('a tier that is off draws no border, name or marker for its footprints', () => {
    const noCounty = tiersOf('kingdom', 'duchy');
    expect(borderWidths('domain', ladder, [northDuchy], noCounty)).toEqual(new Map());
    // the selected duchy's own capital is still named; the county capital is gone
    expect(
      names(placeNames('domain', ladder, [northDuchy], project(4), measure, noCounty))
    ).toEqual(['Kingsport']);
    expect(ranks(seatMarkers('domain', ladder, [northDuchy], noCounty))).toEqual({ Kingsport: 2 });
    const onlyCounty = tiersOf('county');
    expect([...borderWidths('domain-vassal', ladder, [crown], onlyCounty).keys()].sort()).toEqual([
      13, 14, 15,
    ]);
  });

  it('Barony on names every barony in scope and nobody else, with no width rule', () => {
    const on = tiersOf('kingdom', 'duchy', 'county', 'barony');
    const vassal = names(
      placeNames('domain-vassal', ladder, [northDuchy], project(4), measure, on)
    );
    expect(vassal).toEqual(['Aldmere', 'Brack', 'Kingsport', 'Lowfen', 'Marrow', 'Nettle']);
    // only baronies: the whole canvas is theirs, in All too
    expect(names(placeNames('all', ladder, [], project(4), measure, tiersOf('barony')))).toEqual([
      'Kingsport',
      'Lowfen',
      'Marrow',
      'Nettle',
      'Oxgate',
      'Pell',
    ]);
  });

  it("a marker's name moves over or beside the marker when the place under it is taken", () => {
    // two baronies one pip apart, north and south: the second cannot sit under its marker
    // without crossing the first's name, so it sits over it
    const upper = seatOf(30, 13, 'Upper', [8, 4]);
    const lower = seatOf(31, 13, 'Lower', [8, 5]);
    const labels = placeNames(
      'all',
      [aldmere, upper, lower],
      [],
      project(1),
      measure,
      tiersOf('barony')
    );
    expect(names(labels)).toEqual(['Lower', 'Upper']);
    const [, upperY] = project(1)(8, 4);
    const [, lowerY] = project(1)(8, 5);
    const yOf = (text: string) => labels.find((l) => l.text === text)!.y;
    expect(yOf('Upper')).toBeGreaterThan(upperY);
    expect(yOf('Lower')).not.toBe(lowerY + markerRadius(0) + 8);
  });

  it('an undefined barony is marked and not named', () => {
    const undefinedSeat = { ...lowfen, name: 'Undefined' };
    const rows = ladder.map((f) => (f === lowfen ? undefinedSeat : f));
    const on = tiersOf('barony');
    expect(seatMarkers('all', rows, [], on)).toHaveLength(6);
    expect(names(placeNames('all', rows, [], project(4), measure, on))).not.toContain('Undefined');
    expect(names(placeNames('all', rows, [], project(4), measure, on))).toHaveLength(5);
  });

  it('All from far away names no capital whose domain is too small to be named', () => {
    const far = names(placeNames('all', ladder, [], project(0.2), measure, DEFAULT));
    expect(far).toEqual([]);
    expect(seatMarkers('all', ladder, [], DEFAULT)).toHaveLength(3);
  });
});
