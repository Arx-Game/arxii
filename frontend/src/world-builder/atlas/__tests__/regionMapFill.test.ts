import { describe, expect, it } from 'vitest';

import type { RegionMapFootprint, RegionMapPips, RegionMapSummary } from '../../types';
import {
  ancestorTitleIds,
  brushPips,
  floodHeld,
  floodLand,
  isTakeable,
  loopInterior,
  lowestHolderIndex,
  type Pip,
} from '../regionMapFill';

const region: RegionMapSummary = {
  id: 1,
  name: 'Testland',
  area: null,
  area_name: '',
  anchor_x: 0,
  anchor_y: 0,
  width_cells: 2,
  height_cells: 2,
  pips_per_cell: 10,
  created_at: '',
  latest_upload: null,
};

/** A 20×20 region; land where `isLand` says, water elsewhere. */
function grid(
  isLand: (x: number, y: number) => boolean,
  footprints: RegionMapFootprint[] = []
): RegionMapPips {
  const pips: RegionMapPips['pips'] = [];
  for (let y = 0; y < 20; y += 1) {
    for (let x = 0; x < 20; x += 1) {
      pips.push([x, y, isLand(x, y) ? 'plain' : 'water', false]);
    }
  }
  return { region, terrains: ['water', 'plain'], pips, footprints };
}

const island = (x: number, y: number) => x >= 2 && x <= 11 && y >= 2 && y <= 11;

function footprint(areaId: number, titleId: number, pips: Pip[]): RegionMapFootprint {
  return {
    area_id: areaId,
    name: `Domain ${titleId}`,
    level: 53,
    level_display: 'County',
    parent_id: null,
    realm_id: 1,
    holder_org_id: areaId,
    holder_name: '',
    title_id: titleId,
    seat: null,
    pips,
  };
}

function rightHalf(): Pip[] {
  const out: Pip[] = [];
  for (let y = 2; y <= 11; y += 1) for (let x = 7; x <= 11; x += 1) out.push([x, y]);
  return out;
}

const keys = (pips: Pip[]) => new Set(pips.map(([x, y]) => `${x},${y}`));

describe('brushPips', () => {
  it('is the pip itself at width 1 and a square around it otherwise', () => {
    expect(brushPips([5, 5], 1)).toEqual([[5, 5]]);
    const three = brushPips([5, 5], 3);
    expect(three).toHaveLength(9);
    expect(keys(three).has('4,4')).toBe(true);
    expect(keys(three).has('6,6')).toBe(true);
    expect(brushPips([5, 5], 7)).toHaveLength(49);
  });
});

describe('floodLand', () => {
  it('fills a landmass to the coast and leaves the water', () => {
    const got = floodLand(grid(island), [5, 5], 100, []);
    expect(got).toHaveLength(100);
    const k = keys(got);
    expect(k.has('2,2')).toBe(true);
    expect(k.has('11,11')).toBe(true);
    expect(k.has('1,1')).toBe(false);
    expect(k.has('12,5')).toBe(false);
  });

  it('returns nothing from water', () => {
    expect(floodLand(grid(island), [0, 0], 100, [])).toEqual([]);
  });

  it('stops at another domain, and flows over an ancestor', () => {
    const data = grid(island, [footprint(20, 200, rightHalf())]);
    const stopped = floodLand(data, [3, 3], 100, []);
    expect(stopped).toHaveLength(50);
    expect(keys(stopped).has('7,2')).toBe(false);
    const rows = [
      { title_id: 200, parent_title_id: null },
      { title_id: 100, parent_title_id: 200 },
    ];
    expect(floodLand(data, [3, 3], 100, rows)).toHaveLength(100);
    expect(floodLand(data, [8, 8], 100, [])).toEqual([]);
  });
});

describe('isTakeable and ancestorTitleIds', () => {
  it('walks the ladder up from a title', () => {
    const rows = [
      { title_id: 1, parent_title_id: null },
      { title_id: 2, parent_title_id: 1 },
      { title_id: 3, parent_title_id: 2 },
    ];
    expect(ancestorTitleIds(rows, 3)).toEqual(new Set([2, 1]));
    expect(ancestorTitleIds(rows, 1)).toEqual(new Set());
    expect(isTakeable(null, 3, rows)).toBe(true);
    expect(isTakeable(footprint(10, 1, []), 3, rows)).toBe(true);
    expect(isTakeable(footprint(30, 3, []), 1, rows)).toBe(true);
    expect(isTakeable(footprint(40, 4, []), 3, rows)).toBe(false);
  });
});

describe('lowestHolderIndex', () => {
  it('maps every held pip to its lowest holder in one pass', () => {
    const county = footprint(10, 100, [
      [2, 2],
      [3, 2],
    ]);
    county.level = 53;
    const barony = footprint(11, 101, [[3, 2]]);
    barony.level = 40;
    const index = lowestHolderIndex([county, barony]);
    expect(index.get('2,2')?.area_id).toBe(10);
    expect(index.get('3,2')?.area_id).toBe(11);
    expect(index.get('9,9')).toBeUndefined();
    // order of the input does not matter
    expect(lowestHolderIndex([barony, county]).get('3,2')?.area_id).toBe(11);
  });
});

describe('floodHeld', () => {
  it('follows only the connected pips the target itself holds', () => {
    const data = grid(island, [
      footprint(10, 100, [
        [2, 2],
        [3, 2],
        [9, 9],
      ]),
    ]);
    expect(keys(floodHeld(data, [2, 2], 100))).toEqual(new Set(['2,2', '3,2']));
    expect(floodHeld(data, [5, 5], 100)).toEqual([]);
  });
});

describe('loopInterior', () => {
  it('fills the land inside a closed path, path included, water inside ignored', () => {
    const data = grid((x, y) => island(x, y) && !(x === 4 && y === 4));
    const path: Pip[] = [];
    for (let x = 2; x <= 6; x += 1) path.push([x, 2]);
    for (let y = 3; y <= 6; y += 1) path.push([6, y]);
    for (let x = 5; x >= 2; x -= 1) path.push([x, 6]);
    for (let y = 5; y >= 3; y -= 1) path.push([2, y]);
    const got = loopInterior(data, path);
    expect(got).toHaveLength(24);
    expect(keys(got).has('3,3')).toBe(true);
    expect(keys(got).has('2,2')).toBe(true);
    expect(keys(got).has('4,4')).toBe(false);
    expect(keys(got).has('7,7')).toBe(false);
  });

  it('joins far-apart samples', () => {
    const got = loopInterior(grid(island), [
      [2, 2],
      [8, 2],
      [8, 8],
      [2, 8],
    ]);
    expect(got).toHaveLength(49);
  });

  it('does not fill the notch of a concave loop', () => {
    const got = loopInterior(grid(island), [
      [2, 2],
      [8, 2],
      [8, 4],
      [4, 4],
      [4, 6],
      [8, 6],
      [8, 8],
      [2, 8],
    ]);
    const k = keys(got);
    expect(k.has('3,5')).toBe(true);
    expect(k.has('6,5')).toBe(false);
    expect(k.has('6,3')).toBe(true);
  });

  it('takes a single land pip and nothing on water', () => {
    expect(loopInterior(grid(island), [[5, 5]])).toEqual([[5, 5]]);
    expect(loopInterior(grid(island), [[0, 0]])).toEqual([]);
  });
});
