/**
 * Type Helper Function Tests
 *
 * Tests for helper functions in types.ts:
 * - getDefaultStats()
 */

import { describe, it, expect } from 'vitest';
import { getDefaultStats } from '../types';

describe('getDefaultStats', () => {
  it('returns all 9 primary stats', () => {
    const stats = getDefaultStats();

    expect(Object.keys(stats)).toHaveLength(9);
    expect(stats).toHaveProperty('strength');
    expect(stats).toHaveProperty('agility');
    expect(stats).toHaveProperty('stamina');
    expect(stats).toHaveProperty('charm');
    expect(stats).toHaveProperty('presence');
    expect(stats).toHaveProperty('perception');
    expect(stats).toHaveProperty('intellect');
    expect(stats).toHaveProperty('wits');
    expect(stats).toHaveProperty('willpower');
  });

  it('returns all stats with default value of 20', () => {
    const stats = getDefaultStats();

    expect(stats.strength).toBe(20);
    expect(stats.agility).toBe(20);
    expect(stats.stamina).toBe(20);
    expect(stats.charm).toBe(20);
    expect(stats.presence).toBe(20);
    expect(stats.perception).toBe(20);
    expect(stats.intellect).toBe(20);
    expect(stats.wits).toBe(20);
    expect(stats.willpower).toBe(20);
  });
});
