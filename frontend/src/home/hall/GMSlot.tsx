/**
 * GMSlot — the Hall's GM/Staff operational tile (#3478 task 5), rendered by
 * `CharactersBand` as one extra grid cell after the account's PC cards, for
 * any account with `is_gm` or `is_staff` set. Two states:
 *
 * - No GM/Staff roster entry yet: a "Create GM Profile" plate opening
 *   `CreateGMCharacterDialog` (mints the character; role gating is entirely
 *   server-side, so a staff account with no approved `GMProfile` can still
 *   mint a `StaffCharacter` here).
 * - An entry exists (`character_type` "GM" or "STAFF" — treated
 *   identically, both are "the GM slot"): the same card chrome as
 *   `CharacterCard` (avatar, name, tidings count, persona tiles, selectable
 *   to dock via the band's `handleSelect`), plus a small "(GM)" chip, an
 *   edit affordance opening `EditGMProfileDialog`, and a link to the
 *   existing Tables page (never a duplicate of it). `CharacterCard` itself
 *   is private to `CharactersBand.tsx` and has no room for the extra chip/
 *   edit/link chrome, so this is a sibling using the same primitives rather
 *   than a prop-widened `CharacterCard`.
 *
 * The edit affordance only renders once `GET /api/gm/profiles/mine/`
 * resolves successfully — a staff account with a `StaffCharacter` but no
 * approved `GMProfile` row 404s there, and has nothing to edit (creating
 * still worked; gating is server-side, per the brief).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Pencil } from 'lucide-react';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { CountChip, PersonaTiles, Plate } from '@/components/folio';
import { cn } from '@/lib/utils';
import { useAccount } from '@/store/hooks';
import type { MyRosterEntry } from '@/roster/types';
import { CreateGMCharacterDialog } from './CreateGMCharacterDialog';
import { EditGMProfileDialog } from './EditGMProfileDialog';
import { useGMProfileMineQuery } from './queries';

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export interface GMSlotProps {
  /** The account's GM or Staff roster entry (`character_type !== 'PC'`), if minted. */
  gmEntry: MyRosterEntry | undefined;
  isDocked: boolean;
  onSelect: (entry: MyRosterEntry) => void;
}

export function GMSlot({ gmEntry, isDocked, onSelect }: GMSlotProps) {
  const account = useAccount();
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  // Only fetch once there's an entry to edit info for — a plain PC account
  // (this hook still runs for one, but `enabled: false`) has nothing here.
  const mineQuery = useGMProfileMineQuery(!!gmEntry);

  const eligible = !!account?.is_gm || !!account?.is_staff;
  if (!eligible) return null;

  if (!gmEntry) {
    return (
      <>
        <Plate className="p-3">
          <button
            type="button"
            data-testid="create-gm-profile"
            onClick={() => setCreateOpen(true)}
            className="flex h-full min-h-[9rem] w-full flex-col items-center justify-center gap-2 text-center"
          >
            <span className="theme-heading text-sm font-semibold [font-variant:small-caps]">
              Create GM Profile
            </span>
          </button>
        </Plate>
        <CreateGMCharacterDialog open={createOpen} onOpenChange={setCreateOpen} />
      </>
    );
  }

  const canEdit = mineQuery.data != null;

  return (
    <>
      <Plate
        className={cn('relative overflow-hidden p-3', isDocked && 'border-t-2 border-t-primary')}
      >
        <CountChip
          count={gmEntry.unread_narrative_count}
          label="tidings waiting"
          className="absolute right-2 top-2"
        />
        {canEdit && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Edit GM profile"
            data-testid="edit-gm-profile"
            className="absolute left-2 top-2 h-7 w-7 rounded-none"
            onClick={() => setEditOpen(true)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
        )}
        <button
          type="button"
          onClick={() => onSelect(gmEntry)}
          className="flex w-full flex-col items-center gap-2 text-center"
        >
          <Avatar className="h-20 w-20 rounded-none">
            <AvatarImage src={gmEntry.profile_picture_url ?? undefined} alt={gmEntry.name} />
            <AvatarFallback className="rounded-none text-lg">
              {getInitials(gmEntry.name)}
            </AvatarFallback>
          </Avatar>
          <span className="theme-heading text-sm font-semibold [font-variant:small-caps]">
            {gmEntry.name}{' '}
            <span className="font-body text-xs normal-case text-muted-foreground">(GM)</span>
          </span>
        </button>
        <PersonaTiles
          characterSheetId={gmEntry.character_id}
          activePersonaId={gmEntry.active_persona_id}
          className="mt-2 justify-center"
        />
        <Link
          to="/tables"
          className="mt-2 block text-center font-body text-xs text-muted-foreground underline"
        >
          Tables
        </Link>
      </Plate>
      {canEdit && <EditGMProfileDialog open={editOpen} onOpenChange={setEditOpen} />}
    </>
  );
}
