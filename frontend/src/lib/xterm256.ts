/**
 * xterm-256 color lookup table and utilities.
 *
 * Color ranges:
 *   0-7:     Standard colors
 *   8-15:    Bright/bold colors
 *   16-231:  6x6x6 RGB cube
 *   232-255: Grayscale ramp
 */

const STANDARD_COLORS: string[] = [
  '#000000', // 0  black
  '#800000', // 1  red
  '#008000', // 2  green
  '#808000', // 3  yellow
  '#000080', // 4  blue
  '#800080', // 5  magenta
  '#008080', // 6  cyan
  '#c0c0c0', // 7  white
  '#808080', // 8  bright black (gray)
  '#ff0000', // 9  bright red
  '#00ff00', // 10 bright green
  '#ffff00', // 11 bright yellow
  '#0000ff', // 12 bright blue
  '#ff00ff', // 13 bright magenta
  '#00ffff', // 14 bright cyan
  '#ffffff', // 15 bright white
];

const CUBE_LEVELS = [0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff];

function toHex(n: number): string {
  return n.toString(16).padStart(2, '0');
}

function buildTable(): Record<number, string> {
  const table: Record<number, string> = {};

  // 0-15: standard + bright
  for (let i = 0; i < 16; i++) {
    table[i] = STANDARD_COLORS[i];
  }

  // 16-231: 6x6x6 RGB cube
  for (let r = 0; r < 6; r++) {
    for (let g = 0; g < 6; g++) {
      for (let b = 0; b < 6; b++) {
        const index = 16 + 36 * r + 6 * g + b;
        table[index] = `#${toHex(CUBE_LEVELS[r])}${toHex(CUBE_LEVELS[g])}${toHex(CUBE_LEVELS[b])}`;
      }
    }
  }

  // 232-255: grayscale
  for (let i = 0; i < 24; i++) {
    const v = 8 + i * 10;
    table[232 + i] = `#${toHex(v)}${toHex(v)}${toHex(v)}`;
  }

  return table;
}

/** Pre-computed mapping from xterm-256 index to hex color string. */
export const XTERM_TO_HEX: Record<number, string> = buildTable();

/** Evennia/MU* named color shortcuts → xterm index. */
export const MU_COLOR_NAMES: Record<string, number> = {
  r: 1,
  R: 9,
  g: 2,
  G: 10,
  b: 4,
  B: 12,
  y: 3,
  Y: 11,
  c: 6,
  C: 14,
  m: 5,
  M: 13,
  w: 7,
  W: 15,
  x: 8,
  X: 0,
};

/** Look up the hex value for an xterm-256 index. */
export function xtermToHex(index: number): string | undefined {
  return XTERM_TO_HEX[index];
}

/** Look up the hex value for an MU* color name shortcut. */
export function muColorToHex(name: string): string | undefined {
  const index = MU_COLOR_NAMES[name];
  if (index === undefined) return undefined;
  return XTERM_TO_HEX[index];
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

/** Find the nearest xterm-256 index to an arbitrary hex color (Euclidean distance in RGB). */
export function hexToNearestXterm(hex: string): number {
  const [tr, tg, tb] = hexToRgb(hex);
  let bestIndex = 0;
  let bestDist = Infinity;

  for (let i = 0; i < 256; i++) {
    const [cr, cg, cb] = hexToRgb(XTERM_TO_HEX[i]);
    const dist = (tr - cr) ** 2 + (tg - cg) ** 2 + (tb - cb) ** 2;
    if (dist < bestDist) {
      bestDist = dist;
      bestIndex = i;
    }
  }

  return bestIndex;
}
