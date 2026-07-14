import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type Will = components['schemas']['Will'];
export type Bequest = components['schemas']['Bequest'];
export type WillExecutor = components['schemas']['WillExecutor'];
export type EstateSettlement = components['schemas']['EstateSettlement'];
export type EstateClaim = components['schemas']['EstateClaim'];

interface Paginated<T> {
  count: number;
  results: T[];
}

/** The viewer's will for one of their own characters (sheet pk); null when unwritten. */
export async function fetchWill(characterSheetId: number): Promise<Will | null> {
  const res = await apiFetch(`/api/estates/wills/?character_sheet=${characterSheetId}`);
  if (!res.ok) throw new Error('Failed to load will');
  const data: Paginated<Will> = await res.json();
  return data.results[0] ?? null;
}

export function useWillQuery(characterSheetId: number) {
  return useQuery<Will | null>({
    queryKey: ['estates-will', characterSheetId],
    queryFn: () => fetchWill(characterSheetId),
    enabled: characterSheetId > 0,
  });
}

async function jsonOrThrow(res: Response) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(JSON.stringify(body));
  }
  return res.status === 204 ? null : res.json();
}

export function useWillMutations(characterSheetId: number) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['estates-will', characterSheetId] });

  const createWill = useMutation({
    mutationFn: (testamentText: string) =>
      apiFetch('/api/estates/wills/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_sheet: characterSheetId,
          testament_text: testamentText,
        }),
      }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  const updateTestament = useMutation({
    mutationFn: ({ willId, testamentText }: { willId: number; testamentText: string }) =>
      apiFetch(`/api/estates/wills/${willId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ testament_text: testamentText }),
      }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  const addBequest = useMutation({
    mutationFn: (bequest: Partial<Bequest> & { will: number; kind: string }) =>
      apiFetch('/api/estates/bequests/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bequest),
      }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  const removeBequest = useMutation({
    mutationFn: (bequestId: number) =>
      apiFetch(`/api/estates/bequests/${bequestId}/`, { method: 'DELETE' }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  const addExecutor = useMutation({
    mutationFn: ({ willId, personaId }: { willId: number; personaId: number }) =>
      apiFetch('/api/estates/executors/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ will: willId, persona: personaId }),
      }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  const removeExecutor = useMutation({
    mutationFn: (executorId: number) =>
      apiFetch(`/api/estates/executors/${executorId}/`, { method: 'DELETE' }).then(jsonOrThrow),
    onSuccess: invalidate,
  });

  return { createWill, updateTestament, addBequest, removeBequest, addExecutor, removeExecutor };
}

/** Settlements the viewer may see (executor of the will, or staff). */
export function useSettlementsQuery() {
  return useQuery<EstateSettlement[]>({
    queryKey: ['estates-settlements'],
    queryFn: async () => {
      const res = await apiFetch('/api/estates/settlements/?status=pending');
      if (!res.ok) throw new Error('Failed to load settlements');
      const data: Paginated<EstateSettlement> = await res.json();
      return data.results;
    },
  });
}

/** Claims the viewer's characters inherited (the grievance ledger). */
export function useClaimsQuery() {
  return useQuery<EstateClaim[]>({
    queryKey: ['estates-claims'],
    queryFn: async () => {
      const res = await apiFetch('/api/estates/claims/');
      if (!res.ok) throw new Error('Failed to load claims');
      const data: Paginated<EstateClaim> = await res.json();
      return data.results;
    },
  });
}
