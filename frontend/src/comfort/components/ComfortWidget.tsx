/**
 * Personal comfort readout (#1522).
 *
 * The web face of the `comfort` command: a compact glance at how uncomfortable the active
 * character is where they stand, and why. Reads the active character id (passed by the top bar)
 * and queries `/api/locations/comfort/`. Stays silent while the character is comfortable — it
 * only surfaces when something is biting, so the bar isn't cluttered in a cozy room.
 */

import { useCharacterComfort } from '../queries';

/** Tailwind text colors per band index (0 = comfortable … 4 = extreme). PLACEHOLDER palette. */
const BAND_COLORS = [
  'text-muted-foreground',
  'text-amber-500',
  'text-orange-500',
  'text-orange-600',
  'text-red-600',
] as const;

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

interface ComfortWidgetProps {
  characterId: number | null;
}

export function ComfortWidget({ characterId }: ComfortWidgetProps) {
  const { data } = useCharacterComfort(characterId);

  // No data yet, or the character is comfortable → don't clutter the bar.
  if (!data || data.band_index <= 0) return null;

  const color = BAND_COLORS[data.band_index] ?? BAND_COLORS[BAND_COLORS.length - 1];
  const reasons = data.reasons.map(titleCase).join(', ');
  const tooltip = reasons ? `${data.band} — ${reasons}` : data.band;

  return (
    <div
      className={`flex items-center gap-1 text-xs ${color}`}
      title={tooltip}
      aria-label="Personal comfort"
    >
      <span aria-hidden>🌡</span>
      <span>{data.band}</span>
    </div>
  );
}
