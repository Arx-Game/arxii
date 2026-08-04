/**
 * Maturation Point panel (#2756) — owner-only sheet section.
 *
 * Shows points earned by actually aging (milestones every 3rd matured year
 * from 21) and lets the owner spend them: +1 to a stat, capped per stage.
 * Reads GET /maturation/ and writes POST /spend-maturation-point/.
 */

import { Button } from '@/components/ui/button';
import { apiFetch } from '@/evennia_replacements/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface MaturationStat {
  trait_id: number;
  name: string;
  value: number;
  at_cap: boolean;
}

interface MaturationState {
  available_points: number;
  stat_cap: number | null;
  matured_years: number;
  next_milestone_year: number;
  stats: MaturationStat[];
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

  return (
    <section>
      <h3 className="text-xl font-semibold">Maturation</h3>
      <p className="text-sm text-muted-foreground">
        {data.available_points > 0
          ? `${data.available_points} point${data.available_points === 1 ? '' : 's'} earned by the years; spend them below.`
          : `No points waiting. The next milestone arrives at age ${data.next_milestone_year}.`}
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
