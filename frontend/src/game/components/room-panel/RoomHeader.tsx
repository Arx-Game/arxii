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
  /** Show the "Edit" affordance — true only when the viewer owns this room (#1470). */
  canEdit?: boolean;
  onEditRoom?: () => void;
}

export function RoomHeader({
  name,
  scene,
  onStartScene,
  onEndScene,
  isStartPending,
  isEndPending,
  canEdit = false,
  onEditRoom,
}: RoomHeaderProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{name}</h3>
        {canEdit && onEditRoom && (
          <Button variant="ghost" size="sm" className="h-5 px-1 text-xs" onClick={onEditRoom}>
            Edit
          </Button>
        )}
      </div>
      {scene ? (
        <div className="mt-1 flex items-center gap-2">
          <Link to={`/scenes/${scene.id}`}>
            <Badge variant="secondary" className="text-xs">
              Scene: {scene.name}
            </Badge>
          </Link>
          {scene.has_unseen_observer && (
            <Badge variant="destructive" className="text-xs">
              ⚠ OOC: an unseen observer is present
            </Badge>
          )}
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
