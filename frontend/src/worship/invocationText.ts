/** Text helpers for the Call on favor picker (#4333). */

import type { InvocationBonusRow } from './types';

/** "Critical Success +15 · Success +10 · Partial Success +5 · Failure and Critical Failure: none" */
export function bonusLine(rows: InvocationBonusRow[]): string {
  const paying = rows
    .filter((row) => row.bonus > 0)
    .map((row) => `${row.outcome_name} +${row.bonus}`);
  const none = rows.filter((row) => row.bonus <= 0).map((row) => row.outcome_name);
  if (none.length === 0) return paying.join(' · ');
  const noneText = `${none.join(' and ')}: none`;
  return [...paying, noneText].join(' · ');
}
