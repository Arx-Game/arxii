/**
 * MagicProgressionPage — landing page for the player's magic progression surface.
 *
 * Shows every progression stage the active persona has access to, rendered
 * as StageSection cards. The active character is the one currently selected
 * in the game UI (state.game.active from Redux) resolved against the user's
 * roster entries — never inferred from "the first row of some unordered list."
 */

import { useMemo } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useMagicProgression } from '../magicProgressionQueries';
import { StageSection } from '../components/progression/StageSection';

export function MagicProgressionPage() {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myEntries = [] } = useMyRosterEntriesQuery();

  // Resolve active character to a character_sheet pk. CharacterSheet
  // shares its pk with the underlying ObjectDB (character_id) via the
  // OneToOneField(primary_key=True).
  const characterSheetId = useMemo(() => {
    const entry = myEntries.find((e) => e.name === activeCharacterName);
    return entry?.character_id ?? undefined;
  }, [myEntries, activeCharacterName]);

  const { data, isLoading, isError, error } = useMagicProgression(characterSheetId);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">Magic Progression</h1>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        <h1 className="text-2xl font-semibold">Magic Progression</h1>
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load magic progression.'}
        </p>
      </div>
    );
  }

  const stages = data?.stages ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Magic Progression</h1>
      {stages.map((stage) => (
        <StageSection key={stage.stage} stage={stage} />
      ))}
    </div>
  );
}
