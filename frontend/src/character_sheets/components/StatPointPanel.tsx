/**
 * Level Stat Point panel (#3001) — owner-only sheet section.
 *
 * Shows points earned by leveling (+1 per class level past the first) and
 * lets the owner spend them: +1 to a stat, capped per stage (the same
 * MaturationStatCap table the maturation panel binds to).
 * Reads GET /stat-points/ and writes POST /spend-stat-point/.
 */

import { Button } from '@/components/ui/button';
import { apiFetch } from '@/evennia_replacements/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface StatPointStat {
  trait_id: number;
  name: string;
  value: number;
  at_cap: boolean;
}

interface StatPointState {
  available_points: number;
  stat_cap: number | null;
  level: number;
  stats: StatPointStat[];
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

  return (
    <section>
      <h3 className="text-xl font-semibold">Stat Points</h3>
      <p className="text-sm text-muted-foreground">
        {data.available_points > 0
          ? `${data.available_points} point${data.available_points === 1 ? '' : 's'} earned by your levels; spend them below.`
          : 'No stat points waiting. Each new level grants one.'}
      </p>
      {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
      {data.available_points > 0 && (
        <ul className="mt-2 space-y-1">
          {data.stats.map((stat) => (
            <li key={stat.trait_id} className="flex items-center justify-between gap-2">
              <span className="capitalize">
                {stat.name} ({stat.value}
                {data.stat_cap !== null && ` / ${data.stat_cap}`})
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={stat.at_cap || spend.isPending}
                onClick={() => spend.mutate(stat.trait_id)}
              >
                +1
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
