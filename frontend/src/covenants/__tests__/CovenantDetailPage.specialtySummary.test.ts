/**
 * specialtySummaryForMembership tests (#2443)
 *
 * Covers:
 *   1. Unions the anchor role's and resolved role's technique_specialties.
 *   2. Dedups by function when the same function appears on both anchor and
 *      resolved (sub-role) rows — the resolved (sub-role) row's multiplier wins,
 *      since sub-role rows are the escalation layered on top of the anchor.
 *   3. Returns an empty list when neither role carries any specialty rows.
 *   4. Formats the multiplier as ×<tenths/10>, including whole-number values
 *      (multiplier_tenths 10 -> ×1, not ×1.0).
 */

import { describe, it, expect } from 'vitest';
import { specialtySummaryForMembership } from '../pages/CovenantDetailPage';

describe('specialtySummaryForMembership', () => {
  it('unions anchor and resolved role specialties when functions differ', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: {
        technique_specialties: [
          { function: 'charm', function_display: 'Charm', multiplier_tenths: 15 },
        ],
      },
      anchor_role: {
        technique_specialties: [
          { function: 'barrier', function_display: 'Barrier', multiplier_tenths: 10 },
        ],
      },
    });
    expect(chips).toHaveLength(2);
    expect(chips.map((c) => c.function).sort()).toEqual(['barrier', 'charm']);
  });

  it('dedups by function, preferring the resolved (sub-role) row on collision', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: {
        technique_specialties: [
          { function: 'charm', function_display: 'Charm', multiplier_tenths: 20 },
        ],
      },
      anchor_role: {
        technique_specialties: [
          { function: 'charm', function_display: 'Charm', multiplier_tenths: 15 },
        ],
      },
    });
    expect(chips).toHaveLength(1);
    expect(chips[0]).toEqual({ function: 'charm', label: 'Charm ×2' });
  });

  it('returns an empty list when neither role has specialty rows', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: { technique_specialties: [] },
      anchor_role: { technique_specialties: [] },
    });
    expect(chips).toEqual([]);
  });

  it('returns an empty list when anchor_role is absent and resolved role has none', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: { technique_specialties: [] },
      anchor_role: undefined,
    });
    expect(chips).toEqual([]);
  });

  it('formats multiplier_tenths 15 as ×1.5', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: {
        technique_specialties: [
          { function: 'charm', function_display: 'Charm', multiplier_tenths: 15 },
        ],
      },
      anchor_role: { technique_specialties: [] },
    });
    expect(chips[0].label).toBe('Charm ×1.5');
  });

  it('formats multiplier_tenths 10 (×1) without a trailing .0', () => {
    const chips = specialtySummaryForMembership({
      covenant_role: {
        technique_specialties: [
          { function: 'mobility', function_display: 'Mobility', multiplier_tenths: 10 },
        ],
      },
      anchor_role: { technique_specialties: [] },
    });
    expect(chips[0].label).toBe('Mobility ×1');
  });
});
