import { describe, expect, it } from 'vitest';

import type { RegionMapFootprint, RegionMapSummary } from '../../types';
import { DEFAULT_VIEW } from '../latticeState';
import {
  centroid,
  footprintAt,
  holderColor,
  PIP_PX,
  pipAt,
  regionBounds,
} from '../regionMapCanvas';

const region: RegionMapSummary = {
  id: 1,
  name: 'Catenys',
  area: null,
  area_name: '',
  anchor_x: 5,
  anchor_y: 3,
  width_cells: 2,
  height_cells: 2,
  pips_per_cell: 10,
  created_at: '',
  latest_upload: null,
};

const footprints: RegionMapFootprint[] = [
  {
    area_id: 10,
    name: 'County',
    level: 53,
    level_display: 'County',
    parent_id: null,
    realm_id: 1,
    holder_org_id: 4,
    holder_name: 'House A',
    title_id: 100,
    seat: [52, 31],
    pips: [
      [51, 31],
      [52, 31],
      [51, 32],
    ],
  },
  {
    area_id: 11,
    name: 'Barony',
    level: 40,
    level_display: 'Barony',
    parent_id: 10,
    realm_id: 1,
    holder_org_id: 4,
    holder_name: 'House A',
    title_id: 101,
    seat: [52, 31],
    pips: [[52, 31]],
  },
];

describe('regionMapCanvas', () => {
  it('shifts the region to its first world pip', () => {
    expect(regionBounds(region)).toEqual({ x0: 50, y0: 30, width: 20, height: 20, per: 10 });
  });

  it('finds the world pip under a pointer, through zoom and pan', () => {
    const rect = { left: 100, top: 200 };
    expect(pipAt(region, DEFAULT_VIEW, rect, 100 + PIP_PX * 2.5, 200 + PIP_PX * 1.5)).toEqual([
      52, 31,
    ]);
    const view = { zoom: 2, panX: 10, panY: 20 };
    expect(
      pipAt(region, view, rect, 100 + 10 + PIP_PX * 2 * 3.5, 200 + 20 + PIP_PX * 2 * 0.5)
    ).toEqual([53, 30]);
    expect(pipAt(region, DEFAULT_VIEW, rect, 99, 200)).toBeNull();
    expect(pipAt(region, DEFAULT_VIEW, rect, 100 + PIP_PX * 20, 200)).toBeNull();
  });

  it('answers the lowest footprint holding a pip, or open ground', () => {
    expect(footprintAt(footprints, 52, 31)?.name).toBe('Barony');
    expect(footprintAt(footprints, 51, 31)?.name).toBe('County');
    expect(footprintAt(footprints, 60, 40)).toBeNull();
  });

  it('colours holders stably and open ground grey', () => {
    expect(holderColor(4)).toBe(holderColor(4));
    expect(holderColor(4)).not.toBe(holderColor(5));
    expect(holderColor(null)).toContain('rgba(120, 110, 100');
  });

  it('centres a label on the footprint', () => {
    expect(centroid(footprints[0].pips)).toEqual([51 + 1 / 3, 31 + 1 / 3]);
    expect(centroid([])).toEqual([0, 0]);
  });
});
