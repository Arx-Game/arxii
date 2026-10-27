/**
 * PullBurnInput - the resonance burn number on a thread pull (#4736).
 *
 * Shown under a chosen pull once the preview has answered with burn numbers.
 * The ceiling comes from the server (already capped by the balance left after
 * the pull); the input is clamped to it, and the server checks again.
 */

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { BurnPreview } from '../../types';

export interface PullBurnInputProps {
  /** Burn numbers from the pull preview; null/undefined hides the input. */
  burn: BurnPreview | null | undefined;
  value: number;
  onChange: (next: number) => void;
  /** Tier of the pull, for the ceiling line. */
  tier: number;
  disabled?: boolean;
}

function clampBurn(raw: string, ceiling: number): number {
  const parsed = Math.floor(Number(raw));
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.min(parsed, ceiling);
}

export function PullBurnInput({ burn, value, onChange, tier, disabled }: PullBurnInputProps) {
  if (!burn || !burn.available) return null;
  return (
    <div className="space-y-1" data-testid="pull-burn">
      <Label htmlFor="pull-burn-input" className="text-xs">
        Burn resonance
      </Label>
      <Input
        id="pull-burn-input"
        type="number"
        inputMode="numeric"
        min={0}
        max={burn.ceiling}
        step={1}
        value={value}
        disabled={disabled || burn.ceiling === 0}
        onChange={(e) => onChange(clampBurn(e.target.value, burn.ceiling))}
        data-testid="pull-burn-input"
        className="h-8 w-24"
      />
      <p className="text-xs text-muted-foreground" data-testid="pull-burn-ceiling">
        Burn ceiling at Tier {tier}: {burn.ceiling} resonance
      </p>
      {burn.hasty_fall && (
        <p className="text-xs text-amber-500" data-testid="pull-burn-hasty">
          Falls at the pair rate and leaves extra corruption.
        </p>
      )}
    </div>
  );
}
