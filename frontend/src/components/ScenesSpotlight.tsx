import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../evennia_replacements/api';
import { SceneListCard } from './SceneListCard';
import type { SceneSummary } from '../scenes/types';

interface ScenesSpotlightData {
  in_progress: SceneSummary[];
  recent: SceneSummary[];
}

async function fetchScenesSpotlight(): Promise<ScenesSpotlightData> {
  const res = await apiFetch('/api/scenes/spotlight/');
  if (!res.ok) {
    throw new Error('Failed to load scenes');
  }
  return res.json();
}

export function ScenesSpotlight() {
  const { data } = useQuery({
    queryKey: ['scenes', 'spotlight'],
    queryFn: fetchScenesSpotlight,
  });

  return (
    <section className="container mx-auto grid gap-4 py-8 md:grid-cols-2">
      <SceneListCard
        title="In Progress"
        scenes={data?.in_progress ?? []}
        emptyMessage="No active scenes."
      />
      <SceneListCard
        title="Recently Concluded"
        scenes={data?.recent ?? []}
        emptyMessage="No recently concluded scenes."
      />
    </section>
  );
}
