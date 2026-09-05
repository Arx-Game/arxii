/**
 * MagicProgressionPage — landing page for the player's magic progression surface.
 *
 * Shows every progression stage the active persona has access to, rendered
 * as StageSection cards. The active character is this tab's browsing identity
 * (#3479) — never inferred from "the first row of some unordered list."
 */

import { Skeleton } from '@/components/ui/skeleton';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { useMagicProgression } from '../magicProgressionQueries';
import { PathIntentCard } from '../components/PathIntentCard';
import { StageSection } from '../components/progression/StageSection';

export function MagicProgressionPage() {
  // Resolve the browsing character to a character_sheet pk. CharacterSheet
  // shares its pk with the underlying ObjectDB (character_id) via the
  // OneToOneField(primary_key=True).
  const { entry } = useBrowsingIdentity();
  const characterSheetId = entry?.character_id ?? undefined;

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
      <PathIntentCard characterId={characterSheetId ?? 0} />
      {stages.map((stage) => (
        <StageSection key={stage.stage} stage={stage} />
      ))}
    </div>
  );
}
