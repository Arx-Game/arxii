import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { startScene, finishScene } from '../../scenes/queries';
import type { SceneSummary } from '../../hooks/types';
import { useAppDispatch } from '../../store/hooks';
import { setSessionScene } from '../../store/gameSlice';

interface Props {
  character: string;
  scene: SceneSummary | null;
  room: { id: number; name: string } | null;
}

export function SceneWindow({ character, scene, room }: Props) {
  const dispatch = useAppDispatch();
  const start = useMutation({
    mutationFn: () => {
      if (!room) throw new Error('No room');
      const name = `${character} scene at ${room.name} on ${new Date().toISOString().slice(0, 10)}`;
      return startScene(room.id, name);
    },
    onSuccess: (data: SceneSummary) => {
      dispatch(setSessionScene({ character, scene: data }));
    },
  });

  const end = useMutation({
    mutationFn: () => finishScene(String(scene?.id)),
    onSuccess: () => {
      dispatch(setSessionScene({ character, scene: null }));
    },
  });

  if (!room) return null;

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        {scene ? (
          <div className="flex items-center justify-between">
            <Link to={`/scenes/${scene.id}`} className="underline">
              {scene.name}
            </Link>
            {scene.is_owner && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => end.mutate()}
                disabled={end.isPending}
              >
                End Scene
              </Button>
            )}
          </div>
        ) : (
          <Button size="sm" onClick={() => start.mutate()} disabled={start.isPending}>
            Start Scene
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
