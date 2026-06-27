/**
 * SoulfrayAcceptGate — inline accept gate for a combat cast that carries a
 * Soulfray warning (#1543). Renders the warning prose (reusing the same
 * SoulfrayWarningData shape + danger styling as <SoulfrayWarning>) plus an
 * "Accept the risk" toggle whose state lives in YourTurn until submit.
 *
 * Distinct from scenes' <SoulfrayWarning>, which is a momentary
 * Cancel/Proceed block; combat needs a persistent accept that holds with the
 * rest of the declaration state.
 */
import type { SoulfrayWarningData } from '@/scenes/actionTypes';
import { cn } from '@/lib/utils';

interface SoulfrayAcceptGateProps {
  warning: SoulfrayWarningData;
  techniqueName: string;
  animaCost: number;
  accepted: boolean;
  onAcceptChange: (v: boolean) => void;
  disabled?: boolean;
}

export function SoulfrayAcceptGate({
  warning,
  techniqueName,
  animaCost,
  accepted,
  onAcceptChange,
  disabled = false,
}: SoulfrayAcceptGateProps) {
  const isDangerous = warning.has_death_risk;

  return (
    <div
      data-testid="soulfray-accept-gate"
      className={cn(
        'rounded-lg border p-3',
        isDangerous ? 'border-red-500 bg-red-950/50' : 'border-amber-500 bg-amber-950/50'
      )}
    >
      <h3 className={cn('mb-1 text-sm font-bold', isDangerous ? 'text-red-400' : 'text-amber-400')}>
        {isDangerous ? 'DANGER: ' : ''}Soulfray Warning — {warning.stage_name}
      </h3>
      <p className="mb-1 text-xs text-gray-300">{warning.stage_description}</p>
      <p className="mb-2 text-xs text-gray-400">
        Casting <strong>{techniqueName}</strong> will cost <strong>{animaCost} anima</strong> and
        may worsen your condition.
      </p>
      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          role="checkbox"
          aria-label="Accept the risk"
          checked={accepted}
          disabled={disabled}
          onChange={(e) => onAcceptChange(e.target.checked)}
          data-testid="soulfray-accept-checkbox"
          className="accent-amber-500"
        />
        Accept the risk
      </label>
    </div>
  );
}
