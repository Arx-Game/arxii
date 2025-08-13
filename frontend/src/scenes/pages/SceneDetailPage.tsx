import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneMessages } from '../components/SceneMessages';

export function SceneDetailPage() {
  const { id = '' } = useParams();
  const { data: scene, refetch } = useQuery<SceneDetail>({
    queryKey: ['scene', id],
    queryFn: () => fetchScene(id),
    refetchInterval: (query) => (query.state.data?.is_active ? 60000 : false),
  });
  return (
    <div className="container mx-auto p-4">
      <SceneHeader scene={scene} onRefresh={() => refetch()} />
      <SceneMessages sceneId={id} />
    </div>
  );
}
