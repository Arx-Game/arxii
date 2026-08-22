import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dices } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppSelector } from '@/store/hooks';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import {
  fetchPlaces,
  fetchTavernGames,
  fetchTavernGameSessions,
  joinTavernGameSession,
  leaveTavernGameSession,
  openTavernGameSession,
  rollTavernGameSession,
} from '../actionQueries';

interface Props {
  roomId: string;
}

/**
 * The Place-bar coin-stakes game widget (#3292): shows the open table (if
 * any) at the viewer's current Place, with Join/Roll/Leave controls, plus a
 * simple form to open a new one. No animation - the roll result is just a
 * number in the response.
 */
export function TavernGameWidget({ roomId }: Props) {
  const qc = useQueryClient();
  const placesQueryKey = ['scene-places', roomId];
  const sessionsQueryKey = ['tavern-game-sessions', roomId];

  const { data: placesData } = useQuery({
    queryKey: placesQueryKey,
    queryFn: () => fetchPlaces(roomId),
  });
  const { data: gamesData } = useQuery({
    queryKey: ['tavern-games'],
    queryFn: fetchTavernGames,
  });
  const { data: sessionsData, isLoading } = useQuery({
    queryKey: sessionsQueryKey,
    queryFn: () => fetchTavernGameSessions(roomId),
  });

  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  const personaId = actingPersonaId(activeEntry);

  const myPlace = placesData?.results?.find((p) => p.viewer_is_present) ?? null;
  const games = gamesData?.results ?? [];
  const session =
    sessionsData?.results?.find((s) => myPlace != null && s.place === myPlace.id) ?? null;
  const mySeat = session?.seats.find((seat) => seat.persona === personaId) ?? null;

  const [gameId, setGameId] = useState<number | ''>('');
  const [ante, setAnte] = useState<string>('');

  const invalidate = () => qc.invalidateQueries({ queryKey: sessionsQueryKey });

  const openMut = useMutation({
    mutationFn: () => openTavernGameSession(myPlace!.id, Number(gameId), Number(ante)),
    onSuccess: invalidate,
  });
  const joinMut = useMutation({
    mutationFn: () => joinTavernGameSession(session!.id),
    onSuccess: invalidate,
  });
  const rollMut = useMutation({
    mutationFn: () => rollTavernGameSession(session!.id),
    onSuccess: invalidate,
  });
  const leaveMut = useMutation({
    mutationFn: () => leaveTavernGameSession(session!.id),
    onSuccess: invalidate,
  });

  if (isLoading || myPlace == null) return null;

  if (!session) {
    if (games.length === 0) return null;
    return (
      <div className="flex items-center gap-2 border-b px-2 py-1.5">
        <Dices className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">Table games:</span>
        <select
          className="h-7 rounded border bg-background px-1 text-xs"
          value={gameId}
          onChange={(e) => setGameId(e.target.value ? Number(e.target.value) : '')}
          aria-label="Game to open"
        >
          <option value="">Choose a game...</option>
          {games.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <input
          className="h-7 w-16 rounded border bg-background px-1 text-xs"
          type="number"
          min={1}
          placeholder="Ante"
          value={ante}
          onChange={(e) => setAnte(e.target.value)}
          aria-label="Ante"
        />
        <Button
          size="sm"
          variant="ghost"
          disabled={!gameId || !ante || openMut.isPending}
          onClick={() => openMut.mutate()}
        >
          Open
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 border-b px-2 py-1.5">
      <Dices className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="text-xs font-medium text-muted-foreground">
        {session.game_name}: ante {session.ante}, pot {session.pot}
      </span>
      <div className="flex flex-wrap gap-1">
        {session.seats.map((seat) => (
          <span key={seat.id} className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {seat.persona_name}
            {seat.roll_result != null ? `: ${seat.roll_result}` : ''}
          </span>
        ))}
      </div>
      <div className="ml-auto flex gap-1">
        {!mySeat && (
          <Button size="sm" variant="ghost" disabled={joinMut.isPending} onClick={() => joinMut.mutate()}>
            Join
          </Button>
        )}
        {mySeat && mySeat.roll_result == null && (
          <Button size="sm" variant="ghost" disabled={rollMut.isPending} onClick={() => rollMut.mutate()}>
            Roll
          </Button>
        )}
        {mySeat && (
          <Button size="sm" variant="ghost" disabled={leaveMut.isPending} onClick={() => leaveMut.mutate()}>
            Leave
          </Button>
        )}
      </div>
    </div>
  );
}
