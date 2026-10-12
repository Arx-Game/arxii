import { describe, expect, it, vi } from 'vitest';

import type { RegionMapFootprint, RegionMapPips, RegionMapSummary } from '../../types';
import { DEFAULT_VIEW } from '../latticeState';
import {
  centroid,
  drawRegionMap,
  TERRAIN_COLORS,
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

function recordingCanvas() {
  const paints: { style: string; rect: number[] }[] = [];
  const context = {
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    font: '',
    textAlign: 'start',
    textBaseline: 'alphabetic',
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    strokeText: vi.fn(),
    fillText: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    setLineDash: vi.fn(),
    strokeRect: vi.fn(),
  };
  context.fillRect.mockImplementation((...rect: number[]) => {
    paints.push({ style: context.fillStyle, rect });
  });
  return { context, paints, ctx: context as unknown as CanvasRenderingContext2D };
}

const drawingData: RegionMapPips = {
  region,
  terrains: ['plain', 'water'],
  pips: [
    [51, 31, 'plain', true],
    [52, 31, 'water', false],
  ],
  // Deliberately child first: painting must still put its county underneath.
  footprints: [footprints[1], footprints[0]],
};

describe('region map drawing', () => {
  it('paints terrain, rivers, parent holdings and selected child holdings in order', () => {
    const { ctx, context, paints } = recordingCanvas();
    drawRegionMap(ctx, drawingData, { selectedAreaId: 11 });
    expect(context.clearRect).toHaveBeenCalledWith(0, 0, 120, 120);
    expect(paints[0]).toEqual({ style: TERRAIN_COLORS.water, rect: [0, 0, 120, 120] });
    expect(paints[1]).toEqual({ style: TERRAIN_COLORS.plain, rect: [6, 6, 6, 6] });
    expect(paints[2].style).toBe(TERRAIN_COLORS.water);
    expect(paints[3]).toEqual({ style: '#3f6ea8', rect: [8, 8, 2, 2] });
    expect(paints.slice(4, 7).map((paint) => paint.style)).toEqual([
      holderColor(4),
      holderColor(4),
      holderColor(4),
    ]);
    expect(paints[7]).toEqual({ style: holderColor(4, 0.65), rect: [12, 6, 6, 6] });
    expect(context.arc).toHaveBeenCalledTimes(2);
    expect(context.fillText).toHaveBeenCalledWith('County', expect.any(Number), expect.any(Number));
    expect(context.fillText).not.toHaveBeenCalledWith(
      'Barony',
      expect.any(Number),
      expect.any(Number)
    );
  });

  it('hides labels on request and draws a removal preview after the seated holdings', () => {
    const { ctx, context } = recordingCanvas();
    drawRegionMap(ctx, drawingData, {
      showLabels: false,
      pending: new Set(['51,31']),
      pendingRemove: true,
    });
    expect(context.arc).toHaveBeenCalledTimes(2);
    expect(context.fillText).not.toHaveBeenCalled();
    expect(context.save).toHaveBeenCalledOnce();
    expect(context.setLineDash).toHaveBeenCalledWith([3, 2]);
    expect(context.strokeStyle).toBe('#a0121b');
    expect(context.strokeRect).toHaveBeenCalledWith(7, 7, 4, 4);
    expect(context.strokeRect.mock.invocationCallOrder[0]).toBeGreaterThan(
      context.fill.mock.invocationCallOrder[1]
    );
    expect(context.restore).toHaveBeenCalledOnce();
  });
});
