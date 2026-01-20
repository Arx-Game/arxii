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
