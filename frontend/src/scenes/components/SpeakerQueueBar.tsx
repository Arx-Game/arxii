import { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ListOrdered, ChevronRight, UserPlus, UserMinus, ListX } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  fetchSpeakerQueue,
  openSpeakerQueue,
  joinSpeakerQueue,
  leaveSpeakerQueue,
  advanceSpeakerQueue,
  closeSpeakerQueue,
  skipSpeakerInQueue,
} from '../actionQueries';
import type { SpeakerQueue as SpeakerQueueType } from '../actionTypes';
import { useAppSelector } from '@/store/hooks';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';

interface Props {
  roomId: string;
}

export function SpeakerQueueBar({ roomId }: Props) {
  const qc = useQueryClient();
  const queryKey = ['speaker-queue', roomId];

  const { data, isLoading } = useQuery<{ results: SpeakerQueueType[] }>({
    queryKey,
    queryFn: () => fetchSpeakerQueue(roomId),
  });

  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const personaId = actingPersonaId(activeEntry);

  const queue = data?.results?.[0] ?? null;
  const myEntry = queue?.entries.find((e) => e.persona === personaId) ?? null;
  const isCurrent = myEntry?.position === 1;
  const isOpenedByMe = queue?.opened_by === personaId;

  const invalidate = () => qc.invalidateQueries({ queryKey });

  const openMut = useMutation({
    mutationFn: () => openSpeakerQueue(Number(roomId)),
    onSuccess: invalidate,
  });
  const joinMut = useMutation({
    mutationFn: () => joinSpeakerQueue(queue!.id),
    onSuccess: invalidate,
  });
  const leaveMut = useMutation({
    mutationFn: () => leaveSpeakerQueue(queue!.id),
    onSuccess: invalidate,
  });
  const advanceMut = useMutation({
    mutationFn: () => advanceSpeakerQueue(queue!.id),
    onSuccess: invalidate,
  });
  const closeMut = useMutation({
    mutationFn: () => closeSpeakerQueue(queue!.id),
    onSuccess: invalidate,
  });
  const skipMut = useMutation({
    mutationFn: (name: string) => skipSpeakerInQueue(queue!.id, name),
    onSuccess: invalidate,
  });

  if (isLoading) return null;

  // No active queue — show open button
  if (!queue) {
    return (
      <div className="flex items-center gap-2 border-b px-2 py-1.5">
        <ListOrdered className="h-4 w-4 shrink-0 text-muted-foreground" />
        <Button
          size="sm"
          variant="ghost"
          onClick={() => openMut.mutate()}
          disabled={openMut.isPending}
        >
          Open Speaker Line
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 border-b px-2 py-1.5">
      <ListOrdered className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="text-xs font-medium text-muted-foreground">Speaker Line:</span>
      <div className="flex flex-wrap gap-1">
        {queue.entries.map((entry) => (
          <span
            key={entry.id}
            className={`rounded px-2 py-0.5 text-xs ${
              entry.position === 1
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground'
            }`}
          >
            {entry.position === 1 && <ChevronRight className="mr-0.5 inline h-3 w-3" />}
            {entry.persona_name}
          </span>
        ))}
        {queue.entries.length === 0 && (
          <span className="text-xs italic text-muted-foreground">Empty</span>
        )}
      </div>
      <div className="ml-auto flex gap-1">
        {!myEntry && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => joinMut.mutate()}
            disabled={joinMut.isPending}
          >
            <UserPlus className="mr-0.5 h-3 w-3" />
            Join
          </Button>
        )}
        {myEntry && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => leaveMut.mutate()}
            disabled={leaveMut.isPending}
          >
            <UserMinus className="mr-0.5 h-3 w-3" />
            Leave
          </Button>
        )}
        {(isCurrent || isOpenedByMe) && queue.entries.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => advanceMut.mutate()}
            disabled={advanceMut.isPending}
          >
            Next
          </Button>
        )}
        {queue.entries.length > 0 && (
          <select
            className="h-7 rounded border bg-background px-1 text-xs"
            defaultValue=""
            onChange={(e) => {
              const name = e.target.value;
              if (name) skipMut.mutate(name);
              e.target.value = '';
            }}
            disabled={skipMut.isPending}
            aria-label="Skip a speaker"
          >
            <option value="" disabled>
              Skip…
            </option>
            {queue.entries
              .filter((e) => e.persona !== personaId)
              .map((entry) => (
                <option key={entry.id} value={entry.persona_name}>
                  Skip {entry.persona_name}
                </option>
              ))}
          </select>
        )}
        {isOpenedByMe && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => closeMut.mutate()}
            disabled={closeMut.isPending}
          >
            <ListX className="mr-0.5 h-3 w-3" />
            Close
          </Button>
        )}
      </div>
    </div>
  );
}
