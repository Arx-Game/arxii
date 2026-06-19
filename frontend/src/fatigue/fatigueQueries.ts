import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

// Sourced from the generated OpenAPI schema. `zone` is a ChoiceField on the wire
// (FatiguePoolStatusSerializer), so the union is generated, not hand-written.
export type FatigueZone = components['schemas']['ZoneEnum'];
export type FatiguePoolStatus = components['schemas']['FatiguePoolStatus'];
export type FatigueStatus = components['schemas']['VitalsFatigue'];

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
