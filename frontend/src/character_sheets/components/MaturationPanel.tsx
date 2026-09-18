/**
 * Maturation Point panel (#2756) — owner-only sheet section.
 *
 * Shows points earned by actually aging (milestones every 3rd matured year
 * from 21) and lets the owner spend them: +1 to a stat, capped per stage.
 * Reads GET /maturation/ and writes POST /spend-maturation-point/.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { SpendableStatList, type SpendableStat } from './SpendableStatList';
import { Subheading } from '@/character_sheets/components/sheet/primitives';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface MaturationState {
  available_points: number;
  stat_cap: number | null;
  matured_years: number;
  next_milestone_year: number | null;
  stats: SpendableStat[];
}

async function fetchMaturation(sheetId: number): Promise<MaturationState> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/maturation/`);
  if (!res.ok) throw new Error('Failed to load maturation state');
  return (await res.json()) as MaturationState;
}

async function spendPoint(sheetId: number, traitId: number): Promise<MaturationState> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/spend-maturation-point/`, {
    method: 'POST',
    body: JSON.stringify({ trait_id: traitId }),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail ?? 'Failed to spend maturation point');
  }
  return (await res.json()) as MaturationState;
}

interface MaturationPanelProps {
  sheetId: number;
}

/**
 * The idle line: the next milestone, or none once the last (75) is behind the character
 * (#3635). An absent year is treated the same as an explicit null — an older payload, or
 * one that simply did not carry the field, printed "at age undefined" at the player
 * (found while capturing #3898's evidence, once Growth became a page people read).
 */
function waitingLine(nextMilestoneYear: number | null | undefined): string {
  if (nextMilestoneYear === null || nextMilestoneYear === undefined) {
    return 'No points waiting, and no milestones remain.';
  }
  return `No points waiting. The next milestone arrives at age ${nextMilestoneYear}.`;
}

export function MaturationPanel({ sheetId }: MaturationPanelProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ['maturation', sheetId],
    queryFn: () => fetchMaturation(sheetId),
  });

  const spend = useMutation({
    mutationFn: (traitId: number) => spendPoint(sheetId, traitId),
    onSuccess: (state) => {
      setError(null);
      queryClient.setQueryData(['maturation', sheetId], state);
      void queryClient.invalidateQueries({ queryKey: ['character-sheet', sheetId] });
    },
    onError: (err: Error) => setError(err.message),
  });

  if (!data) return null;

  const pointNoun = data.available_points === 1 ? 'point' : 'points';

  return (
    <div className="refsheet-stack">
      <Subheading>Maturation</Subheading>
      <p className="refsheet-ledger">
        {data.available_points > 0
          ? `${data.available_points} ${pointNoun} earned by the years; spend them below.`
          : waitingLine(data.next_milestone_year)}
      </p>
      {error && (
        <p className="refsheet-note" style={{ color: 'hsl(var(--destructive))' }}>
          {error}
        </p>
      )}
      {data.available_points > 0 && (
        <SpendableStatList
          stats={data.stats}
          statCap={data.stat_cap}
          disabled={spend.isPending}
          onSpend={(traitId) => spend.mutate(traitId)}
        />
      )}
    </div>
  );
}
