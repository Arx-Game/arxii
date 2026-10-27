/**
 * PullBurnInput - the resonance burn on a thread pull, shown in the Strain area (#4736).
 *
 * Shown once a pull is chosen and the preview has answered with burn numbers. The
 * ceiling comes from the server (already capped by the balance left after the pull);
 * the input is clamped to it, and the server checks again. One burn per pull: a pull
 * draws on one resonance, so the row is labelled with that resonance.
 */

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { BurnPreview } from '../../types';
import { effectiveBurn, type StrainBurn } from '../../burn';

export interface PullBurnInputProps extends StrainBurn {
  /** Power from the strain curve with this burn fully reached, or null to hide it. */
  powerBonus?: number | null;
  disabled?: boolean;
}

function clampBurn(raw: string, ceiling: number): number {
  const parsed = Math.floor(Number(raw));
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.min(parsed, ceiling);
}

function ceilingLabel(preview: BurnPreview, tier: number | undefined): string {
  if (preview.ceiling_tier_name) return `Burn ceiling at ${preview.ceiling_tier_name}`;
  if (tier !== undefined) return `Burn ceiling at Tier ${tier}`;
  return 'Burn ceiling';
}

export function PullBurnInput({
  preview,
  value,
  onChange,
  tier,
  powerBonus,
  disabled,
}: PullBurnInputProps) {
  if (!preview || !preview.available) return null;
  const burning = effectiveBurn(preview, value);
  const corruption = preview.corruption_affinity_name;
  return (
    <div className="space-y-1" data-testid="pull-burn">
      <div className="flex items-center gap-2">
        <Label htmlFor="pull-burn-input" className="text-xs" data-testid="pull-burn-label">
          {preview.resonance_name}{' '}
          <span className="text-muted-foreground">
            {preview.off_affinity ? '(off-affinity)' : '(yours)'}
          </span>
        </Label>
        <Input
          id="pull-burn-input"
          type="number"
          inputMode="numeric"
          min={0}
          max={preview.ceiling}
          step={1}
          value={burning}
          disabled={disabled || preview.ceiling === 0}
          onChange={(e) => onChange(clampBurn(e.target.value, preview.ceiling))}
          data-testid="pull-burn-input"
          className="h-7 w-20"
        />
        {burning > 0 && powerBonus != null && (
          <span className="font-mono text-xs text-foreground" data-testid="pull-burn-power">
            up to +{powerBonus} power
          </span>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground" data-testid="pull-burn-ceiling">
        {ceilingLabel(preview, tier)}: {preview.ceiling} resonance
      </p>
      {burning > 0 && (
        <p className="text-[10px] text-muted-foreground" data-testid="pull-burn-check">
          Strain check on submit. Degrees decide how much of the {burning} you reach.
        </p>
      )}
      {burning > 0 && preview.hasty_fall && corruption && (
        <p className="text-xs text-amber-500" role="alert" data-testid="pull-burn-hasty">
          <b>Hasty fall.</b> No rite, so it leaves extra {corruption} corruption.
        </p>
      )}
      {burning > 0 && !preview.hasty_fall && preview.off_affinity && corruption && (
        <p className="text-xs text-amber-500" role="alert" data-testid="pull-burn-off-affinity">
          <b>Burning {preview.resonance_name} raw.</b> It leaves {corruption} corruption you will
          need cleansed.
        </p>
      )}
    </div>
  );
}
