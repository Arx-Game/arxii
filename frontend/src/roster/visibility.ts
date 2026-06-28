/**
 * Visibility settings (#1484) — the web control for quiet/hidden mode (`appear_offline`).
 *
 * Scoped to the player's active character; reads/writes `/api/roster/visibility-settings/` (the
 * web equivalent of the telnet `hide`/`unhide` commands). React Query hooks + plain fetchers.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

export type VisibilitySettings = components['schemas']['VisibilitySettings'];

const URL = '/api/roster/visibility-settings/';

export async function fetchVisibilitySettings(): Promise<VisibilitySettings> {
  const res = await apiFetch(URL);
  if (!res.ok) throw new Error('Failed to load visibility settings');
  return res.json() as Promise<VisibilitySettings>;
}

export async function setAppearOffline(appearOffline: boolean): Promise<VisibilitySettings> {
  const res = await apiFetch(URL, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ appear_offline: appearOffline }),
  });
  if (!res.ok) throw new Error('Failed to update visibility settings');
  return res.json() as Promise<VisibilitySettings>;
}

const visibilityKey = ['roster', 'visibility-settings'] as const;

/** The active character's visibility prefs. Quiet (404/no-character) is surfaced as an error. */
export function useVisibilitySettings() {
  return useQuery({ queryKey: visibilityKey, queryFn: fetchVisibilitySettings });
}

export function useSetAppearOffline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appearOffline: boolean) => setAppearOffline(appearOffline),
    onSuccess: (data) => {
      queryClient.setQueryData(visibilityKey, data);
    },
  });
}
