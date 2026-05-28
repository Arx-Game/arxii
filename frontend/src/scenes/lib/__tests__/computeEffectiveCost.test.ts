import { describe, it, expect } from 'vitest';
import { computeEffectiveCost } from '../computeEffectiveCost';

describe('computeEffectiveCost', () => {
  it('returns base cost when strain is zero', () => {
    expect(computeEffectiveCost(5, 0)).toBe(5);
  });

  it('adds strain to base cost', () => {
    expect(computeEffectiveCost(5, 3)).toBe(8);
  });

  it('treats negative strain as zero', () => {
    expect(computeEffectiveCost(5, -2)).toBe(5);
  });
});
