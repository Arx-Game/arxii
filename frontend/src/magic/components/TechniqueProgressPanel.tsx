/**
 * TechniqueProgressPanel (#2739 Task 3) — player-facing training-meter list.
 *
 * Lists the owning character's in-progress `TechniqueProgress` meters
 * (technique name, progress bar/fraction, teacher-or-self-study, weekly
 * remaining) with a Train button (+ optional AP-to-invest input) per row.
 * Mounted below MotifStylePanel in SpellbookTab, own-view only — mirrors its
 * query/mutation idiom (#2030).
 *
 * Wire contract: TechniqueProgressViewSet
 * (src/world/magic/views_technique_progress.py) — list/train dispatch
 * TrainTechniqueAction (src/actions/definitions/technique_training.py). 400s
 * (no meter, weekly cap hit, can't afford the AP, stale meter) carry a
 * `{detail}` string surfaced verbatim below the row that triggered them.
 */

import { useState, type FormEvent } from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useTechniqueProgress, useTrainTechnique } from '@/magic/queries';
import type { TrainTechniqueResult } from '@/magic/types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterSheetId: number;
}

export function TechniqueProgressPanel({ characterSheetId }: Props) {
  const { data: meters, isLoading } = useTechniqueProgress(characterSheetId);
  const train = useTrainTechnique(characterSheetId);

  const [apInputs, setApInputs] = useState<Record<number, string>>({});
  const [lastResult, setLastResult] = useState<Record<number, TrainTechniqueResult>>({});
  const [failedTechniqueId, setFailedTechniqueId] = useState<number | null>(null);

  const rows = meters ?? [];

  function handleTrain(event: FormEvent, techniqueId: number) {
    event.preventDefault();
    const raw = apInputs[techniqueId];
    const parsed = raw ? Number(raw) : undefined;
    const body =
      parsed && Number.isInteger(parsed) && parsed > 0 ? { ap_to_invest: parsed } : undefined;
    setFailedTechniqueId(null);
    train.mutate(
      { techniqueId, body },
      {
        onSuccess: (data) => {
          setLastResult((prev) => ({ ...prev, [techniqueId]: data }));
        },
        onError: () => {
          setFailedTechniqueId(techniqueId);
        },
      }
    );
  }

  const renderRows = () => {
    if (isLoading) {
      return <p className="text-sm text-muted-foreground">Loading training meters…</p>;
    }
    if (rows.length === 0) {
      return (
        <p className="text-sm text-muted-foreground" data-testid="technique-progress-empty">
          Nothing in training right now.
        </p>
      );
    }
    return (
      <div className="space-y-3" data-testid="technique-progress-list">
        {rows.map((meter) => {
          const pct =
            meter.total_required > 0
              ? Math.min(100, Math.round((meter.points_accumulated / meter.total_required) * 100))
              : 0;
          const result = lastResult[meter.technique_id];

          return (
            <form
              key={meter.id}
              onSubmit={(event) => handleTrain(event, meter.technique_id)}
              className="space-y-2 rounded-md border p-3"
              data-testid="technique-progress-row"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{meter.technique_name}</span>
                <Badge variant="outline">
                  {meter.teacher_name ? `Taught by ${meter.teacher_name}` : 'Self-study'}
                </Badge>
              </div>
              <Progress value={pct} data-testid={`technique-progress-bar-${meter.technique_id}`} />
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                <span>
                  {meter.points_accumulated}/{meter.total_required} — {meter.source_label}
                </span>
                {meter.weekly_remaining !== null && (
                  <span>{meter.weekly_remaining} AP left this week</span>
                )}
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <label
                  className="flex flex-col gap-1 text-xs text-muted-foreground"
                  htmlFor={`technique-progress-ap-${meter.technique_id}`}
                >
                  AP to invest (optional)
                  <input
                    id={`technique-progress-ap-${meter.technique_id}`}
                    data-testid={`technique-progress-ap-input-${meter.technique_id}`}
                    type="number"
                    min={1}
                    step={1}
                    className="h-9 w-24 rounded-md border border-input bg-transparent px-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={apInputs[meter.technique_id] ?? ''}
                    onChange={(event) =>
                      setApInputs((prev) => ({
                        ...prev,
                        [meter.technique_id]: event.target.value,
                      }))
                    }
                  />
                </label>
                <Button
                  type="submit"
                  size="sm"
                  disabled={train.isPending}
                  data-testid={`technique-progress-train-${meter.technique_id}`}
                >
                  Train
                </Button>
              </div>
              {result && (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid={`technique-progress-result-${meter.technique_id}`}
                >
                  {result.technique_acquired
                    ? `Your training pays off — you've learned ${meter.technique_name}!`
                    : `${result.outcome_name}: ${result.points_after}/${result.total_required}.`}
                </p>
              )}
              {train.isError && failedTechniqueId === meter.technique_id && (
                <p
                  role="alert"
                  data-testid={`technique-progress-error-${meter.technique_id}`}
                  className="text-sm font-medium text-red-500"
                >
                  {train.error?.message}
                </p>
              )}
            </form>
          );
        })}
      </div>
    );
  };

  return (
    <Card data-testid="technique-progress-panel">
      <CardHeader>
        <CardTitle className="text-base">Training</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">{renderRows()}</CardContent>
    </Card>
  );
}
