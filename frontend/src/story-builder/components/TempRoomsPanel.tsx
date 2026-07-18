/**
 * TempRoomsPanel — the GM's own active temp scene rooms (#2450): a "spin up"
 * form (name + description → `spin_up_scene_room`) and one row per active
 * `InstancedRoom`, each with a close button (`close_scene_room`) and an
 * expandable `RoomAccessPanel` for granting/revoking join access.
 *
 * `useStoryInstancesQuery` returns a bare array (the endpoint isn't
 * paginated — see `world.gm.story_views`'s `instances` action and
 * `api.ts`'s `fetchStoryInstances`), not a `{results: [...]}` page.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

import { useStoryInstancesQuery } from '../queries';
import { RoomAccessPanel } from './RoomAccessPanel';

export interface TempRoomsPanelProps {
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
  runAccessAction: (
    key: 'grant_story_room' | 'revoke_story_room',
    kwargs: Record<string, unknown>,
    onSuccess: () => void
  ) => void;
}

export function TempRoomsPanel({ runAction, runAccessAction }: TempRoomsPanelProps) {
  const { data, isLoading } = useStoryInstancesQuery();
  const instances = data ?? [];
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [expandedRoomId, setExpandedRoomId] = useState<number | null>(null);

  const spinUp = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const kwargs: Record<string, unknown> = { name: trimmed };
    if (description.trim()) kwargs.description = description.trim();
    runAction('spin_up_scene_room', kwargs);
    setName('');
    setDescription('');
  };

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto border-t p-2"
      data-testid="temp-rooms-panel"
    >
      <h3 className="px-1 text-sm font-semibold">Temp Scene Rooms</h3>
      <div className="flex flex-col gap-1.5 px-1">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Room name"
          className="h-8"
          data-testid="spin-up-name-input"
        />
        <Textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Description (optional)"
          rows={2}
        />
        <Button size="sm" onClick={spinUp} disabled={!name.trim()} data-testid="spin-up-submit">
          Spin up
        </Button>
      </div>
      {isLoading && <p className="px-1 text-xs text-muted-foreground">Loading…</p>}
      {!isLoading && instances.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">No active temp rooms.</p>
      )}
      {instances.map((instance) => (
        <div key={instance.id} className="flex flex-col gap-1 rounded-md border p-2">
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              className="flex-1 truncate text-left text-sm"
              onClick={() =>
                setExpandedRoomId((prev) => (prev === instance.room_id ? null : instance.room_id))
              }
              data-testid="temp-room-row"
              data-room-id={instance.room_id}
            >
              {instance.name}
            </button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => runAction('close_scene_room', { room_id: instance.room_id })}
              data-testid={`close-scene-room-${instance.room_id}`}
            >
              Close
            </Button>
          </div>
          {expandedRoomId === instance.room_id && (
            <RoomAccessPanel
              roomId={instance.room_id}
              grants={instance.grants}
              runAccessAction={runAccessAction}
            />
          )}
        </div>
      ))}
    </div>
  );
}
