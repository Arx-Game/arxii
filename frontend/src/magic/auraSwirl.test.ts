import { describe, expect, it } from 'vitest';
import { cloud, hexToOklch, oklchToHex, ramp, swirlThreshold, type Oklch } from '@/magic/auraSwirl';

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

  it('round-trips the demo colour Arderi through hex', () => {
    const arderi: Oklch = [0.68, 0.19, 45];
    const back = hexToOklch(oklchToHex(arderi));
    expect(Math.abs(back[0] - arderi[0])).toBeLessThan(0.01);
    expect(Math.abs(back[1] - arderi[1])).toBeLessThan(0.01);
  });

  it('refuses a string that is not #RRGGBB', () => {
    expect(() => hexToOklch('red')).toThrow(RangeError);
  });
});

describe('ramp', () => {
  it('runs 33 steps from the first colour to the second', () => {
    const steps = ramp([0.68, 0.19, 45], [0.22, 0.1, 20]);
    expect(steps).toHaveLength(33);
    expect(steps[0][0]).toBeGreaterThan(steps[32][0]);
  });
});
