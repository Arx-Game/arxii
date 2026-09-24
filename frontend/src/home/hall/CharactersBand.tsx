/**
 * "Your Characters" band (#3412 slice 2) — the Hall's portrait-forward roster
 * of the account's playable characters. Clicking a card sets the account's
 * durable server-side selection (`useSelectCharacterMutation`); the docked
 * card gets a primary top rule + a presence meta line that reads the
 * character's live session from the store (#3859: "In the world" while the
 * socket is open, else `dockedStateLabel`, the same fact and the same helper
 * `SelectedCharacterChip` uses). "Clear Active Character" lives once,
 * bottom-right of the whole band — disabled (not hidden) when nothing is
 * docked, so the control stays discoverable per the ruling.
 *
 * Selection is NOT presence (ruled): this band never starts/stops a `/game`
 * session — Enter-the-world and Leave-the-world stay the header chip's job.
 *
 * Degraded-state meta line (#3412 final review, IMPORTANT-1): a docked
 * character whose `lifecycle_state` is CAPTURED/DEAD/RETIRED/UNKNOWN used to
 * assert "Playing: Currently Offscreen" unconditionally — a factual
 * contradiction with `OffscreenActsPlate`'s death/captivity prose shown right
 * below it on the same screen. The meta line branches the same way the plate
 * does (`ALLOWED_LIFECYCLE_STATES`: ALIVE and the unwritten COMA member read
 * "Not in the world" when no session is live; everything else gets a short
 * PLACEHOLDER state label instead). "Clear Active Character" and card
 * selection stay unaffected — this is a display-only fix, same as the plate's
 * own gate/display split.
 *
 * The Hall's GM slot (#3478 task 5): `characters` (from
 * `MyRosterEntry.character_type`, Task 3) can carry at most one non-"PC"
 * entry per account — the account's own GM or Staff character. That entry
 * is pulled out of the PC grid and handed to `GMSlot`, an extra grid tile
 * rendered only for `is_gm`/`is_staff` accounts (never for a plain player,
 * even if `characters` somehow carried a GM entry that isn't theirs — it
 * can't, `mine` is account-scoped, but the guard is cheap insurance).
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { CountChip, PersonaTiles, Plate, PlateHead } from '@/components/folio';
import { cn } from '@/lib/utils';
import { useSelectCharacterMutation } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { dockedStateLabel } from '@/roster/lifecycleDisplay';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { useAccount, useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  hydrateActiveCharacter,
  setBrowsingIdentity,
  clearBrowsingIdentity,
} from '@/store/gameSlice';
import { writeTabIdentity, clearTabIdentity } from '@/store/browsingIdentity';
import { CharacterActionsMenu } from './CharacterActionsMenu';
import { GMSlot } from './GMSlot';
import { NewCharacterTile } from './NewCharacterTile';

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

interface CharacterCardProps {
  entry: MyRosterEntry;
  isDocked: boolean;
  onSelect: (entry: MyRosterEntry) => void;
}

function CharacterCard({ entry, isDocked, onSelect }: CharacterCardProps) {
  // #3859: the meta line states presence from the store, the same fact the
  // header chip reads. Sockets survive navigation (ADR-0295), so a docked
  // character can be live in the world while the player reads this page.
  const live = useAppSelector((state) => Boolean(state.game.sessions[entry.name]?.isConnected));
  return (
    <Plate
      className={cn('relative overflow-hidden p-3', isDocked && 'border-t-2 border-t-primary')}
    >
      <CountChip
        count={entry.unread_narrative_count}
        label="tidings waiting"
        className="absolute right-2 top-2"
      />
      <CharacterActionsMenu entry={entry} />
      <button
        type="button"
        onClick={() => onSelect(entry)}
        className="flex w-full flex-col items-center gap-2 text-center"
      >
        <Avatar className="h-20 w-20 rounded-none">
          <AvatarImage src={entry.profile_picture_url ?? undefined} alt={entry.name} />
          <AvatarFallback className="rounded-none text-lg">
            {getInitials(entry.name)}
          </AvatarFallback>
        </Avatar>
        <span className="theme-heading text-sm font-semibold [font-variant:small-caps]">
          {entry.name}
        </span>
        {isDocked && (
          <span className="font-body text-xs text-muted-foreground">
            {live ? 'In the world' : dockedStateLabel(entry.lifecycle_state)}
          </span>
        )}
        {entry.activity_state === 'FROZEN' && (
          <span className="font-body text-xs text-muted-foreground">Frozen</span>
        )}
      </button>
      <PersonaTiles
        characterSheetId={entry.character_id}
        activePersonaId={entry.active_persona_id}
        className="mt-2 justify-center"
      />
    </Plate>
  );
}

export function CharactersBand({ characters }: { characters: MyRosterEntry[] }) {
  const dispatch = useAppDispatch();
  const account = useAccount();
  const { entryId } = useBrowsingIdentity();
  const selectMutation = useSelectCharacterMutation();

  const handleSelect = (entry: MyRosterEntry) => {
    if (entry.id === entryId) return;
    // Write this tab's own browsing identity FIRST (#3479) so the picking
    // tab's UI (this docked highlight, every ambient page reading
    // useBrowsingIdentity) updates immediately: it must not wait on the
    // select mutation's round trip or the account refetch it triggers.
    writeTabIdentity(entry.id);
    dispatch(setBrowsingIdentity(entry.id));
    dispatch(hydrateActiveCharacter({ name: entry.name, entryId: entry.id }));
    selectMutation.mutate(entry.id);
  };

  const handleClear = () => {
    clearTabIdentity();
    dispatch(clearBrowsingIdentity());
    dispatch(hydrateActiveCharacter(null));
    selectMutation.mutate(null);
  };

  const pcs = characters.filter((entry) => entry.character_type === 'PC');
  const gmEntry = characters.find((entry) => entry.character_type !== 'PC');
  const showGMSlot = !!account?.is_gm || !!account?.is_staff;

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-3">
        Your Characters
      </PlateHead>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {pcs.map((entry) => (
          <CharacterCard
            key={entry.id}
            entry={entry}
            isDocked={entry.id === entryId}
            onSelect={handleSelect}
          />
        ))}
        {showGMSlot && (
          <GMSlot
            gmEntry={gmEntry}
            isDocked={gmEntry != null && gmEntry.id === entryId}
            onSelect={handleSelect}
          />
        )}
        <NewCharacterTile slots={account?.character_slots} characters={pcs} />
      </div>
      <div className="mt-3 flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-none"
          disabled={entryId == null}
          onClick={handleClear}
        >
          Clear Active Character
        </Button>
      </div>
    </Plate>
  );
}
