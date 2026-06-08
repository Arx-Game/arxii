/**
 * React Query hooks for the Spread a Tale flow (#745).
 *
 * - useSpreadableDeedsQuery: deeds the persona may spread (societies it knows).
 * - useSpreadMutation: dispatch a telling in the current scene.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';

export interface SpreadableDeed {
  id: number;
  title: string;
  base_value: number;
  created_at: string;
}

export interface SpreadResult {
  resolved: boolean;
  outcome: string;
  band: string;
}

export interface SpreadForm {
  id: number;
  name: string;
  description: string;
}

export interface SpreadInput {
  scene: number;
  deed: number;
  pose_text: string;
  effort_level: string;
  specialization?: number | null;
}

export interface DeedStory {
  id: number;
  author_name: string;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface SaveDeedStoryInput {
  deed: number;
  text: string;
}

async function fetchSpreadSpecializations(): Promise<SpreadForm[]> {
  const res = await apiFetch('/api/personas/spread-specializations/');
  if (!res.ok) {
    throw new Error('Failed to load telling forms.');
  }
  return res.json() as Promise<SpreadForm[]>;
}

export function useSpreadSpecializationsQuery(enabled = true) {
  return useQuery({
    queryKey: ['spread-specializations'],
    queryFn: fetchSpreadSpecializations,
    enabled,
  });
}

export interface SceneActivity {
  band: string;
}

async function fetchSceneActivity(sceneId: number): Promise<SceneActivity> {
  const res = await apiFetch(`/api/scenes/${sceneId}/activity/`);
  if (!res.ok) {
    throw new Error('Failed to read the room.');
  }
  return res.json() as Promise<SceneActivity>;
}

export function useSceneActivityQuery(sceneId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['scene-activity', sceneId],
    queryFn: () => fetchSceneActivity(sceneId as number),
    enabled: sceneId !== null && enabled,
  });
}

async function fetchSpreadableDeeds(personaId: number): Promise<SpreadableDeed[]> {
  const res = await apiFetch(`/api/personas/${personaId}/spreadable-deeds/`);
  if (!res.ok) {
    throw new Error('Failed to load deeds you can spread.');
  }
  return res.json() as Promise<SpreadableDeed[]>;
}

export function useSpreadableDeedsQuery(personaId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['spreadable-deeds', personaId],
    queryFn: () => fetchSpreadableDeeds(personaId as number),
    enabled: personaId !== null && enabled,
  });
}

export function useSpreadMutation(personaId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: SpreadInput): Promise<SpreadResult> => {
      const res = await apiFetch(`/api/personas/${personaId}/spread/`, {
        method: 'POST',
        body: JSON.stringify(input),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? 'The tale could not be spread.');
      }
      return res.json() as Promise<SpreadResult>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spreadable-deeds', personaId] });
      queryClient.invalidateQueries({ queryKey: ['renown', personaId] });
    },
    onError: () => {
      // A deed may have been deactivated mid-flight — refresh the picker so a
      // stale tale drops out rather than re-failing on retry.
      queryClient.invalidateQueries({ queryKey: ['spreadable-deeds', personaId] });
    },
  });
}

async function fetchDeedStories(personaId: number, deedId: number): Promise<DeedStory[]> {
  const res = await apiFetch(`/api/personas/${personaId}/deed-stories/?deed=${deedId}`);
  if (!res.ok) {
    throw new Error('Failed to load accounts of this deed.');
  }
  const body = (await res.json()) as { results: DeedStory[] };
  return body.results;
}

export function useDeedStoriesQuery(
  personaId: number | null,
  deedId: number | null,
  enabled = true
) {
  return useQuery({
    queryKey: ['deed-stories', personaId, deedId],
    queryFn: () => fetchDeedStories(personaId as number, deedId as number),
    enabled: personaId !== null && deedId !== null && enabled,
  });
}

export function useSaveDeedStoryMutation(personaId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: SaveDeedStoryInput): Promise<DeedStory> => {
      const res = await apiFetch(`/api/personas/${personaId}/deed-story/`, {
        method: 'POST',
        body: JSON.stringify(input),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? 'Your account could not be saved.');
      }
      return res.json() as Promise<DeedStory>;
    },
    onSuccess: (_data, input) => {
      queryClient.invalidateQueries({ queryKey: ['deed-stories', personaId, input.deed] });
    },
  });
}
