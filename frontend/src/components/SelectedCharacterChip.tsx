import { Link } from 'react-router-dom';
import { DoorOpen, X } from 'lucide-react';

import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { PersonaSwitcher } from '@/game/components/PersonaSwitcher';
import { useSelectCharacterMutation } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';

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
 * works app-wide, not just once you're already in the game), an "Enter the
 * world" link into `/game` (the ONE deliberate selection->presence crossing —
 * `GamePage`'s own mount-path effect does the actual auto-puppeting, not this
 * component), and a quiet "step away" that clears the selection.
 *
 * PLACEHOLDER copy throughout — final chrome wording/visual design is a
 * separate pass; this markup stays plain shadcn primitives on purpose so
 * restyling later is cheap.
 */
export function SelectedCharacterChip({ entry }: SelectedCharacterChipProps) {
  const selectCharacter = useSelectCharacterMutation();

  return (
    <div className="flex items-center gap-2 rounded-md border px-2 py-1">
      <Avatar className="h-8 w-8">
        <AvatarImage src={entry.profile_picture_url ?? undefined} alt={entry.name} />
        <AvatarFallback className="text-xs">{getInitials(entry.name)}</AvatarFallback>
      </Avatar>
      <span className="text-sm font-medium">{entry.name}</span>
      <PersonaSwitcher
        characterSheetId={entry.character_id}
        activePersonaId={entry.active_persona_id}
      />
      <Button asChild variant="secondary" size="sm">
        {/* PLACEHOLDER copy */}
        <Link to="/game">
          <DoorOpen className="h-3.5 w-3.5" />
          Enter the world
        </Link>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 text-muted-foreground"
        title="Step away"
        disabled={selectCharacter.isPending}
        onClick={() => selectCharacter.mutate(null)}
      >
        <X className="h-3.5 w-3.5" />
        {/* PLACEHOLDER copy */}
        <span className="sr-only">Step away</span>
      </Button>
    </div>
  );
}
