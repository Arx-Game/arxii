/**
 * LevelBar (#3983 Task 8, plate I `.lvl`) — the realm ladder's tier picker: a
 * `role="group"` of `aria-pressed` buttons, each carrying its tier's
 * unclaimed count via the folio `CountChip` (renders nothing at `count <=
 * 0` — the same rule the plate uses to show the realm's own crown tier with
 * no digit while a genuinely unclaimed tier gets one). The tier set is
 * `levelBarTiers(rows)` (`./tree.ts`, review fix round 1): the distinct
 * tiers actually present among the rows, with march folded into county — a
 * realm with no march titles never shows a phantom March button, and one
 * with march titles doesn't grow a second bucket next to County. The
 * County button's count is therefore `unclaimed_by_tier.county +
 * unclaimed_by_tier.march` combined, matching `displayTier`'s fold in
 * `./tree.ts`.
 */
import { CountChip } from '@/components/folio';

import type { LadderRow } from '../types';
import { levelBarTiers, TIER_LABELS, tierNoun } from './tree';

export interface LevelBarProps {
  rows: LadderRow[];
  unclaimedByTier: Record<string, number>;
  pressedTier: string | null;
  onPressTier: (tier: string) => void;
}

function tierCount(unclaimedByTier: Record<string, number>, tier: string): number {
  const base = unclaimedByTier[tier] ?? 0;
  return tier === 'county' ? base + (unclaimedByTier.march ?? 0) : base;
}

export function LevelBar({ rows, unclaimedByTier, pressedTier, onPressTier }: LevelBarProps) {
  const tiers = levelBarTiers(rows);
  if (tiers.length === 0) return null;

  return (
    <div className="lvl" role="group" aria-label="Level">
      {tiers.map((tier) => {
        const count = tierCount(unclaimedByTier, tier);
        return (
          <button
            key={tier}
            type="button"
            aria-pressed={tier === pressedTier}
            onClick={() => onPressTier(tier)}
          >
            {TIER_LABELS[tier] ?? tier}
            <CountChip count={count} label={`unclaimed ${tierNoun(tier, count)}`} />
          </button>
        );
      })}
    </div>
  );
}
