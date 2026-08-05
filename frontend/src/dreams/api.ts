/**
 * Dreams API functions (#3003).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { DreamState } from './types';

const BASE_URL = '/api/dreams';

export async function getDreamState(characterId: number): Promise<DreamState> {
  const res = await apiFetch(`${BASE_URL}/${characterId}/`);
  if (!res.ok) {
    throw new Error('Failed to load dream state');
  }
  return res.json();
}
