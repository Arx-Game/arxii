/**
 * NewCharacterTile (#3996) — the Hall's way to start another character. Always
 * present after the character cards. Shows the slot count as a bare
 * `used of total` (nothing for an exempt staff account) and two actions:
 * browse the roster, or create a character. When the slots are full both stay
 * visible but disabled, and the tile lists what holds a slot with the action
 * that frees it: Freeze for an original character, Give up for a roster
 * character, a link back into the draft, or the pending application by name.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Plate } from '@/components/folio';
import type { CharacterSlots, SlotHolder } from '@/evennia_replacements/types';
import type { MyRosterEntry } from '@/roster/types';
import { SlotActionDialog } from './SlotActionDialog';
import { slotActionFor, slotActionLabel, type SlotAction } from './slotActions';

interface NewCharacterTileProps {
  slots: CharacterSlots | undefined;
  characters: MyRosterEntry[];
}

function HolderRow({
  holder,
  entry,
  onAct,
}: {
  holder: SlotHolder;
  entry: MyRosterEntry | undefined;
  onAct: (entry: MyRosterEntry, action: SlotAction) => void;
}) {
  if (holder.kind === 'draft') {
    return (
      <li className="flex items-center justify-between gap-2">
        <span>Your draft</span>
        <Link to="/characters/create" className="text-xs underline">
          Finish or discard
        </Link>
      </li>
    );
  }
  if (holder.kind === 'application' || entry == null) {
    return (
      <li className="flex items-center justify-between gap-2">
        <span>{holder.name}</span>
        <span className="text-xs text-muted-foreground">
          {holder.kind === 'application' ? 'Application pending' : ''}
        </span>
      </li>
    );
  }
  const action = slotActionFor(entry);
  return (
    <li className="flex items-center justify-between gap-2">
      <span>{holder.name}</span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 rounded-none text-xs"
        onClick={() => onAct(entry, action)}
      >
        {slotActionLabel(action)}
      </Button>
    </li>
  );
}

export function NewCharacterTile({ slots, characters }: NewCharacterTileProps) {
  const [pending, setPending] = useState<{ entry: MyRosterEntry; action: SlotAction } | null>(null);
  const exempt = slots == null || slots.total == null;
  const full = !exempt && slots.used >= (slots.total ?? 0);
  const byEntryId = new Map(characters.map((entry) => [entry.id, entry]));
  const occupants = slots?.holders.filter((holder) => holder.counts) ?? [];

  return (
    <Plate className="flex flex-col gap-3 p-3" data-testid="new-character-tile">
      {!exempt && (
        <span className="theme-heading text-sm font-semibold [font-variant:small-caps]">
          {slots.used} of {slots.total}
        </span>
      )}
      <div className="flex flex-col gap-2">
        {full ? (
          <>
            <Button type="button" variant="outline" size="sm" className="rounded-none" disabled>
              Browse the roster
            </Button>
            <Button type="button" variant="outline" size="sm" className="rounded-none" disabled>
              Create a character
            </Button>
          </>
        ) : (
          <>
            <Button asChild variant="outline" size="sm" className="rounded-none">
              <Link to="/roster">Browse the roster</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="rounded-none">
              <Link to="/characters/create">Create a character</Link>
            </Button>
          </>
        )}
      </div>
      {full && (
        <ul className="flex flex-col gap-1 font-body text-sm" aria-label="Holding your slots">
          {occupants.map((holder) => (
            <HolderRow
              key={`${holder.kind}-${holder.roster_entry_id ?? holder.name}`}
              holder={holder}
              entry={
                holder.roster_entry_id != null ? byEntryId.get(holder.roster_entry_id) : undefined
              }
              onAct={(entry, action) => setPending({ entry, action })}
            />
          ))}
        </ul>
      )}
      <SlotActionDialog
        entry={pending?.entry ?? null}
        action={pending?.action ?? null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      />
    </Plate>
  );
}
