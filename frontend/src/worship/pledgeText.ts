/**
 * Pledge text helpers (#4333 slice 2): the earning rate in its parts and the time a pledge
 * has left, shared by the pledge dialog and the pledge card.
 */

import type { ServiceTerms } from './types';

/** "100% + 100% Chosen + 0% favor-earning modifiers". */
export function earningRateParts(terms: ServiceTerms): string {
  const parts = [`${terms.rate.base}%`];
  if (terms.rate.chosen_bonus) parts.push(`${terms.rate.chosen_bonus}% Chosen`);
  parts.push(`${terms.rate.modifiers}% favor-earning modifiers`);
  return parts.join(' + ');
}

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;

/** "4 days left", "5 hours left", or "span ended". */
export function timeLeft(timeLimit: string, now: number = Date.now()): string {
  const remaining = new Date(timeLimit).getTime() - now;
  if (remaining <= 0) return 'span ended';
  const days = Math.floor(remaining / DAY_MS);
  if (days >= 1) return `${days} day${days === 1 ? '' : 's'} left`;
  const hours = Math.max(1, Math.floor(remaining / HOUR_MS));
  return `${hours} hour${hours === 1 ? '' : 's'} left`;
}
