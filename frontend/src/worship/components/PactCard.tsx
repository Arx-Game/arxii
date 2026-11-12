/**
 * PactCard (#4341) — a character's pact with a being on her sheet: the favor earned this period
 * against the commitment with the time left, what earned it by source, the condition's current
 * stage and when the next begins, and the offer's promises. Her own player may renounce it. An
 * ended pact still easing out shows its stage and how fast it eases, with nothing to do.
 * Read by the owner and staff only (a pact with a secret faith is hers alone).
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Subheading } from '@/character_sheets/components/sheet/primitives';
import { useRenouncePact } from '../queries';
import { timeLeft } from '../pledgeText';
import type { PactCard as PactCardData } from '../types';

interface PactCardProps {
  card: PactCardData;
  /** Set for the owner: the character the renouncement is dispatched as. */
  characterId?: number | null;
}

export function PactCard({ card, characterId }: PactCardProps) {
  const renounce = useRenouncePact(characterId ?? 0);
  const [confirming, setConfirming] = useState(false);
  const being = card.being_name;
  const stageNumber = card.stages.findIndex((stage) => stage.name === card.stage_name) + 1;
  const nextStageNumber =
    card.next_stage_threshold == null
      ? 0
      : card.stages.findIndex((stage) => stage.threshold === card.next_stage_threshold) + 1;
  const stageLabel = stageNumber > 0 ? `${stageNumber}. ${card.stage_name}` : card.stage_name;

  function handleRenounce() {
    renounce.mutate(card.being_id, {
      onSuccess: (result) => {
        if (result.success === false) {
          toast.error(result.message);
          return;
        }
        toast.success(result.message);
      },
      onError: (error: Error) => toast.error(error.message),
    });
  }

  return (
    <div className="refsheet-stack" data-testid="pact-card">
      <Subheading>Pact: {being}</Subheading>
      <div className="space-y-2 font-sans text-sm">
        {card.is_active ? (
          <>
            <p data-testid="pact-progress">
              This period:{' '}
              <b>
                {card.earned} of {card.required}
              </b>{' '}
              favor earned{card.time_limit ? `, ${timeLeft(card.time_limit)}` : ''}.
            </p>
            <progress
              className="block h-2 w-full overflow-hidden rounded-full bg-muted [&::-moz-progress-bar]:bg-amber-600 [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-amber-600"
              max={Math.max(card.required, 1)}
              value={Math.min(card.earned, card.required)}
              aria-label={`${card.earned} of ${card.required} favor`}
            />
            {card.sources.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm" data-testid="pact-sources">
                  <thead>
                    <tr className="text-xs text-muted-foreground">
                      <th className="py-0.5 pr-2 font-normal">Source this period</th>
                      <th className="py-0.5 font-normal">Favor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {card.sources.map((source) => (
                      <tr key={source.label} className="border-t border-dotted align-top">
                        <td className="py-1 pr-2">{source.label}</td>
                        <td className="py-1 font-semibold tabular-nums text-amber-700 dark:text-amber-400">
                          +{source.favor}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p data-testid="pact-stage">
              Current stage: <b>{stageLabel}</b>. Severity {card.severity}
              {nextStageNumber > 0 &&
                `; stage ${nextStageNumber} begins at ${card.next_stage_threshold}`}
              .
            </p>
            {card.promises.map((promise, index) => (
              <p key={index} className="italic" data-testid="pact-card-promise">
                {promise}
              </p>
            ))}
            {characterId != null && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirming(true)}
                disabled={renounce.isPending}
                data-testid="renounce-pact-button"
              >
                Renounce
              </Button>
            )}
          </>
        ) : (
          <p data-testid="pact-ended">
            Ended. Current stage: <b>{stageLabel}</b>. {card.stage_name} eases by{' '}
            {card.severity_per_miss} each period until it is gone.
          </p>
        )}
      </div>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Renounce your pact with {being}?</AlertDialogTitle>
            <AlertDialogDescription>
              {card.stage_name} eases by {card.severity_per_miss} each period until it is gone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleRenounce} data-testid="confirm-renounce-pact">
              Renounce
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
