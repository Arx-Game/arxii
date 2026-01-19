/**
 * Type Helper Function Tests
 *
 * Tests for helper functions in types.ts:
 * - getDefaultStats()
 * - calculateFreePoints()
 */

import { describe, it, expect } from 'vitest';
import { getDefaultStats, calculateFreePoints } from '../types';

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

describe('calculateFreePoints', () => {
  it('returns 5 for default stats (all 20)', () => {
    const stats = getDefaultStats();
    const freePoints = calculateFreePoints(stats);

    // 9 stats * 2 = 18 points, 23 - 18 = 5 free
    expect(freePoints).toBe(5);
  });

  it('returns 0 when all points are spent', () => {
    const stats = {
      strength: 30,
      agility: 30,
      stamina: 30,
      charm: 20,
      presence: 20,
      perception: 20,
      intellect: 20,
      wits: 30,
      willpower: 30,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+3+3+2+2+2+2+3+3 = 23 points, 23 - 23 = 0
    expect(freePoints).toBe(0);
  });

  it('returns negative when over budget', () => {
    const stats = {
      strength: 50,
      agility: 50,
      stamina: 40,
      charm: 20,
      presence: 20,
      perception: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 5+5+4+2+2+2+2+2+2 = 26 points, 23 - 26 = -3
    expect(freePoints).toBe(-3);
  });

  it('returns positive when under budget', () => {
    const stats = {
      strength: 30,
      agility: 20,
      stamina: 20,
      charm: 20,
      presence: 20,
      perception: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+2+2+2+2+2+2+2+2 = 19 points, 23 - 19 = 4
    expect(freePoints).toBe(4);
  });

  it('handles minimum values (all 10)', () => {
    const stats = {
      strength: 10,
      agility: 10,
      stamina: 10,
      charm: 10,
      presence: 10,
      perception: 10,
      intellect: 10,
      wits: 10,
      willpower: 10,
    };

    const freePoints = calculateFreePoints(stats);
    // 9 stats * 1 = 9 points, 23 - 9 = 14 free
    expect(freePoints).toBe(14);
  });

  it('handles maximum values (all 50)', () => {
    const stats = {
      strength: 50,
      agility: 50,
      stamina: 50,
      charm: 50,
      presence: 50,
      perception: 50,
      intellect: 50,
      wits: 50,
      willpower: 50,
    };

    const freePoints = calculateFreePoints(stats);
    // 9 stats * 5 = 45 points, 23 - 45 = -22
    expect(freePoints).toBe(-22);
  });

  it('uses Math.floor for rounding', () => {
    // This tests that we handle any potential rounding issues
    const stats = {
      strength: 25, // If this were in the system, would represent 2.5, but internal it's 25
      agility: 20,
      stamina: 20,
      charm: 20,
      presence: 20,
      perception: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // Using Math.floor: (25+20+20+20+20+20+20+20+20)/10 = 185/10 = 18.5 -> 18
    // 23 - 18 = 5
    expect(freePoints).toBe(5);
  });

  it('handles partial point allocations correctly', () => {
    const stats = {
      strength: 30,
      agility: 30,
      stamina: 10,
      charm: 20,
      presence: 20,
      perception: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+3+1+2+2+2+2+2+2 = 19 points, 23 - 19 = 4
    expect(freePoints).toBe(4);
  });
});
