import { Link, useLocation } from 'react-router-dom';
import { DoorClosed, DoorOpen } from 'lucide-react';

import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { PersonaSwitcher } from '@/game/components/PersonaSwitcher';
import { useCharacterPersonasQuery } from '@/game/personaQueries';
import { useGameSocket } from '@/hooks/useGameSocket';
import { cn } from '@/lib/utils';
import type { MyRosterEntry } from '@/roster/types';
import { dockedStateLabel } from '@/roster/lifecycleDisplay';
import { useAppSelector } from '@/store/hooks';

interface SelectedCharacterChipProps {
  entry: MyRosterEntry;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Docked-portrait chip (#3412) — the app-wide chrome surface for the account's
 * durable server-side character selection (`gameSlice.active`/`activeEntryId`,
 * hydrated from `GET /api/user/`'s `selected_entry`; see `useAccountQuery`).
 * Rendered by `Header` right after `SiteTitle`, ONLY when a selection exists —
 * when there's none the header renders exactly as it did before this chip
 * existed.
 *
 * Selection is NOT presence, and the chip shows both (#3859). Presence is the
 * character's live game session in the store (`sessions[name].isConnected`,
 * the same fact `GatefoldPage`'s `/` redirect and `GameTopBar`'s connection
 * dot read). Sockets live at module scope and `GamePage` has no teardown
 * (ADR-0295), so a player who opens the Hall or the roster from the world
 * menu is still in the world; the chip used to say "Enter the world" and
 * "Playing: Currently Offscreen" on that page regardless, which was a false
 * fact on every page the header renders. Now:
 *
 * - live session: the sub-line reads "In the world" (with the room's name
 *   when the session has one), the primary button is "Return to the world",
 *   and a "Leave the world" button closes that character's socket — the same
 *   `useGameSocket().disconnect(name)` the world menu's item calls, so the
 *   server unpuppets them and nobody stands unpiloted on the grid;
 * - no session: "Enter the world" into `/game` (the ONE deliberate
 *   selection->presence crossing — `GamePage`'s own mount-path effect does the
 *   actual auto-puppeting, not this component), and the sub-line says "Not in
 *   the world".
 *
 * The chip deliberately carries NO clear-selection control (Apostate ruling,
 * 2026-08-28: "step away" next to Enter-the-world read as logout). Clearing
 * lives with the character list — the Hall's "Your Characters" band gains a
 * "Clear Active Character" control in slice 2. Ruled vocabulary: "Log out" =
 * account; "quit" (telnet) = leave the world but stay selected; "Clear Active
 * Character" = no selection, still logged in. "Leave the world" is that same
 * quit: presence ends, selection stays.
 *
 * Portrait-forward restyle (#3412 slice 2, Direction B "Commonplace Book" —
 * ratified 2026-08-28): the portrait is the load-bearing state signal, so it
 * grows to `h-11`; the name takes the Cinzel identity voice
 * (`.theme-heading`); a data-voice sub-line under the name spells out the
 * worn persona and presence state; the primary action is the folio's squared
 * button (no radius, tracked uppercase). All colors flow through realm tokens
 * — no literals — so the chip holds in every realm and dark mode by
 * construction.
 *
 * Degraded-state sub-line (#3412 final review, IMPORTANT-1): a docked
 * character whose `lifecycle_state` is CAPTURED/DEAD/RETIRED/UNKNOWN shows the
 * short state label (`dockedStateLabel`) instead of a presence claim, the
 * same branch the Hall's `OffscreenActsPlate` takes. "Enter the world" stays
 * rendered for them deliberately — a dead character's player legitimately
 * enters as a spectator/ghost (the dead-gate whitelist exists for exactly
 * that, #2287) — only the sub-line's wording changes.
 */
export function SelectedCharacterChip({ entry }: SelectedCharacterChipProps) {
  const { data: personas = [] } = useCharacterPersonasQuery(entry.character_id);
  const worn =
    personas.find((p) => p.id === entry.active_persona_id) ??
    personas.find((p) => p.persona_type === 'primary') ??
    personas[0];
  const wornName = worn?.name ?? entry.name;

  const session = useAppSelector((state) => state.game.sessions[entry.name]);
  const live = Boolean(session?.isConnected);
  const roomName = session?.room?.name ?? null;
  const { disconnect } = useGameSocket();

  // On /game the top bar already carries the connection state, and the header
  // is not rendered there at all (Layout's full-viewport routes); the guard
  // stays so a future full-chrome /game never shows the fact twice.
  const { pathname } = useLocation();
  const onGamePage = pathname.startsWith('/game');

  let presence: string;
  if (live) {
    presence = roomName ? `In the world, ${roomName}` : 'In the world';
  } else {
    presence = dockedStateLabel(entry.lifecycle_state);
  }

  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-none border bg-card px-2 py-1',
        'text-card-foreground'
      )}
    >
      <Avatar className="h-11 w-11 rounded-none">
        <AvatarImage src={entry.profile_picture_url ?? undefined} alt={entry.name} />
        <AvatarFallback className="rounded-none text-sm">{getInitials(entry.name)}</AvatarFallback>
      </Avatar>
      <div className="flex flex-col leading-tight">
        <span className="theme-heading text-sm font-semibold [font-variant:small-caps]">
          {entry.name}
        </span>
        <span className="font-body text-xs text-muted-foreground">
          as {wornName}
          {onGamePage ? '' : ` · ${presence}`}
        </span>
        <PersonaSwitcher
          characterSheetId={entry.character_id}
          activePersonaId={entry.active_persona_id}
        />
      </div>
      <Button
        asChild
        variant="default"
        size="sm"
        className="rounded-none uppercase tracking-[0.08em]"
      >
        <Link to="/game">
          <DoorOpen className="h-3.5 w-3.5" />
          {live ? 'Return to the world' : 'Enter the world'}
        </Link>
      </Button>
      {live && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-none uppercase tracking-[0.08em]"
          title={`Leave the world as ${entry.name}: your character leaves the grid; you stay signed in and selected`}
          onClick={() => disconnect(entry.name)}
        >
          <DoorClosed className="h-3.5 w-3.5" />
          Leave the world
        </Button>
      )}
    </div>
  );
}
