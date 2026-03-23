import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneMessages } from '../components/SceneMessages';
import { ActionPanel } from '../components/ActionPanel';
import { PlaceBar } from '../components/PlaceBar';
import { ConsentPrompt } from '../components/ConsentPrompt';

export function SceneDetailPage() {
  const { id = '' } = useParams();
  const { data: scene, refetch } = useQuery<SceneDetail>({
    queryKey: ['scene', id],
    queryFn: () => fetchScene(id),
    refetchInterval: (query) => (query.state.data?.is_active ? 60000 : false),
  });

  const isActive = scene?.is_active ?? false;

  return (
    <div className="container mx-auto p-4">
      <SceneHeader scene={scene} onRefresh={() => refetch()} />
      {isActive && <ConsentPrompt sceneId={id} />}
      <PlaceBar sceneId={id} />
      <SceneMessages sceneId={id} />
      {isActive && <ActionPanel sceneId={id} />}
    </div>
  );
}
