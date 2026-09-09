/**
 * Nominations for good RP (#3738): the nominator's own side of the API.
 *
 * A nomination is an OOC act by the account, invisible to the nominee until
 * the week settles. The only read is your own list for the week, so you know
 * whom you have already nominated; there is no budget, no count received and
 * no received view anywhere in the client.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';

// --- Types ---

export type NominationTargetType = 'interaction' | 'journal';

export interface Nomination {
  id: number;
  target_type: NominationTargetType;
  target_id: number;
  nominee_name: string;
  target_name: string;
  created_at: string;
}

// --- API functions ---

export async function fetchMyNominations(): Promise<Nomination[]> {
  const res = await apiFetch('/api/progression/nominations/');
  if (!res.ok) throw new Error('Failed to load your nominations');
  return res.json();
}

export async function nominate(
  targetType: NominationTargetType,
  targetId: number
): Promise<Nomination> {
  const res = await apiFetch('/api/progression/nominations/', {
    method: 'POST',
    body: JSON.stringify({ target_type: targetType, target_id: targetId }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to nominate');
  }
  return res.json();
}

export async function withdrawNomination(nominationId: number): Promise<void> {
  const res = await apiFetch(`/api/progression/nominations/${nominationId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to withdraw the nomination');
}

// --- Query keys ---

export const nominationKeys = {
  mine: ['my-nominations'] as const,
};

// --- Hooks ---

export function useMyNominationsQuery() {
  return useQuery({
    queryKey: nominationKeys.mine,
    queryFn: fetchMyNominations,
  });
}

export function useNominateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      targetType,
      targetId,
    }: {
      targetType: NominationTargetType;
      targetId: number;
    }) => nominate(targetType, targetId),
    onSuccess: (row) => {
      queryClient.setQueryData<Nomination[]>(nominationKeys.mine, (old) =>
        old ? [...old, row] : [row]
      );
    },
  });
}

export function useWithdrawNominationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (nominationId: number) => withdrawNomination(nominationId),
    onSuccess: (_, nominationId) => {
      queryClient.setQueryData<Nomination[]>(nominationKeys.mine, (old) =>
        old ? old.filter((row) => row.id !== nominationId) : []
      );
    },
  });
}
