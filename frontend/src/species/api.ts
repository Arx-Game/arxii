/**
 * Species API functions (#2993).
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { MyLanguage } from './types';

const BASE_URL = '/api/species';

/** The viewer's own active character's known languages (fluency/band/is_current). */
export async function fetchMyLanguages(): Promise<MyLanguage[]> {
  const res = await apiFetch(`${BASE_URL}/my-languages/`);
  if (!res.ok) {
    throw new Error('Failed to load languages');
  }
  return res.json();
}
