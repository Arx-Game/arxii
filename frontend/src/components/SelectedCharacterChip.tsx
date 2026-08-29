import { Link, useLocation } from 'react-router-dom';
import { DoorOpen } from 'lucide-react';

import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { PersonaSwitcher } from '@/game/components/PersonaSwitcher';
import { useCharacterPersonasQuery } from '@/game/personaQueries';
import { cn } from '@/lib/utils';
import type { MyRosterEntry } from '@/roster/types';
import { dockedStateLabel } from '@/roster/lifecycleDisplay';

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
 * Selection is NOT presence: this chip never starts or stops a `/game`
 * session on its own. It shows the portrait + name, the same `PersonaSwitcher`
 * `GameTopBar` mounts inside `/game` (re-mounted here so identity-switching
 * works app-wide, not just once you're already in the game), and an "Enter the
 * world" link into `/game` (the ONE deliberate selection->presence crossing —
 * `GamePage`'s own mount-path effect does the actual auto-puppeting, not this
 * component).
 *
 * The chip deliberately carries NO clear-selection control (Apostate ruling,
 * 2026-08-28: "step away" next to Enter-the-world read as logout). Clearing
 * lives with the character list — the Hall's "Your Characters" band gains a
 * "Clear Active Character" control in slice 2. Ruled vocabulary: "Log out" =
 * account; "quit" (telnet) = leave the world but stay selected; "Clear Active
 * Character" = no selection, still logged in.
 *
 * Portrait-forward restyle (#3412 slice 2, Direction B "Commonplace Book" —
 * ratified 2026-08-28): the portrait is the load-bearing state signal, so it
 * grows to `h-11`; the name takes the Cinzel identity voice
 * (`.theme-heading`); a data-voice sub-line under the name spells out the
 * worn persona and presence state; "Enter the world" becomes the folio's
 * squared primary button (no radius, tracked uppercase). All colors flow
 * through realm tokens — no literals — so the chip holds in every realm and
 * dark mode by construction.
 *
 * PLACEHOLDER copy: "Playing: Currently Offscreen" is a stand-in for real
 * presence state (not wired to the WebSocket session yet — this chip still
 * never starts/stops a session on its own, see above).
 *
 * Degraded-state sub-line (#3412 final review, IMPORTANT-1): a docked
 * character whose `lifecycle_state` is CAPTURED/DEAD/RETIRED/UNKNOWN used to
 * assert "Playing: Currently Offscreen" on every non-`/game` page — a
 * factual contradiction with the Hall's `OffscreenActsPlate` death/captivity
 * prose shown for the same character. The sub-line now branches the same way
 * the plate does (mirrors its `ALLOWED_LIFECYCLE_STATES` set) and shows a
 * short PLACEHOLDER state label instead. "Enter the world" stays rendered in
 * every state deliberately — a dead character's player legitimately enters
 * as a spectator/ghost (the dead-gate whitelist exists for exactly that,
 * #2287) — only the sub-line's wording changes.
 */
export function SelectedCharacterChip({ entry }: SelectedCharacterChipProps) {
  const { data: personas = [] } = useCharacterPersonasQuery(entry.character_id);
  const worn =
    personas.find((p) => p.id === entry.active_persona_id) ??
    personas.find((p) => p.persona_type === 'primary') ??
    personas[0];
  const wornName = worn?.name ?? entry.name;
  // On /game the player IS in the world — asserting "Currently Offscreen"
  // there would be a false fact, so the state fragment drops and only the
  // worn-persona line remains. Real presence wiring is a later slice.
  const { pathname } = useLocation();
  const inWorld = pathname.startsWith('/game');

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
        {/* PLACEHOLDER copy — presence state isn't wired yet */}
        <span className="font-body text-xs text-muted-foreground">
          as {wornName}
          {inWorld ? '' : ` · Playing: ${dockedStateLabel(entry.lifecycle_state)}`}
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
        {/* PLACEHOLDER copy */}
        <Link to="/game">
          <DoorOpen className="h-3.5 w-3.5" />
          Enter the world
        </Link>
      </Button>
    </div>
  );
}
