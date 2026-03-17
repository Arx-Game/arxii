/**
 * API functions for progression data.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { AccountProgressionData } from './types';

export async function fetchAccountProgression(): Promise<AccountProgressionData> {
  const res = await apiFetch('/api/progression/account/');
  if (!res.ok) {
    throw new Error('Failed to load progression data');
  }
  return res.json();
}

export async function claimKudosForXP(
  claimCategoryId: number,
  amount: number
): Promise<AccountProgressionData> {
  const res = await apiFetch('/api/progression/claim-kudos/', {
    method: 'POST',
    body: JSON.stringify({ claim_category_id: claimCategoryId, amount }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to claim kudos');
  }
  return res.json();
}
