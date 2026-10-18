/**
 * Powers on a created NPC (#4418, Screen 1b): the staff edit mode's own stats, skills
 * and grant-magic editors, run against the NPC's sheet (those endpoints are open to the
 * NPC's owner). They need the sheet, so they appear once the NPC exists.
 */

import { useQuery } from '@tanstack/react-query';

import {
  MagicEditor,
  SkillsEditor,
  StatsEditor,
} from '@/character_sheets/components/sheet/StaffRowsBand';
import type { Run } from '@/character_sheets/components/sheet/staffRowPrimitives';
import {
  useCharacterSheetQuery,
  useStaffOptions,
  useStaffRowMutation,
} from '@/character_sheets/queries';
import { fetchSheetIdForEntry } from './npcFormApi';

/** The sheet behind a created NPC (the same cache entry the portrait reads). */
function useNpcSheetId(entryId: number, enabled = true) {
  return useQuery({
    queryKey: ['roster-entry-sheet', entryId],
    queryFn: () => fetchSheetIdForEntry(entryId),
    enabled,
    staleTime: Infinity,
  });
}

export function NpcPowersPanel({ entryId }: { entryId: number }) {
  const { data: sheetId = 0 } = useNpcSheetId(entryId);
  const { data: sheet } = useCharacterSheetQuery(sheetId);
  const rows = sheet?.staff_edit?.rows;
  const { data: options } = useStaffOptions(sheetId, rows !== undefined);
  const mutation = useStaffRowMutation(sheetId);
  const run: Run = (request, onDone) => mutation.mutate(request, { onSuccess: () => onDone?.() });

  return (
    <section className="flex flex-col gap-3 border-t pt-4" aria-label="Powers">
      <h3 className="font-display text-base">Powers</h3>
      {!rows || !options ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="flex flex-col gap-4">
          {!rows.has_gift && <MagicEditor sheetId={sheetId} run={run} />}
          <StatsEditor rows={rows} options={options} run={run} />
          <SkillsEditor rows={rows} options={options} run={run} />
        </div>
      )}
    </section>
  );
}
