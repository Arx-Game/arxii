/**
 * The one GM prompt queue (#4101; was the #2183 dramatic-moment suggestion
 * inbox). Backs `GMPromptQueue`/`GMPromptRow`/`NarrationComposer` against
 * `GMPromptViewSet` (`world/gm/views.py`). `scene` is a required query param
 * server-side (400 without it) — every hook here is scoped to one scene.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import type { GMPrompt } from './types';

export const gmPromptKeys = {
  all: ['gm-prompts'] as const,
  scene: (sceneId: string) => ['gm-prompts', sceneId] as const,
};

/** Lists PENDING and NARRATED prompts for `sceneId` (controller amendment R6-2 —
 * a NARRATED prompt stays in the queue until dismissed). */
export function useGMPrompts(sceneId: string) {
  return useQuery({
    queryKey: gmPromptKeys.scene(sceneId),
    queryFn: async (): Promise<GMPrompt[]> => {
      const res = await apiFetch(`/api/gm/prompts/?scene=${sceneId}`);
      if (!res.ok) await throwApiError(res, 'Failed to load GM prompts');
      const data = (await res.json()) as { results: GMPrompt[] };
      return data.results;
    },
  });
}

function usePromptPost(sceneId: string, verb: 'confirm' | 'dismiss') {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (promptId: number): Promise<GMPrompt> => {
      const res = await apiFetch(`/api/gm/prompts/${promptId}/${verb}/`, { method: 'POST' });
      if (!res.ok) await throwApiError(res, `Failed to ${verb} prompt`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gmPromptKeys.scene(sceneId) });
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
    },
  });
}

/** Mints the tag for a `dramatic_moment` prompt (the one kind `confirm` resolves). */
export const useConfirmGMPrompt = (sceneId: string) => usePromptPost(sceneId, 'confirm');
/** Closes a prompt — PENDING (never narrated) or NARRATED (the GM is done sending lines). */
export const useDismissGMPrompt = (sceneId: string) => usePromptPost(sceneId, 'dismiss');

export interface NarrateBody {
  promptId: number;
  text: string;
  audience: 'room' | 'chosen';
  /** Required (and must be present in the room) when `audience` is `'chosen'`. */
  receiver_persona_ids?: number[];
}

/**
 * A successful narrate's response: the refreshed prompt row, plus `message`
 * when the dispatched action has one to report — e.g. the prompt closed (a
 * sibling dismiss, scene-end expiry) between resolve and link, so the line
 * went out in full but as plain, unlinked narration (#4101 Task 10).
 */
export interface NarrateResult extends GMPrompt {
  message?: string;
}

export function useNarrateGMPrompt(sceneId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ promptId, ...body }: NarrateBody): Promise<NarrateResult> => {
      const res = await apiFetch(`/api/gm/prompts/${promptId}/narrate/`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (!res.ok) await throwApiError(res, 'Failed to send narration');
      return res.json();
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: gmPromptKeys.scene(sceneId) }),
  });
}
