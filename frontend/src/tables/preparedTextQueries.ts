/**
 * Prepared per-character Audere text (#4101 Task 4 backend, Task 11
 * frontend) — staff or a character's table GM prepares their next Crossing
 * text (`CharacterCrossingText`, `/api/magic/prepared-crossing-texts/`) and
 * Audere surge line (`CharacterSurgeText`, `/api/magic/prepared-surge-texts/`).
 *
 * Crossing text supports multiple rows per character over time (one per
 * crossing, `crossing` null until used) — `?unused=true` narrows to the one
 * still-pending row, the picker this dialog needs. Surge text is a plain
 * one-per-character `OneToOneField`, so no `unused` filter exists there.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

export type PreparedByRole = 'staff' | 'table_gm';

export interface PreparedCrossingText {
  id: number;
  character_sheet: number;
  character_name: string;
  vision_text: string;
  manifestation_text: string;
  deed_title: string;
  prepared_by_role: PreparedByRole;
  crossing: number | null;
  updated_at: string;
}

export interface PreparedSurgeText {
  id: number;
  character_sheet: number;
  character_name: string;
  surge_text: string;
  prepared_by_role: PreparedByRole;
  updated_at: string;
}

const preparedTextKeys = {
  crossing: (sheetId: number) => ['prepared-crossing-text', sheetId] as const,
  surge: (sheetId: number) => ['prepared-surge-text', sheetId] as const,
};

/** The character's own unused (not-yet-fired) prepared Crossing text, or null. */
export function usePreparedCrossingText(sheetId: number) {
  return useQuery({
    queryKey: preparedTextKeys.crossing(sheetId),
    queryFn: async (): Promise<PreparedCrossingText | null> => {
      const res = await apiFetch(
        `/api/magic/prepared-crossing-texts/?character_sheet=${sheetId}&unused=true`
      );
      if (!res.ok) await throwApiError(res, 'Failed to load prepared crossing text');
      const data = (await res.json()) as { results: PreparedCrossingText[] };
      return data.results[0] ?? null;
    },
  });
}

export interface SaveCrossingTextBody {
  /** The existing row's id -- present PATCHes it; absent creates one. */
  id?: number;
  vision_text: string;
  manifestation_text: string;
  deed_title: string;
}

export function useSavePreparedCrossingText(sheetId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...fields }: SaveCrossingTextBody): Promise<PreparedCrossingText> => {
      const res = await apiFetch(
        id != null
          ? `/api/magic/prepared-crossing-texts/${id}/`
          : '/api/magic/prepared-crossing-texts/',
        {
          method: id != null ? 'PATCH' : 'POST',
          body: JSON.stringify(id != null ? fields : { character_sheet: sheetId, ...fields }),
        }
      );
      if (!res.ok) await throwApiError(res, 'Failed to save prepared crossing text');
      return res.json();
    },
    onSuccess: (row) => queryClient.setQueryData(preparedTextKeys.crossing(sheetId), row),
  });
}

/** The character's own prepared Audere surge line, or null. */
export function usePreparedSurgeText(sheetId: number) {
  return useQuery({
    queryKey: preparedTextKeys.surge(sheetId),
    queryFn: async (): Promise<PreparedSurgeText | null> => {
      const res = await apiFetch(`/api/magic/prepared-surge-texts/?character_sheet=${sheetId}`);
      if (!res.ok) await throwApiError(res, 'Failed to load prepared surge text');
      const data = (await res.json()) as { results: PreparedSurgeText[] };
      return data.results[0] ?? null;
    },
  });
}

export interface SaveSurgeTextBody {
  /** The existing row's id -- present PATCHes it; absent creates one. */
  id?: number;
  surge_text: string;
}

export function useSavePreparedSurgeText(sheetId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...fields }: SaveSurgeTextBody): Promise<PreparedSurgeText> => {
      const res = await apiFetch(
        id != null ? `/api/magic/prepared-surge-texts/${id}/` : '/api/magic/prepared-surge-texts/',
        {
          method: id != null ? 'PATCH' : 'POST',
          body: JSON.stringify(id != null ? fields : { character_sheet: sheetId, ...fields }),
        }
      );
      if (!res.ok) await throwApiError(res, 'Failed to save prepared surge text');
      return res.json();
    },
    onSuccess: (row) => queryClient.setQueryData(preparedTextKeys.surge(sheetId), row),
  });
}
