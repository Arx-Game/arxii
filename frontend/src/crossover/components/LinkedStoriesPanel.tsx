/**
 * LinkedStoriesPanel — shows linked stories' stakes summaries on the scene page (#2075).
 *
 * Fetches EpisodeScene rows for the scene, then for each linked episode fetches
 * its beats and their stakes summaries. Renders nothing if no linked episodes exist
 * (normal non-crossover scene). Privacy is enforced server-side: the stakes-summary
 * endpoint only returns data for beats the viewer can see.
 */

import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { useEpisodeScenesForScene, getStakesSummary } from '../queries';
import { crossoverKeys } from '../queries';
import type { Beat, EpisodeScene } from '../types';
import type { StakesSummary } from '../api';

interface LinkedStoriesPanelProps {
  sceneId: number | string;
}

interface BeatWithStakes {
  beat: Beat;
  stakes?: StakesSummary;
}

export function LinkedStoriesPanel({ sceneId }: LinkedStoriesPanelProps) {
  const numericSceneId = typeof sceneId === 'string' ? Number(sceneId) : sceneId;
  const { data: episodeScenesData, isLoading } = useEpisodeScenesForScene(
    Number.isFinite(numericSceneId) ? numericSceneId : null
  );

  const episodeScenes = (episodeScenesData?.results ?? []) as EpisodeScene[];

  // Fetch beats for each linked episode in a single query
  const beatsQuery = useQuery({
    queryKey: [
      ...crossoverKeys.all,
      'beats',
      'scene',
      numericSceneId,
      episodeScenes.map((es) => es.episode_id),
    ],
    queryFn: async () => {
      const results: Record<number, Beat[]> = {};
      for (const es of episodeScenes) {
        const res = await apiFetch(`/api/beats/?episode=${es.episode_id}&page_size=50`);
        if (res.ok) {
          const data = await res.json();
          results[es.episode_id] = (data.results ?? []) as Beat[];
        }
      }
      return results;
    },
    enabled: episodeScenes.length > 0,
  });

  // Flatten all beats across episodes for stakes-summary fetching
  const allBeats = useMemo(() => {
    const beats: { episodeId: number; episodeTitle: string; beat: Beat }[] = [];
    for (const es of episodeScenes) {
      const epBeats = beatsQuery.data?.[es.episode_id] ?? [];
      for (const beat of epBeats) {
        beats.push({
          episodeId: es.episode_id,
          episodeTitle: es.episode ?? `Episode #${es.episode_id}`,
          beat,
        });
      }
    }
    return beats;
  }, [episodeScenes, beatsQuery.data]);

  // Fetch stakes summaries for all beats
  const stakesQueries = useQueries({
    queries: allBeats.map(({ beat }) => ({
      queryKey: [...crossoverKeys.all, 'stakes-summary', beat.id],
      queryFn: () => getStakesSummary(beat.id),
      enabled: allBeats.length > 0,
      throwOnError: false,
    })),
  });

  // Group beats by episode with their stakes
  const episodesWithStakes = useMemo(() => {
    const map = new Map<number, { title: string; beats: BeatWithStakes[] }>();
    for (let i = 0; i < allBeats.length; i++) {
      const { episodeId, episodeTitle, beat } = allBeats[i];
      if (!map.has(episodeId)) {
        map.set(episodeId, { title: episodeTitle, beats: [] });
      }
      map.get(episodeId)!.beats.push({
        beat,
        stakes: stakesQueries[i]?.data as StakesSummary | undefined,
      });
    }
    return Array.from(map.entries()).map(([id, data]) => ({ id, ...data }));
  }, [allBeats, stakesQueries]);

  // Don't render if loading or no linked stories
  if (isLoading) return null;
  if (episodeScenes.length === 0) return null;

  return (
    <div className="rounded-lg border p-4" data-testid="linked-stories-panel">
      <h3 className="mb-3 text-sm font-semibold">Linked Stories</h3>
      <div className="space-y-4">
        {episodesWithStakes.map(({ id, title, beats }) => (
          <div key={id} className="space-y-2">
            <p className="text-sm font-medium">{title}</p>
            {beats.length === 0 ? (
              <p className="text-xs text-muted-foreground">No beats found.</p>
            ) : (
              <div className="space-y-1">
                {beats.map(({ beat, stakes }) => (
                  <div
                    key={beat.id}
                    className="flex items-center gap-2 text-xs"
                    data-testid={`linked-beat-${beat.id}`}
                  >
                    <span className="font-medium">{beat.name ?? `Beat ${beat.order}`}</span>
                    {stakes && (
                      <>
                        <span className="rounded bg-muted px-1.5 py-0.5">
                          Risk: {stakes.declared_risk}
                        </span>
                        <span className="text-muted-foreground">
                          {stakes.is_ready ? '✓ Ready' : '○ Not ready'}
                        </span>
                        {stakes.stakes.length > 0 && (
                          <span className="text-muted-foreground">
                            ({stakes.stakes.length} stake
                            {stakes.stakes.length !== 1 ? 's' : ''})
                          </span>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
