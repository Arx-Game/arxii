/**
 * Level Stat Point panel (#3001) — owner-only sheet section.
 *
 * Shows points earned by leveling (+1 per class level past the first) and
 * lets the owner spend them: +1 to a stat, capped per stage (the same
 * MaturationStatCap table the maturation panel binds to).
 * Reads GET /stat-points/ and writes POST /spend-stat-point/.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { SpendableStatList, type SpendableStat } from './SpendableStatList';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface StatPointState {
  available_points: number;
  stat_cap: number | null;
  level: number;
  stats: SpendableStat[];
}

async function fetchStatPoints(sheetId: number): Promise<StatPointState> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/stat-points/`);
  if (!res.ok) throw new Error('Failed to load stat point state');
  return (await res.json()) as StatPointState;
}

async function spendPoint(sheetId: number, traitId: number): Promise<StatPointState> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/spend-stat-point/`, {
    method: 'POST',
    body: JSON.stringify({ trait_id: traitId }),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail ?? 'Failed to spend stat point');
  }
  return (await res.json()) as StatPointState;
}

interface StatPointPanelProps {
  sheetId: number;
}

export function StatPointPanel({ sheetId }: StatPointPanelProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ['stat-points', sheetId],
    queryFn: () => fetchStatPoints(sheetId),
  });

  const spend = useMutation({
    mutationFn: (traitId: number) => spendPoint(sheetId, traitId),
    onSuccess: (state) => {
      setError(null);
      queryClient.setQueryData(['stat-points', sheetId], state);
      void queryClient.invalidateQueries({ queryKey: ['character-sheet', sheetId] });
    },
    onError: (err: Error) => setError(err.message),
  });

  if (!data) return null;

  const pointNoun = data.available_points === 1 ? 'point' : 'points';

  return (
    <section>
      <h3 className="text-xl font-semibold">Stat Points</h3>
      <p className="text-sm text-muted-foreground">
        {data.available_points > 0
          ? `${data.available_points} ${pointNoun} earned by your levels; spend them below.`
          : 'No stat points waiting. Each new level grants one.'}
      </p>
      {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
      {data.available_points > 0 && (
        <SpendableStatList
          stats={data.stats}
          statCap={data.stat_cap}
          disabled={spend.isPending}
          onSpend={(traitId) => spend.mutate(traitId)}
        />
      )}
    </section>
  );
}
