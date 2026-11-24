/**
 * The swirling aura drawing (#5231), ported from the approved demo's `drawMass` and its
 * helpers. The constants and the arithmetic are the demo's, so the look the maintainer
 * approved is the look that ships.
 *
 * An aura is one mass of up to two colours. Each pixel of the disc reads a twisted cloud of
 * noise, and the top `q` of the in-disc cloud values is painted in the second colour, so
 * that colour covers exactly its share of the disc however the noise falls.
 *
 * Colours are OKLCH triples, `[lightness, chroma, hue in degrees]`. The server sends hex
 * strings, so `hexToOklch` is the way in.
 */

export type Oklch = [number, number, number];
export type Rgb = [number, number, number];

/** The neutral grey: the colour a resonance starts with, and the aura's for an unreadable one. */
export const NEUTRAL_HEX = '#8C8C8C';

/** Steps in a colour ramp, from the first colour to the second. */
const RAMP_STEPS = 32;
/** Histogram bins for the share cut. */
const HIST_BINS = 256;
/** Radius of the painted disc, as a fraction of half the canvas. */
const DISC_RADIUS = 0.72;
/** Radius inside which the twisted cloud is sampled. */
const CLOUD_RADIUS = 0.78;
/** Threshold above every cloud value, used when the second colour has no share. */
const NO_SHARE_THRESHOLD = 2;

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** A CSS `oklch()` colour with an alpha. */
export function oklchCss(c: Oklch, alpha: number): string {
  return `oklch(${c[0].toFixed(3)} ${c[1].toFixed(3)} ${c[2].toFixed(1)} / ${clamp(alpha, 0, 1).toFixed(2)})`;
}

/** Lightness, chroma and hue as OKLab's lightness, a and b. */
function lab(c: Oklch): [number, number, number] {
  const r = (c[2] * Math.PI) / 180;
  return [c[0], c[1] * Math.cos(r), c[1] * Math.sin(r)];
}

/** Linear light to the 0..255 sRGB channel. */
function gamma(x: number): number {
  const v = clamp(x, 0, 1);
  return 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055);
}

/** The 0..1 sRGB channel to linear light. */
function linear(x: number): number {
  return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
}

/** OKLab to sRGB channels in 0..255. */
function rgbOf(L: number, A: number, B: number): Rgb {
  const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
  const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
  const q = Math.pow(L - 0.0894841775 * A - 1.291485548 * B, 3);
  return [
    gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * q),
    gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * q),
    gamma(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * q),
  ];
}

/** `#RRGGBB` to OKLCH: sRGB, linear light, LMS, OKLab, then lightness, chroma and hue. */
export function hexToOklch(hex: string): Oklch {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) {
    throw new RangeError(`Not a #RRGGBB colour: ${hex}`);
  }
  const [r, g, b] = [match[1], match[2], match[3]].map((p) => linear(parseInt(p, 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const chroma = Math.sqrt(A * A + B * B);
  const hue = ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360;
  return [L, chroma, hue];
}

/** A brighter stand-in for a dark colour, so its rim can be seen against a night plate. */
export function lift(c: Oklch): Oklch {
  return [Math.max(c[0], 0.64), Math.max(c[1], 0.11), c[2]];
}

function smooth(lo: number, hi: number, v: number): number {
  const t = clamp((v - lo) / (hi - lo), 0, 1);
  return t * t * (3 - 2 * t);
}

/** 33 steps from one colour to the other, mixed in OKLab where the eye mixes them. */
export function ramp(a: Oklch, b: Oklch): Rgb[] {
  const x = lab(a);
  const y = lab(b);
  const out: Rgb[] = [];
  for (let i = 0; i <= RAMP_STEPS; i++) {
    const t = i / RAMP_STEPS;
    out.push(rgbOf(x[0] + (y[0] - x[0]) * t, x[1] + (y[1] - x[1]) * t, x[2] + (y[2] - x[2]) * t));
  }
  return out;
}

/** The permutation table every noise lookup reads, shuffled from a fixed seed. */
const PERM: Uint8Array = (() => {
  const perm = new Uint8Array(512);
  let seed = 20261120;
  for (let i = 0; i < 256; i++) perm[i] = i;
  for (let i = 255; i > 0; i--) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const j = seed % (i + 1);
    const t = perm[i];
    perm[i] = perm[j];
    perm[j] = t;
  }
  for (let i = 0; i < 256; i++) perm[i + 256] = perm[i];
  return perm;
})();

/** Smooth value noise in 0..1. */
export function noise(x: number, y: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  const X = xi & 255;
  const Y = yi & 255;
  const a = PERM[PERM[X] + Y];
  const b = PERM[PERM[X + 1] + Y];
  const c = PERM[PERM[X] + Y + 1];
  const d = PERM[PERM[X + 1] + Y + 1];
  const top = a + (b - a) * u;
  return (top + (c + (d - c) * u - top) * v) / 255;
}

/** Four octaves of noise in 0..1. */
export function cloud(x: number, y: number): number {
  return (
    (noise(x, y) * 0.5 +
      noise(x * 2.03 + 31, y * 2.03 + 7) * 0.25 +
      noise(x * 4.1 + 5, y * 4.1 + 53) * 0.125 +
      noise(x * 8.2 + 71, y * 8.2 + 19) * 0.0625) /
    0.9375
  );
}

/**
 * The cloud value above which the top `q` of the in-disc values sit. `values` holds the
 * cloud value per pixel, with a negative number for a pixel outside the disc; `count` is
 * the number of in-disc values. The cut is read off a 256-bin histogram and interpolated
 * inside its bin, so the second colour covers `q` of the disc to within a pixel or two.
 * A `q` of 0 gives a threshold above every value.
 */
export function swirlThreshold(values: Float32Array, count: number, q: number): number {
  if (q <= 0) return NO_SHARE_THRESHOLD;
  const hist = new Uint32Array(HIST_BINS);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v >= 0) hist[Math.min(HIST_BINS - 1, Math.floor(v * HIST_BINS))]++;
  }
  const need = q * count;
  let seen = 0;
  let bin = HIST_BINS - 1;
  while (bin > 0 && seen + hist[bin] < need) {
    seen += hist[bin];
    bin--;
  }
  return (bin + 1 - (need - seen) / Math.max(1, hist[bin])) / HIST_BINS;
}

/** The buffers one canvas reuses from frame to frame. */
interface MassBuffers {
  size: number;
  ctx: CanvasRenderingContext2D;
  img: ImageData;
  n: Float32Array;
  u: Float32Array;
  v: Float32Array;
}

const BUFFERS = new WeakMap<HTMLCanvasElement, MassBuffers>();

function buffersFor(canvas: HTMLCanvasElement): MassBuffers | null {
  const size = canvas.width;
  const held = BUFFERS.get(canvas);
  if (held && held.size === size) return held;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const made: MassBuffers = {
    size,
    ctx,
    img: ctx.createImageData(size, size),
    n: new Float32Array(size * size),
    u: new Float32Array(size * size),
    v: new Float32Array(size * size),
  };
  BUFFERS.set(canvas, made);
  return made;
}

/** Fill the reusable sample buffers and find the cut for the requested color share. */
function sampleSwirl({ size: S, n: N, u: U, v: V }: MassBuffers, q: number, time: number): number {
  const rot = time * 0.1;
  const ox = 3 + time * 0.045;
  const oy = 9 + time * 0.03;
  let count = 0;
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const nx = ((x + 0.5) / S) * 2 - 1;
      const ny = ((y + 0.5) / S) * 2 - 1;
      const r = Math.sqrt(nx * nx + ny * ny);
      const i = y * S + x;
      if (r > CLOUD_RADIUS) {
        N[i] = -1;
        continue;
      }
      const ang = 4.4 * (1 - r / CLOUD_RADIUS) + rot;
      const cs = Math.cos(ang);
      const sn = Math.sin(ang);
      U[i] = (nx * cs - ny * sn) * 2.7 + ox;
      V[i] = (nx * sn + ny * cs) * 2.7 + oy;
      N[i] = cloud(U[i], V[i]);
      count++;
    }
  }
  return swirlThreshold(N, count, q);
}

/**
 * Draw the mass onto `canvas`: colour `a`, with colour `b` covering a share `q` of it
 * (`b` null or `q` 0 draws `a` alone). `time` is in seconds and moves the swirl.
 */
export function drawMass(
  canvas: HTMLCanvasElement,
  a: Oklch,
  b: Oklch | null,
  q: number,
  time: number
): void {
  const buf = buffersFor(canvas);
  if (!buf) return;
  const { size: S, ctx, img, n: N, u: U, v: V } = buf;
  const data = img.data;
  const lut = ramp(a, b ?? a);
  const R = DISC_RADIUS;
  const th = q > 0 ? sampleSwirl(buf, q, time) : NO_SHARE_THRESHOLD;
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      const nx = ((x + 0.5) / S) * 2 - 1;
      const ny = ((y + 0.5) / S) * 2 - 1;
      const r = Math.sqrt(nx * nx + ny * ny);
      const i = y * S + x;
      const o = i * 4;
      const edge = 1 - smooth(R - 0.05, R + 0.04, r);
      if (edge <= 0) {
        data[o + 3] = 0;
        continue;
      }
      const t = q > 0 ? smooth(th - 0.022, th + 0.022, N[i]) : 0;
      const shade = q > 0 ? 0.86 + 0.28 * noise(U[i] * 2.4 + 17, V[i] * 2.4 + 41) : 1;
      const c = lut[Math.round(t * RAMP_STEPS)];
      data[o] = c[0] * shade;
      data[o + 1] = c[1] * shade;
      data[o + 2] = c[2] * shade;
      data[o + 3] = 255 * edge;
    }
  }
  ctx.putImageData(img, 0, 0);
}

/** The glow and rim styles the demo's `paint` derives from the two colours and the share. */
export interface MassFrame {
  bloomBackground: string;
  rimBorderColor: string;
  rimBoxShadow: string;
  rimOpacity: number;
}

export function massFrame(a: Oklch, b: Oklch | null, q: number): MassFrame {
  const gA = clamp((a[0] - 0.3) * 1.15, 0, 0.85) * Math.sqrt(1 - q);
  const gB = b ? clamp((b[0] - 0.3) * 1.15, 0, 0.85) * Math.sqrt(q) : 0;
  const avg = a[0] * (1 - q) + (b ? b[0] * q : 0);
  const lit = lift(b && b[0] < a[0] ? b : a);
  return {
    bloomBackground: `radial-gradient(circle closest-side, ${oklchCss(b && gB > gA ? b : a, Math.max(gA, gB))} 55%, transparent 100%)`,
    rimBorderColor: oklchCss(lit, 1),
    rimBoxShadow: `0 0 1rem ${oklchCss(lit, 0.9)}, inset 0 0 0.5rem ${oklchCss(lit, 0.5)}`,
    rimOpacity: Number(clamp((0.5 - avg) / 0.28, 0, 1).toFixed(2)),
  };
}
