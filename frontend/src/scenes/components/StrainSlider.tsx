import { Slider } from '@/components/ui/slider';
import { computeEffectiveCost } from '../lib/computeEffectiveCost';

interface StrainSliderProps {
  /** Current strain commitment (extra anima beyond base cost). */
  value: number;
  /** Maximum allowable strain commitment (backend-enforced upper bound). */
  cap: number;
  /** Base anima cost before strain is added. */
  baseEffectiveCost: number;
  /** Caster's current anima pool; if omitted, no over-pool indicator is shown. */
  currentAnima?: number;
  /** Called as the player drags the slider. */
  onChange: (value: number) => void;
}

/**
 * Slider for committing extra strain on a cast — Phase 7 of the non-clash
 * casting initiative.
 *
 * Renders an inline indicator (not a full confirm/cancel dialog) when the
 * projected cost would exceed the pool — the real Soulfray confirm step lives
 * at the ActionPanel dispatch boundary, not on the adjustment control.
 */
export function StrainSlider({
  value,
  cap,
  baseEffectiveCost,
  currentAnima,
  onChange,
}: Readonly<StrainSliderProps>) {
  const projectedCost = computeEffectiveCost(baseEffectiveCost, value);
  const overPool = currentAnima !== undefined && projectedCost > currentAnima;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">Strain</span>
        <span className="text-muted-foreground">
          {value} / {cap}
        </span>
      </div>
      <Slider
        value={[value]}
        min={0}
        max={cap}
        step={1}
        onValueChange={(values) => onChange(values[0] ?? 0)}
        aria-label="Strain commitment"
      />
      <p className="text-xs text-muted-foreground">Effective cost: {projectedCost} anima</p>
      {overPool && (
        <p
          role="status"
          className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-xs text-amber-200"
        >
          <span className="font-semibold">Insufficient anima</span>
          {' — projected '}
          {projectedCost}
          {' exceeds pool '}
          {currentAnima ?? 0}
        </p>
      )}
    </div>
  );
}
