import { apiFetch } from '@/evennia_replacements/api';

import type { MagicProgressionResponse } from './magicProgressionTypes';

const MAGIC_PROGRESSION_URL = '/api/magic/progression/';

export async function getMagicProgression(
  characterSheetId?: number
): Promise<MagicProgressionResponse> {
  const url = characterSheetId != null
    ? `${MAGIC_PROGRESSION_URL}?character_sheet_id=${characterSheetId}`
    : MAGIC_PROGRESSION_URL;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error('Failed to load magic progression');
  return res.json() as Promise<MagicProgressionResponse>;
}
