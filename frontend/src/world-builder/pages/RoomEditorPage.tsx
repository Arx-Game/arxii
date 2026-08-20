/**
 * RoomEditorPage — /staff/world-builder/rooms/:roomId (#3283).
 *
 * Nearly all authoring work happens on a room, and the canvas page's 320px
 * side panel compressed it badly. This page gives one room the full width:
 * hierarchy breadcrumb on top (building › neighborhood › city, at a glance),
 * then the identity panel and every authoring section flowing in responsive
 * columns. Self-sufficient on the room-detail endpoint (which carries the
 * room row, catalogs, and breadcrumb), so it deep-links and survives reloads.
 */
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { RoomDetailPanel } from '../components/RoomDetailPanel';
import { useRoomDetailQuery, useWorldBuilderAction } from '../queries';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import type { WorldBuilderActionKey } from '../types';

export function RoomEditorPage() {
  const { roomId } = useParams();
  const navigate = useNavigate();
  const characterId = useWorldBuilderActor();
  const parsedRoomId = roomId ? Number(roomId) : null;
  const { data: detail, isLoading } = useRoomDetailQuery(parsedRoomId);
  const { mutate: runMutation } = useWorldBuilderAction(
    characterId ?? 0,
    detail?.room.area_id ?? null
  );

  const runAction = (key: string, kwargs: Record<string, unknown>) => {
    if (characterId == null) {
      toast.error('You need a character to build as — mint one from the World Builder page.');
      return;
    }
    runMutation({ key: key as WorldBuilderActionKey, kwargs });
  };

  if (isLoading || !detail) {
    return <Skeleton className="m-4 h-64 w-full" />;
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-3 p-4" data-testid="room-editor-page">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => navigate('/staff/world-builder')}>
          ← Canvas
        </Button>
        <nav className="text-sm text-muted-foreground" data-testid="room-editor-breadcrumb">
          {detail.breadcrumb.map((crumb) => (
            <span key={crumb.id}>
              <Link to="/staff/world-builder" className="hover:underline">
                {crumb.name}
              </Link>
              <span className="mx-1">›</span>
            </span>
          ))}
          <span className="font-medium text-foreground">{detail.room.name}</span>
        </nav>
      </div>
      <div className="columns-1 gap-4 lg:columns-2 xl:columns-3 [&>*]:mb-4 [&>*]:break-inside-avoid">
        <RoomDetailPanel
          room={detail.room}
          catalogs={detail.catalogs}
          exits={[]}
          runAction={runAction}
          onLinkRooms={() => navigate('/staff/world-builder')}
        />
      </div>
    </div>
  );
}
