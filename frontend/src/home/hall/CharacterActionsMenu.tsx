/**
 * CharacterActionsMenu (#3996) — the overflow menu on a Hall character card.
 * One item, chosen by the entry's provenance: Freeze or Thaw for an original
 * character, Give up for a roster character. Thaw is disabled until the
 * character's thaw date. Selecting an item opens `SlotActionDialog`.
 */
import { useState } from 'react';
import { MoreHorizontal } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { MyRosterEntry } from '@/roster/types';
import { SlotActionDialog } from './SlotActionDialog';
import { slotActionFor, slotActionLabel, type SlotAction } from './slotActions';

function thawWaitsUntil(entry: MyRosterEntry): Date | null {
  if (entry.activity_state !== 'FROZEN' || !entry.thaw_available_at) return null;
  const until = new Date(entry.thaw_available_at);
  return until.getTime() > Date.now() ? until : null;
}

export function CharacterActionsMenu({ entry }: { entry: MyRosterEntry }) {
  const [pending, setPending] = useState<SlotAction | null>(null);
  const action = slotActionFor(entry);
  const waitsUntil = action === 'thaw' ? thawWaitsUntil(entry) : null;
  const label = waitsUntil
    ? `Thaw from ${waitsUntil.toLocaleDateString()}`
    : slotActionLabel(action);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute left-1 top-1 h-7 w-7 rounded-none"
            aria-label={`Actions for ${entry.name}`}
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem disabled={waitsUntil != null} onSelect={() => setPending(action)}>
            {label}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <SlotActionDialog
        entry={pending ? entry : null}
        action={pending}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      />
    </>
  );
}
