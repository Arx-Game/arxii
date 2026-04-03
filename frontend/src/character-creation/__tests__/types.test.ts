/**
 * Type Helper Function Tests
 *
 * Tests for helper functions in types.ts:
 * - getDefaultStats()
 */

import { describe, it, expect } from 'vitest';
import { getDefaultStats } from '../types';

describe('getDefaultStats', () => {
  it('returns all 12 primary stats', () => {
    const stats = getDefaultStats();

    expect(Object.keys(stats)).toHaveLength(12);
    expect(stats).toHaveProperty('strength');
    expect(stats).toHaveProperty('agility');
    expect(stats).toHaveProperty('stamina');
    expect(stats).toHaveProperty('charm');
    expect(stats).toHaveProperty('presence');
    expect(stats).toHaveProperty('composure');
    expect(stats).toHaveProperty('intellect');
    expect(stats).toHaveProperty('wits');
    expect(stats).toHaveProperty('stability');
    expect(stats).toHaveProperty('luck');
    expect(stats).toHaveProperty('perception');
    expect(stats).toHaveProperty('willpower');
  });

  it('returns all stats with default value of 2', () => {
    const stats = getDefaultStats();

    expect(stats.strength).toBe(2);
    expect(stats.agility).toBe(2);
    expect(stats.stamina).toBe(2);
    expect(stats.charm).toBe(2);
    expect(stats.presence).toBe(2);
    expect(stats.composure).toBe(2);
    expect(stats.intellect).toBe(2);
    expect(stats.wits).toBe(2);
    expect(stats.stability).toBe(2);
    expect(stats.luck).toBe(2);
    expect(stats.perception).toBe(2);
    expect(stats.willpower).toBe(2);
  });
});
