import { useMutation, useQueryClient } from '@tanstack/react-query';
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

export async function restCommand(): Promise<{ detail: string }> {
  const res = await apiFetch('/api/fatigue/rest/', { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to rest');
  }
  return res.json();
}

export function useRestMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: restCommand,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character-vitals'] }).catch(() => {});
    },
  });
}
