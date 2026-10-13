import type { MyRosterEntry } from '@/roster/types';
import { useAppSelector } from '@/store/hooks';

export interface CharacterPresence {
  /** The character is puppeted somewhere: here, another tab, or another device. */
  inWorld: boolean;
  /** The room the character stands in, from this tab's socket when it has one, else the server. */
  roomName: string | null;
  /** Sessions puppeting the character, as the server last reported them. */
  sessionCount: number;
  /** This tab holds an open socket for the character. */
  hasLocalSocket: boolean;
}

/**
 * The one presence rule (#4321, ADR-4321): a character is in the world when a
 * session puppets it, and the server is the only thing that knows that for
 * every tab and device. This tab's own socket (`gameSlice.sessions`) is the
 * fast path, correct the instant it opens or closes, and the only source of
 * the room while the session is still entering; the roster payload's
 * `session_count` and `room_name` (`GET /api/roster/entries/mine/`) cover a
 * tab that opened no socket, which before this hook said "Not in the world"
 * about a character standing in a room in the tab next to it.
 *
 * Every surface that states presence reads it here: the header chip, the
 * Hall's docked card and the world menu. `GatefoldPage`'s `/` redirect is
 * the deliberate exception and keeps reading the local socket alone, so a
 * fresh tab is never sent into the game because the character is in the
 * world elsewhere.
 */
export function useCharacterPresence(entry: MyRosterEntry | null): CharacterPresence {
  const session = useAppSelector((state) => (entry ? state.game.sessions[entry.name] : undefined));
  const hasLocalSocket = Boolean(session?.isConnected);
  const sessionCount = entry?.session_count ?? 0;
  const inWorld = hasLocalSocket || sessionCount > 0;
  const roomName = session?.room?.name ?? entry?.room_name ?? null;
  return { inWorld, roomName, sessionCount, hasLocalSocket };
}
