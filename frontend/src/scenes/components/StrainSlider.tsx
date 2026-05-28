import { Slider } from '@/components/ui/slider';
import { computeEffectiveCost } from '../lib/computeEffectiveCost';
import { SoulfrayWarning } from './SoulfrayWarning';

interface StrainSliderProps {
  /** Current strain commitment (extra anima beyond base cost). */
  value: number;
  /** Maximum allowable strain commitment (backend-enforced upper bound). */
  cap: number;
  /** Base anima cost before strain is added. */
  baseEffectiveCost: number;
  /** Caster's current anima pool; if omitted, no over-pool warning is shown. */
  currentAnima?: number;
  /** Called as the player drags the slider. */
  onChange: (value: number) => void;
}

/**
 * Slider for committing extra strain on a cast — Phase 7 of the non-clash
 * casting initiative.
 *
 * - Range is 0…cap (step 1).
 * - Renders a small readout: "Effective cost: N anima" using
 *   {@link computeEffectiveCost}.
 * - When `currentAnima` is supplied and the projected cost would exceed it,
 *   a <SoulfrayWarning> is rendered inline as an over-pool warning.
 */
export function StrainSlider({
  value,
  cap,
  baseEffectiveCost,
  currentAnima,
  onChange,
}: StrainSliderProps) {
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
        <SoulfrayWarning
          warning={{
            stage_name: 'Insufficient anima',
            stage_description: `Projected cost (${projectedCost}) exceeds your current pool (${currentAnima ?? 0}).`,
            has_death_risk: false,
          }}
          techniqueName="this cast"
          animaCost={projectedCost}
          onConfirm={() => {
            /* purely informational at the slider level — confirm/cancel happen
             * at the surrounding ActionPanel */
          }}
          onCancel={() => {
            /* see above */
          }}
        />
      )}
    </div>
  );
}
