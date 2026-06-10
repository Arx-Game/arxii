/**
 * BeatCard — the CK2-event view of one mission's current beat (#885).
 *
 * Framing prose (the node's authored flavor text), then the LIVE options
 * as succinct buttons (the server already applied location ∧ visibility —
 * an empty list means "nothing you can do HERE; follow the compass").
 * Clicking resolves: the roll/result prose renders in place (it also
 * lands in the scroll as a STORY narrative block), then Continue moves
 * to the next beat or the epilogue.
 */
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useBeat, useResolveBeat } from '../queries';
import type { BeatOption, ResolvedBeat } from '../types';

interface BeatCardProps {
  instanceId: number;
  /** Stable identifier of the player's current room (refetch key). */
  roomKey: string;
}

export function BeatCard({ instanceId, roomKey }: BeatCardProps) {
  const { data: beat, isLoading } = useBeat(instanceId, roomKey);
  const resolve = useResolveBeat();
  const [result, setResult] = useState<ResolvedBeat | null>(null);

  if (result) {
    return (
      <div className="space-y-2 rounded border bg-card p-3" data-testid="beat-result">
        {result.outcome_name ? <Badge variant="outline">{result.outcome_name}</Badge> : null}
        <p className="whitespace-pre-wrap text-sm">{result.story_text}</p>
        {result.is_terminal ? (
          <p className="whitespace-pre-wrap text-sm italic text-muted-foreground">
            {result.epilogue || 'The story concludes.'}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setResult(null)}>
            Continue
          </Button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <div className="p-3 text-sm text-muted-foreground">…</div>;
  }
  if (!beat) {
    return (
      <div className="p-3 text-sm text-muted-foreground" data-testid="beat-concluded">
        This story has concluded — see your journal for how it ended.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded border bg-card p-3" data-testid="beat-card">
      {beat.flavor_text ? <p className="whitespace-pre-wrap text-sm">{beat.flavor_text}</p> : null}
      {beat.options.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-testid="beat-not-here">
          Nothing presents itself here — this story waits somewhere else.
        </p>
      ) : (
        <div className="space-y-1" data-testid="beat-options">
          {beat.options.map((option) => (
            <OptionButton
              key={`${option.option_id}-${option.approach_id ?? 'authored'}`}
              option={option}
              pending={resolve.isPending}
              onPick={() =>
                resolve.mutate(
                  {
                    instanceId,
                    option_id: option.option_id,
                    approach_id: option.approach_id,
                  },
                  { onSuccess: setResult }
                )
              }
            />
          ))}
        </div>
      )}
      {resolve.error ? (
        <p className="text-xs text-destructive" data-testid="beat-error">
          {resolve.error instanceof ApiValidationError
            ? flattenErrorMessage(resolve.error.fieldErrors)
            : resolve.error.message}
        </p>
      ) : null}
    </div>
  );
}

function OptionButton({
  option,
  pending,
  onPick,
}: {
  option: BeatOption;
  pending: boolean;
  onPick: () => void;
}) {
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-auto w-full justify-between whitespace-normal py-1.5 text-left"
      disabled={pending}
      onClick={onPick}
    >
      <span>{option.label}</span>
      {option.check_type_name ? (
        <span className="ml-2 shrink-0 text-xs text-muted-foreground">
          {option.check_type_name}
          {option.base_risk > 0 ? ` · risk ${option.base_risk}` : ''}
        </span>
      ) : null}
    </Button>
  );
}
