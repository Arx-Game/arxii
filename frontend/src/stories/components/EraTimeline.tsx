/**
 * EraTimeline — horizontal timeline visualization of all eras.
 *
 * Eras are sorted by season_number ascending and displayed as connected
 * nodes. The ACTIVE era is highlighted prominently. Clicking a node
 * fires onSelectEra with the era id, which the parent can use to scroll
 * to the detail row.
 *
 * Color coding:
 *   CONCLUDED → gray
 *   ACTIVE    → green (ring + larger dot)
 *   UPCOMING  → amber
 */

import type { Era } from '../types';

interface EraTimelineProps {
  eras: Era[];
  selectedId?: number | null;
  onSelectEra?: (id: number) => void;
}

const STATUS_DOT: Record<string, string> = {
  concluded: 'bg-gray-400 border-gray-500',
  active: 'bg-green-500 border-green-700 ring-4 ring-green-200',
  upcoming: 'bg-amber-400 border-amber-600',
};

const STATUS_LABEL: Record<string, string> = {
  concluded: 'text-gray-500',
  active: 'text-green-700 font-semibold',
  upcoming: 'text-amber-700',
};

export function EraTimeline({ eras, selectedId, onSelectEra }: EraTimelineProps) {
  const sorted = [...eras].sort((a, b) => a.season_number - b.season_number);

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        No eras defined yet.
      </div>
    );
  }

  return (
    <div
      className="relative flex items-center gap-0 overflow-x-auto pb-4"
      data-testid="era-timeline"
    >
      {sorted.map((era, idx) => {
        const isSelected = era.id === selectedId;
        const dotClass = STATUS_DOT[era.status] ?? STATUS_DOT.upcoming;
        const labelClass = STATUS_LABEL[era.status] ?? STATUS_LABEL.upcoming;
        const isLast = idx === sorted.length - 1;

        return (
          <div key={era.id} className="flex items-center">
            {/* Node */}
            <button
              type="button"
              className={`group relative flex flex-col items-center focus:outline-none`}
              onClick={() => onSelectEra?.(era.id)}
              aria-label={`Era: ${era.display_name}`}
              data-testid={`era-node-${era.id}`}
            >
              {/* Dot */}
              <div
                className={`h-4 w-4 shrink-0 cursor-pointer rounded-full border-2 transition-transform group-hover:scale-125 ${dotClass} ${
                  isSelected ? 'scale-125' : ''
                } ${era.status === 'active' ? 'h-5 w-5' : ''}`}
              />
              {/* Label */}
              <div className="mt-2 max-w-24 text-center">
                <div className={`text-xs ${labelClass}`}>S{era.season_number}</div>
                <div
                  className={`line-clamp-2 text-[10px] leading-tight text-muted-foreground ${isSelected ? 'underline' : ''}`}
                >
                  {era.display_name}
                </div>
              </div>
            </button>

            {/* Connector line between nodes */}
            {!isLast && <div className="mx-1 h-0.5 w-12 shrink-0 bg-border" aria-hidden="true" />}
          </div>
        );
      })}
    </div>
  );
}
