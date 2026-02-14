import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { SceneSummary } from '@/hooks/types';

interface RoomHeaderProps {
  name: string;
  scene: SceneSummary | null;
  onStartScene: () => void;
  onEndScene: () => void;
  isStartPending: boolean;
  isEndPending: boolean;
}

export function RoomHeader({
  name,
  scene,
  onStartScene,
  onEndScene,
  isStartPending,
  isEndPending,
}: RoomHeaderProps) {
  return (
    <div className="border-b px-3 py-2">
      <h3 className="text-sm font-semibold">{name}</h3>
      {scene ? (
        <div className="mt-1 flex items-center gap-2">
          <Link to={`/scenes/${scene.id}`}>
            <Badge variant="secondary" className="text-xs">
              Scene: {scene.name}
            </Badge>
          </Link>
          {scene.is_owner && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1 text-xs text-destructive"
              onClick={onEndScene}
              disabled={isEndPending}
            >
              End
            </Button>
          )}
        </div>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          className="mt-1 h-6 px-2 text-xs"
          onClick={onStartScene}
          disabled={isStartPending}
        >
          Start Scene
        </Button>
      )}
    </div>
  );
}
