/**
 * The region map's drawing and hit-testing, kept pure so it can be tested without a
 * canvas (#4242). A pip is a 10-mile square; `PIP_PX` is its size on the canvas at
 * zoom 1. World coordinates come from the server; the canvas is region-local, so
 * every world pip is shifted by the region's first pip before drawing.
 */
import type { LatticeView } from './latticeState';
import type { RegionMapFootprint, RegionMapPips, RegionMapSummary } from '../types';

export const PIP_PX = 6;

/** Flat colour per terrain: the first pass the owner ruled; tile art is a later styling pass. */
export const TERRAIN_COLORS: Record<string, string> = {
  water: '#7d9ec4',
  lake: '#8fb3d6',
  plain: '#d9d6a3',
  forest: '#5f9a5a',
  hill: '#b6a66f',
  mountain: '#8d8781',
  marsh: '#6f9c86',
  desert: '#e3cf8e',
  tundra: '#b8a98c',
  glacier: '#e9f0f4',
};
const RIVER_COLOR = '#3f6ea8';
const CELL_LINE_COLOR = 'rgba(40, 32, 20, 0.22)';
const COAST_COLOR = 'rgba(30, 50, 80, 0.45)';
const WATER_TERRAINS = new Set(['water', 'lake']);

export function pipKey(x: number, y: number): string {
  return `${x},${y}`;
}

export function regionBounds(region: RegionMapSummary) {
  const per = region.pips_per_cell;
  const x0 = region.anchor_x * per;
  const y0 = region.anchor_y * per;
  return {
    x0,
    y0,
    width: region.width_cells * per,
    height: region.height_cells * per,
    per,
  };
}

/**
 * The world pip under a pointer position. `rect` is the viewport's bounding box,
 * `view` the zoom and pan of the canvas inside it. `null` outside the region.
 */
export function pipAt(
  region: RegionMapSummary,
  view: LatticeView,
  rect: { left: number; top: number },
  clientX: number,
  clientY: number
): [number, number] | null {
  const b = regionBounds(region);
  const localX = (clientX - rect.left - view.panX) / view.zoom / PIP_PX;
  const localY = (clientY - rect.top - view.panY) / view.zoom / PIP_PX;
  const x = Math.floor(localX);
  const y = Math.floor(localY);
  if (x < 0 || y < 0 || x >= b.width || y >= b.height) return null;
  return [b.x0 + x, b.y0 + y];
}

/** A stable colour for a holder: hue from the org id; open and unclaimed land share a grey. */
export function holderColor(orgId: number | null, alpha = 0.45): string {
  if (orgId == null) return `rgba(120, 110, 100, ${alpha})`;
  const hue = (orgId * 137.508) % 360;
  return `hsla(${hue.toFixed(0)}, 62%, 42%, ${alpha})`;
}

/** The lowest-level footprint holding a pip, or null for open ground. */
export function footprintAt(
  footprints: RegionMapFootprint[],
  x: number,
  y: number
): RegionMapFootprint | null {
  const key = pipKey(x, y);
  let best: RegionMapFootprint | null = null;
  for (const footprint of footprints) {
    if (best && footprint.level >= best.level) continue;
    if (footprint.pips.some(([px, py]) => pipKey(px, py) === key)) best = footprint;
  }
  return best;
}

export function centroid(pips: [number, number][]): [number, number] {
  if (pips.length === 0) return [0, 0];
  let sx = 0;
  let sy = 0;
  for (const [x, y] of pips) {
    sx += x;
    sy += y;
  }
  return [sx / pips.length, sy / pips.length];
}

export interface DrawOptions {
  /** World pips being added or removed in a drag, drawn as a dashed outline. */
  pending?: Set<string>;
  pendingRemove?: boolean;
  selectedAreaId?: number | null;
  showLabels?: boolean;
}

/**
 * Draw the whole map at zoom 1 onto a canvas sized to the region. Terrain first,
 * then rivers, the coast, cell lines, footprints by holder, seats and names.
 */
export function drawRegionMap(
  ctx: CanvasRenderingContext2D,
  data: RegionMapPips,
  options: DrawOptions = {}
): void {
  const b = regionBounds(data.region);
  const W = b.width * PIP_PX;
  const H = b.height * PIP_PX;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = TERRAIN_COLORS.water;
  ctx.fillRect(0, 0, W, H);

  const terrainAt = new Map<string, string>();
  for (const [x, y, terrain] of data.pips) {
    terrainAt.set(pipKey(x, y), terrain);
    ctx.fillStyle = TERRAIN_COLORS[terrain] ?? '#c0c0c0';
    ctx.fillRect((x - b.x0) * PIP_PX, (y - b.y0) * PIP_PX, PIP_PX, PIP_PX);
  }
  // rivers: a stroke across the pip
  ctx.fillStyle = RIVER_COLOR;
  for (const [x, y, , river] of data.pips) {
    if (!river) continue;
    ctx.fillRect(
      (x - b.x0) * PIP_PX + PIP_PX / 3,
      (y - b.y0) * PIP_PX + PIP_PX / 3,
      PIP_PX / 3,
      PIP_PX / 3
    );
  }
  // the coast: land pips with water to the east or south get an edge, read from neighbours
  ctx.strokeStyle = COAST_COLOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const [x, y, terrain] of data.pips) {
    const land = !WATER_TERRAINS.has(terrain);
    const east = terrainAt.get(pipKey(x + 1, y));
    const south = terrainAt.get(pipKey(x, y + 1));
    const px = (x - b.x0) * PIP_PX;
    const py = (y - b.y0) * PIP_PX;
    if (east !== undefined && land !== !WATER_TERRAINS.has(east)) {
      ctx.moveTo(px + PIP_PX, py);
      ctx.lineTo(px + PIP_PX, py + PIP_PX);
    }
    if (south !== undefined && land !== !WATER_TERRAINS.has(south)) {
      ctx.moveTo(px, py + PIP_PX);
      ctx.lineTo(px + PIP_PX, py + PIP_PX);
    }
  }
  ctx.stroke();
  // cell lines every ten pips
  ctx.strokeStyle = CELL_LINE_COLOR;
  ctx.beginPath();
  for (let cx = 0; cx <= b.width; cx += b.per) {
    ctx.moveTo(cx * PIP_PX + 0.5, 0);
    ctx.lineTo(cx * PIP_PX + 0.5, H);
  }
  for (let cy = 0; cy <= b.height; cy += b.per) {
    ctx.moveTo(0, cy * PIP_PX + 0.5);
    ctx.lineTo(W, cy * PIP_PX + 0.5);
  }
  ctx.stroke();

  // footprints: largest first so a barony draws over its county
  const footprints = [...data.footprints].sort((a, c) => c.level - a.level);
  for (const footprint of footprints) {
    const selected = options.selectedAreaId === footprint.area_id;
    ctx.fillStyle = holderColor(footprint.holder_org_id, selected ? 0.65 : 0.45);
    for (const [x, y] of footprint.pips) {
      ctx.fillRect((x - b.x0) * PIP_PX, (y - b.y0) * PIP_PX, PIP_PX, PIP_PX);
    }
    const own = new Set(footprint.pips.map(([x, y]) => pipKey(x, y)));
    ctx.strokeStyle = selected ? '#1a140c' : 'rgba(26, 20, 12, 0.75)';
    ctx.lineWidth = selected ? 2 : 1;
    ctx.beginPath();
    for (const [x, y] of footprint.pips) {
      const px = (x - b.x0) * PIP_PX;
      const py = (y - b.y0) * PIP_PX;
      if (!own.has(pipKey(x, y - 1))) {
        ctx.moveTo(px, py);
        ctx.lineTo(px + PIP_PX, py);
      }
      if (!own.has(pipKey(x, y + 1))) {
        ctx.moveTo(px, py + PIP_PX);
        ctx.lineTo(px + PIP_PX, py + PIP_PX);
      }
      if (!own.has(pipKey(x - 1, y))) {
        ctx.moveTo(px, py);
        ctx.lineTo(px, py + PIP_PX);
      }
      if (!own.has(pipKey(x + 1, y))) {
        ctx.moveTo(px + PIP_PX, py);
        ctx.lineTo(px + PIP_PX, py + PIP_PX);
      }
    }
    ctx.stroke();
  }
  // seats and names
  for (const footprint of footprints) {
    if (footprint.seat) {
      const [sx, sy] = footprint.seat;
      ctx.fillStyle = '#1a140c';
      ctx.beginPath();
      ctx.arc(
        (sx - b.x0) * PIP_PX + PIP_PX / 2,
        (sy - b.y0) * PIP_PX + PIP_PX / 2,
        PIP_PX / 2.2,
        0,
        Math.PI * 2
      );
      ctx.fill();
    }
    if (options.showLabels !== false && footprint.name && footprint.pips.length > 1) {
      const [cx, cy] = centroid(footprint.pips);
      ctx.font = `${Math.max(10, PIP_PX * 2)}px "Cormorant Garamond", Georgia, serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(255, 250, 240, 0.9)';
      ctx.fillStyle = '#1a140c';
      const lx = (cx - b.x0 + 0.5) * PIP_PX;
      const ly = (cy - b.y0 + 0.5) * PIP_PX;
      ctx.strokeText(footprint.name, lx, ly);
      ctx.fillText(footprint.name, lx, ly);
    }
  }
  // the drag in progress
  if (options.pending && options.pending.size > 0) {
    ctx.save();
    ctx.setLineDash([3, 2]);
    ctx.strokeStyle = options.pendingRemove ? '#a0121b' : '#1a5e2a';
    ctx.lineWidth = 2;
    for (const key of options.pending) {
      const [x, y] = key.split(',').map(Number);
      ctx.strokeRect((x - b.x0) * PIP_PX + 1, (y - b.y0) * PIP_PX + 1, PIP_PX - 2, PIP_PX - 2);
    }
    ctx.restore();
  }
}
