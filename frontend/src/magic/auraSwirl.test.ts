import { describe, expect, it } from 'vitest';
import { cloud, hexToOklch, noise, swirlThreshold } from '@/magic/auraSwirl';

function cloudSamples(count: number): Float32Array {
  const side = Math.sqrt(count);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    out[i] = cloud((i % side) * 0.07 + 3, Math.floor(i / side) * 0.07 + 9);
  }
  return out;
}

describe('swirlThreshold', () => {
  const samples = cloudSamples(10000);

  it.each([0.1, 0.3, 0.5, 0.9])('puts a share of %s of the samples at or above the cut', (q) => {
    const cut = swirlThreshold(samples, samples.length, q);
    const above = samples.filter((v) => v >= cut).length / samples.length;
    expect(Math.abs(above - q)).toBeLessThan(0.01);
  });

  it('gives a cut above every sample when the share is zero', () => {
    const cut = swirlThreshold(samples, samples.length, 0);
    expect(samples.every((v) => v < cut)).toBe(true);
  });
});

describe('hexToOklch', () => {
  it('reads white as full lightness and black as none', () => {
    expect(hexToOklch('#ffffff')[0]).toBeCloseTo(1, 2);
    expect(hexToOklch('#000000')[0]).toBeCloseTo(0, 2);
  });

  it('reads #ff0000 as the CSS Color 4 reference gives it, oklch(0.628 0.2577 29.23)', () => {
    const [lightness, chroma, hue] = hexToOklch('#ff0000');
    expect(lightness).toBeCloseTo(0.628, 3);
    expect(chroma).toBeCloseTo(0.2577, 3);
    expect(hue).toBeCloseTo(29.2, 1);
  });

  it('refuses a string that is not #RRGGBB', () => {
    expect(() => hexToOklch('red')).toThrow(RangeError);
  });
});

describe('noise', () => {
  it('matches the approved demo at a fixed point', () => {
    // 0.3189504 is the demo's own noise(3.3, 9.7), run from its <script> with its seed 20261120.
    expect(noise(3.3, 9.7)).toBeCloseTo(0.3189504, 9);
  });
});
