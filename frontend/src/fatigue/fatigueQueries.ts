import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';

export type FatigueZone = 'fresh' | 'strained' | 'tired' | 'overexerted' | 'exhausted';

export interface FatiguePoolStatus {
  current: number;
  capacity: number;
  percentage: number;
  zone: FatigueZone;
}

export interface FatigueStatus {
  physical: FatiguePoolStatus;
  social: FatiguePoolStatus;
  mental: FatiguePoolStatus;
  well_rested: boolean;
  rested_today: boolean;
}

export async function fetchFatigueStatus(): Promise<FatigueStatus> {
  const res = await apiFetch('/api/fatigue/status/');
  if (!res.ok) throw new Error('Failed to load fatigue status');
  return res.json();
}

export async function restCommand(): Promise<{ detail: string }> {
  const res = await apiFetch('/api/fatigue/rest/', { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to rest');
  }
  return res.json();
}

export function useFatigueStatusQuery() {
  return useQuery<FatigueStatus>({
    queryKey: ['fatigue-status'],
    queryFn: fetchFatigueStatus,
    throwOnError: true,
  });
}

export function useRestMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: restCommand,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fatigue-status'] });
    },
  });
}
