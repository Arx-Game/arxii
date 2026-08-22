/**
 * Landing page (Gatefold) React Query hooks — public shop-window reads (#3305).
 *
 * None of these set `throwOnError`: the landing page must degrade quietly for
 * anonymous visitors rather than trip an error boundary. Every hook is meant
 * to be rendered against a possibly-`undefined`/`null` `data` — the caller
 * hides its section rather than surfacing an error state.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCompletedSceneCount,
  getPublicBeginnings,
  getPublicStartingAreas,
  getSceneInteractions,
  getScenesSpotlight,
} from './api';
import type { Beginnings, StartingArea } from '@/character-creation/types';
import type { Interaction, SceneListItem } from '@/scenes/types';

const FIVE_MINUTES = 5 * 60 * 1000;

/** How many spotlight `recent` scenes `useSceneExcerpt` will try before giving up (bounds requests). */
const SCENE_EXCERPT_CANDIDATE_CAP = 3;
/** Poses shown per excerpted scene. */
const SCENE_EXCERPT_POSE_CAP = 2;

export const homeKeys = {
  all: ['home'] as const,
  startingAreas: () => [...homeKeys.all, 'starting-areas'] as const,
  beginnings: (startingAreaId?: number) =>
    [...homeKeys.all, 'beginnings', startingAreaId ?? null] as const,
  sceneExcerpt: () => [...homeKeys.all, 'scene-excerpt'] as const,
  monthlySceneCount: (finishedAfter: string) =>
    [...homeKeys.all, 'monthly-scene-count', finishedAfter] as const,
};

export function usePublicStartingAreas() {
  return useQuery<StartingArea[]>({
    queryKey: homeKeys.startingAreas(),
    queryFn: getPublicStartingAreas,
    staleTime: FIVE_MINUTES,
  });
}

export function usePublicBeginnings(startingAreaId: number | undefined) {
  return useQuery<Beginnings[]>({
    queryKey: homeKeys.beginnings(startingAreaId),
    queryFn: () => getPublicBeginnings(startingAreaId as number),
    enabled: startingAreaId !== undefined,
    staleTime: FIVE_MINUTES,
  });
}

export interface SceneExcerpt {
  scene: SceneListItem;
  poses: Interaction[];
}

/**
 * Walks the spotlight `recent` list in order, trying at most the first
 * `SCENE_EXCERPT_CANDIDATE_CAP` candidates, and resolves the first scene that
 * has at least one visible interaction. A candidate whose interactions fetch
 * itself fails (network hiccup, transient 5xx) is treated the same as an
 * empty scene — skipped rather than aborting the whole walk.
 */
async function fetchSceneExcerpt(): Promise<SceneExcerpt | null> {
  const { recent } = await getScenesSpotlight();
  const candidates = recent.slice(0, SCENE_EXCERPT_CANDIDATE_CAP);
  for (const scene of candidates) {
    let poses: Interaction[] = [];
    try {
      poses = await getSceneInteractions(scene.id);
    } catch {
      continue;
    }
    if (poses.length > 0) {
      return { scene, poses: poses.slice(0, SCENE_EXCERPT_POSE_CAP) };
    }
  }
  return null;
}

export function useSceneExcerpt() {
  return useQuery<SceneExcerpt | null>({
    queryKey: homeKeys.sceneExcerpt(),
    queryFn: fetchSceneExcerpt,
    staleTime: FIVE_MINUTES,
  });
}

/** ISO timestamp for local midnight on the first of the current month. */
export function firstOfMonthISO(now: Date = new Date()): string {
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
}

export function useMonthlySceneCount() {
  const finishedAfter = firstOfMonthISO();
  return useQuery<number>({
    queryKey: homeKeys.monthlySceneCount(finishedAfter),
    queryFn: () => getCompletedSceneCount(finishedAfter),
    staleTime: FIVE_MINUTES,
  });
}
