/**
 * "Your Characters" band (#3412 slice 2) — the Hall's portrait-forward roster
 * of the account's playable characters. Clicking a card sets the account's
 * durable server-side selection (`useSelectCharacterMutation`); the docked
 * card gets a primary top rule + a "Playing: …" meta line (PLACEHOLDER —
 * presence isn't wired yet, mirrors `SelectedCharacterChip`).
 * "Clear Active Character" lives once, bottom-right of the whole band —
 * disabled (not hidden) when nothing is docked, so the control stays
 * discoverable per the ruling.
 *
 * Selection is NOT presence (ruled): this band never starts/stops a `/game`
 * session — Enter-the-world stays the header chip's job.
 *
 * Degraded-state meta line (#3412 final review, IMPORTANT-1): a docked
 * character whose `lifecycle_state` is CAPTURED/DEAD/RETIRED/UNKNOWN used to
 * assert "Playing: Currently Offscreen" unconditionally — a factual
 * contradiction with `OffscreenActsPlate`'s death/captivity prose shown right
 * below it on the same screen. The meta line now branches the same way the
 * plate does (mirrors its `ALLOWED_LIFECYCLE_STATES` set: ALIVE and the
 * unwritten COMA member still read "Currently Offscreen"; everything else
 * gets a short PLACEHOLDER state label instead). "Clear Active Character"
 * and card selection stay unaffected — this is a display-only fix, same as
 * the plate's own gate/display split.
 */
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { CountChip, PersonaTiles, Plate, PlateHead } from '@/components/folio';
import { cn } from '@/lib/utils';
import { useSelectCharacterMutation } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { dockedStateLabel } from '@/roster/lifecycleDisplay';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { hydrateActiveCharacter } from '@/store/gameSlice';

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
  return (
    <Plate
      className={cn('relative overflow-hidden p-3', isDocked && 'border-t-2 border-t-primary')}
    >
      <CountChip
        count={entry.unread_narrative_count}
        label="tidings waiting"
        className="absolute right-2 top-2"
      />
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
        {/* PLACEHOLDER copy — presence state isn't wired yet, mirrors SelectedCharacterChip */}
        {isDocked && (
          <span className="font-body text-xs text-muted-foreground">
            Playing: {dockedStateLabel(entry.lifecycle_state)}
          </span>
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
  const activeEntryId = useAppSelector((state) => state.game.activeEntryId);
  const selectMutation = useSelectCharacterMutation();

  const handleSelect = (entry: MyRosterEntry) => {
    if (entry.id === activeEntryId) return;
    dispatch(hydrateActiveCharacter({ name: entry.name, entryId: entry.id }));
    selectMutation.mutate(entry.id);
  };

  const handleClear = () => {
    dispatch(hydrateActiveCharacter(null));
    selectMutation.mutate(null);
  };

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-3">
        Your Characters
      </PlateHead>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {characters.map((entry) => (
          <CharacterCard
            key={entry.id}
            entry={entry}
            isDocked={entry.id === activeEntryId}
            onSelect={handleSelect}
          />
        ))}
      </div>
      <div className="mt-3 flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-none"
          disabled={activeEntryId == null}
          onClick={handleClear}
        >
          Clear Active Character
        </Button>
      </div>
    </Plate>
  );
}
