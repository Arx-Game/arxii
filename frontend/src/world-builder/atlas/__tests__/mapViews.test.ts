import { describe, expect, it } from 'vitest';

import type { RegionMapFootprint } from '../../types';
import { PIP_PX } from '../regionMapCanvas';
import { MAP_VIEW_LABELS, MAP_VIEWS, placeNames, rootsOf, visibleFootprints } from '../mapViews';

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

  it('Domain shows the anchors alone', () => {
    expect(visibleFootprints('domain', all, [west]).map((f) => f.name)).toEqual(['Vestyr']);
    expect(
      visibleFootprints('domain', all, [west, east])
        .map((f) => f.name)
        .sort()
    ).toEqual(['Norbyria', 'Vestyr']);
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
    const close = placeNames('all', all, [], project(1), measure).map((l) => l.text);
    expect(close).toEqual(['The Umbral Empire', 'Luxen', 'Aberwen']);
    // at zoom 2 the empire (480 px wide) and the kingdoms (240 px) fit side by side; the
    // 10-pip duchy (120 px) does not fit "Carradyn" (56 + padding) over its parent's name;
    // the seat never fits
    const labels = placeNames('all', all, [], project(2), measure);
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
    const far = placeNames('all', all, [], project(0.2), measure).map((l) => l.text);
    const near = placeNames('all', all, [], project(4), measure).map((l) => l.text);
    expect(far).not.toContain('Carradyn');
    expect(near).toContain('Carradyn');
    expect(near).toContain('Aberwen');
  });

  it('Domain names the anchor whatever its size; Domain-Vassal names the children, not the anchor', () => {
    expect(
      placeNames('domain', [barony], [barony], project(0.2), measure).map((l) => l.text)
    ).toEqual(['Seat']);
    const vassal = placeNames('domain-vassal', all, [west], project(0.2), measure).map(
      (l) => l.text
    );
    expect(vassal).not.toContain('Vestyr');
    expect(vassal).toContain('Carradyn'); // a direct child is named even where it would not fit
    expect(vassal).not.toContain('Aberwen'); // a grandchild still has to fit
  });

  it('Geography names nothing', () => {
    expect(placeNames('geography', all, [west], project(1), measure)).toEqual([]);
  });
});
