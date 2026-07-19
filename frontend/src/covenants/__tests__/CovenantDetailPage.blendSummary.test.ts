/**
 * blendSummary / blendSummaryForMembership tests (#2529)
 *
 * Covers:
 *   1. blendSummary formats nonzero-only axes, ordered Sword→Shield→Crown, '·'-separated.
 *   2. blendSummary falls back to "Unaligned" when all weights are zero.
 *   3. blendSummaryForMembership uses the resolved role's weights when nonzero.
 *   4. blendSummaryForMembership falls back to the anchor role's weights when the
 *      resolved role (a sub-role) carries all-zero weights.
 *   5. blendSummaryForMembership falls back to "Unaligned" when the resolved role
 *      is all-zero AND no anchor role is present.
 */

import { describe, it, expect } from 'vitest';
import { blendSummary, blendSummaryForMembership } from '../pages/CovenantDetailPage';

describe('blendSummary', () => {
  it('formats a single nonzero axis at 100%', () => {
    expect(
      blendSummary({ sword_weight: '1.000', shield_weight: '0.000', crown_weight: '0.000' })
    ).toBe('Sword 100%');
  });

  it('formats multiple nonzero axes, ordered Sword→Shield→Crown, separated by ·', () => {
    expect(
      blendSummary({ sword_weight: '0.600', shield_weight: '0.000', crown_weight: '0.400' })
    ).toBe('Sword 60% · Crown 40%');
  });

  it('returns "Unaligned" when all weights are zero', () => {
    expect(
      blendSummary({ sword_weight: '0.000', shield_weight: '0.000', crown_weight: '0.000' })
    ).toBe('Unaligned');
  });
});

describe('blendSummaryForMembership', () => {
  it('uses the resolved role weights when nonzero', () => {
    expect(
      blendSummaryForMembership({
        covenant_role: { sword_weight: '0.600', shield_weight: '0.400', crown_weight: '0.000' },
        anchor_role: { sword_weight: '1.000', shield_weight: '0.000', crown_weight: '0.000' },
      })
    ).toBe('Sword 60% · Shield 40%');
  });

  it('falls back to anchor_role weights when the resolved role is all-zero', () => {
    expect(
      blendSummaryForMembership({
        covenant_role: { sword_weight: '0.000', shield_weight: '0.000', crown_weight: '0.000' },
        anchor_role: { sword_weight: '0.600', shield_weight: '0.000', crown_weight: '0.400' },
      })
    ).toBe('Sword 60% · Crown 40%');
  });

  it('returns "Unaligned" when the resolved role is all-zero and anchor_role is missing', () => {
    expect(
      blendSummaryForMembership({
        covenant_role: { sword_weight: '0.000', shield_weight: '0.000', crown_weight: '0.000' },
        anchor_role: undefined,
      })
    ).toBe('Unaligned');
  });
});
