import { describe, expect, it, vi } from 'vitest';
import { cloud, drawMass, hexToOklch, noise, swirlThreshold } from '@/magic/auraSwirl';

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

describe('drawMass', () => {
  it('reuses its pixel buffer and restores the flat color after drawing a moving swirl', () => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 32;
    const data = new Uint8ClampedArray(canvas.width * canvas.height * 4);
    const context = {
      createImageData: vi.fn(() => ({ data })),
      putImageData: vi.fn(),
    };
    vi.spyOn(canvas, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D);

    const a = hexToOklch('#ff0000');
    const b = hexToOklch('#2962ff');
    drawMass(canvas, a, b, 0, 0);
    const flat = data.slice();
    const center = (16 * canvas.width + 16) * 4;
    expect(flat.slice(center, center + 4)).toEqual(new Uint8ClampedArray([255, 0, 0, 255]));
    expect(flat[3]).toBe(0);

    drawMass(canvas, a, b, 0.5, 0);
    const swirl = data.slice();
    expect(swirl).not.toEqual(flat);
    drawMass(canvas, a, b, 0.5, 4);
    expect(data).not.toEqual(swirl);

    drawMass(canvas, a, b, 0, 4);
    expect(data).toEqual(flat);
    expect(context.createImageData).toHaveBeenCalledTimes(1);
    expect(context.putImageData).toHaveBeenCalledTimes(4);
  });
});
