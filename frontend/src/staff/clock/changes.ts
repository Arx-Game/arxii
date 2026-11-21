import { formatRatio } from './clockDate';
import type { ClockHistoryRow } from './types';

/** One change in a sentence: what was done and where it left the date. */
export function describeChange(row: ClockHistoryRow): string {
  const date = row.new_date_display;
  switch (row.change) {
    case 'paused':
      return `Paused at ${date}`;
    case 'resumed':
      return `Resumed at ${date}`;
    case 'speed':
      return `Speed changed from ${formatRatio(row.old_time_ratio)} to ${formatRatio(row.new_time_ratio)} game days per real day`;
    case 'date_aged':
      return `Date set to ${date}. Characters aged.`;
    case 'date_kept': {
      const shift = row.birth_year_shift;
      const kept = `Date set to ${date}. Characters kept their ages.`;
      if (shift === 0) return kept;
      return `${kept} Birth years moved by ${shift > 0 ? '+' : ''}${shift}.`;
    }
    default:
      return `Clock changed to ${date}`;
  }
}
