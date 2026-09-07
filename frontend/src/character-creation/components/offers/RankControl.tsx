/**
 * RankControl (#3675), the +/- rank stepper on a ranked offer's `.stance`
 * row. A small sibling of `StatRow`'s own step buttons (`folio/InstrumentFrame.tsx`),
 * not that component itself: `StatRow` is its own `.stat-row` grid (name,
 * pips, value, step buttons) and does not compose inside a `.stance` row's
 * grid, so this copies its button pattern rather than mounting it whole.
 */

interface RankControlProps {
  name: string;
  rank: number;
  max: number;
  disabled?: boolean;
  onChange: (rank: number) => void;
}

export function RankControl({ name, rank, max, disabled, onChange }: RankControlProps) {
  return (
    <span className="rank" aria-label={`rank ${rank} of ${max}`}>
      <button
        type="button"
        disabled={disabled || rank <= 0}
        aria-label={`Lower ${name}`}
        onClick={(e) => {
          e.stopPropagation();
          onChange(rank - 1);
        }}
      >
        −
      </button>
      <button
        type="button"
        disabled={disabled || rank >= max}
        aria-label={`Raise ${name}`}
        onClick={(e) => {
          e.stopPropagation();
          onChange(rank + 1);
        }}
      >
        +
      </button>
    </span>
  );
}
