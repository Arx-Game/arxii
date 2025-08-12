import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchScene, SceneDetail } from '../queries';
import { SceneHeader } from '../components/SceneHeader';
import { SceneMessages } from '../components/SceneMessages';

export function SceneDetailPage() {
  const { id = '' } = useParams();
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: ['scene', id],
    queryFn: () => fetchScene(id),
  });
  return (
    <div className="container mx-auto p-4">
      <SceneHeader scene={scene} />
      <SceneMessages sceneId={id} />
    </div>
  );
}
