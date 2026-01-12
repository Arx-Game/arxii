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
  it('returns all 8 primary stats', () => {
    const stats = getDefaultStats();

    expect(Object.keys(stats)).toHaveLength(8);
    expect(stats).toHaveProperty('strength');
    expect(stats).toHaveProperty('agility');
    expect(stats).toHaveProperty('stamina');
    expect(stats).toHaveProperty('charm');
    expect(stats).toHaveProperty('presence');
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
    expect(stats.intellect).toBe(20);
    expect(stats.wits).toBe(20);
    expect(stats.willpower).toBe(20);
  });
});

describe('calculateFreePoints', () => {
  it('returns 5 for default stats (all 20)', () => {
    const stats = getDefaultStats();
    const freePoints = calculateFreePoints(stats);

    // 8 stats * 2 = 16 points, 21 - 16 = 5 free
    expect(freePoints).toBe(5);
  });

  it('returns 0 when all points are spent', () => {
    const stats = {
      strength: 30,
      agility: 30,
      stamina: 20,
      charm: 20,
      presence: 20,
      intellect: 20,
      wits: 20,
      willpower: 30,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+3+2+2+2+2+2+3 = 21 points, 21 - 21 = 0
    expect(freePoints).toBe(0);
  });

  it('returns negative when over budget', () => {
    const stats = {
      strength: 50,
      agility: 50,
      stamina: 20,
      charm: 20,
      presence: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 5+5+2+2+2+2+2+2 = 24 points, 21 - 24 = -3
    expect(freePoints).toBe(-3);
  });

  it('returns positive when under budget', () => {
    const stats = {
      strength: 30,
      agility: 20,
      stamina: 20,
      charm: 20,
      presence: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+2+2+2+2+2+2+2 = 17 points, 21 - 17 = 4
    expect(freePoints).toBe(4);
  });

  it('handles minimum values (all 10)', () => {
    const stats = {
      strength: 10,
      agility: 10,
      stamina: 10,
      charm: 10,
      presence: 10,
      intellect: 10,
      wits: 10,
      willpower: 10,
    };

    const freePoints = calculateFreePoints(stats);
    // 8 stats * 1 = 8 points, 21 - 8 = 13 free
    expect(freePoints).toBe(13);
  });

  it('handles maximum values (all 50)', () => {
    const stats = {
      strength: 50,
      agility: 50,
      stamina: 50,
      charm: 50,
      presence: 50,
      intellect: 50,
      wits: 50,
      willpower: 50,
    };

    const freePoints = calculateFreePoints(stats);
    // 8 stats * 5 = 40 points, 21 - 40 = -19
    expect(freePoints).toBe(-19);
  });

  it('uses Math.floor for rounding', () => {
    // This tests that we handle any potential rounding issues
    const stats = {
      strength: 25, // If this were in the system, would represent 2.5, but internal it's 25
      agility: 20,
      stamina: 20,
      charm: 20,
      presence: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // Using Math.floor: (25+20+20+20+20+20+20+20)/10 = 165/10 = 16.5 -> 16
    // 21 - 16 = 5
    expect(freePoints).toBe(5);
  });

  it('handles partial point allocations correctly', () => {
    const stats = {
      strength: 30,
      agility: 30,
      stamina: 10,
      charm: 20,
      presence: 20,
      intellect: 20,
      wits: 20,
      willpower: 20,
    };

    const freePoints = calculateFreePoints(stats);
    // 3+3+1+2+2+2+2+2 = 17 points, 21 - 17 = 4
    expect(freePoints).toBe(4);
  });
});
