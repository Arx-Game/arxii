/**
 * PledgeCard (#4333) — a character's pledge on their sheet, in three labelled parts: the
 * pledge's staff-authored text, the favor target with progress and time left, and the
 * system-generated list of what has earned favor toward it, each credit with its calculation
 * at the character's earning rate. Ready to close, it offers the closing rite (a live scene is
 * started if none runs; no shrine is needed). Read by the owner and staff only.
 */

import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Entry, Subheading, Tag } from '@/character_sheets/components/sheet/primitives';
import { useClosePledge } from '../queries';
import { timeLeft } from '../pledgeText';
import { PLEDGE_STATE, type PledgeCard as PledgeCardData } from '../types';

const STATE_LABEL: Record<string, string> = {
  [PLEDGE_STATE.open]: 'Open',
  [PLEDGE_STATE.ready]: 'Ready to close',
  [PLEDGE_STATE.closed]: 'Closed',
  [PLEDGE_STATE.lapsed]: 'Lapsed',
};

interface PledgeCardProps {
  card: PledgeCardData;
  /** Set for the owner: the character the close is dispatched as. */
  characterId?: number | null;
}

export function PledgeCard({ card, characterId }: PledgeCardProps) {
  const close = useClosePledge(characterId ?? 0);
  const being = card.terms.being_name;
  const live = card.state === PLEDGE_STATE.open || card.state === PLEDGE_STATE.ready;

  function handleClose() {
    close.mutate(undefined, {
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
    <div className="refsheet-stack" data-testid="pledge-card">
      <Subheading>Pledge</Subheading>
      <Entry
        name={card.pledge.name}
        tags={
          <>
            <Tag>Pledge text · staff-authored</Tag>
            <Tag accent={card.state === PLEDGE_STATE.ready}>{STATE_LABEL[card.state]}</Tag>
          </>
        }
        gloss={card.pledge.description || undefined}
      >
        <div className="mt-2 space-y-2 font-sans text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Tag>Favor target · staff-authored</Tag>
            {live && (
              <span className="text-xs text-muted-foreground">{timeLeft(card.time_limit)}</span>
            )}
          </div>
          <div data-testid="pledge-progress">
            <b>
              {card.progress} of {card.target}
            </b>{' '}
            favor earned with {being} since pledging
          </div>
          <progress
            className="block h-2 w-full overflow-hidden rounded-full bg-muted [&::-moz-progress-bar]:bg-amber-600 [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-amber-600"
            max={Math.max(card.target, 1)}
            value={Math.min(card.progress, card.target)}
            aria-label={`${card.progress} of ${card.target} favor`}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Tag>What earns favor with {being} for you · system-generated</Tag>
            <span className="rounded-full border px-2 text-xs font-semibold">
              {card.terms.rate.total}%{card.terms.rate.chosen_bonus ? ' · Chosen' : ''}
            </span>
          </div>
          {card.credits.length === 0 ? (
            <p className="text-xs text-muted-foreground" data-testid="pledge-no-credits">
              Nothing yet.
            </p>
          ) : (
            <ul className="divide-y divide-dotted" data-testid="pledge-credits">
              {card.credits.map((credit) => (
                <li
                  key={credit.id}
                  className="flex flex-wrap justify-between gap-x-3 gap-y-0.5 py-1"
                >
                  <span>{credit.label}</span>
                  <span className="min-w-0 max-w-full text-left font-semibold tabular-nums text-amber-700 dark:text-amber-400 sm:text-right">
                    {credit.calculation}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {card.retry_available && (
            <p className="text-xs text-muted-foreground">
              Your first closing rite failed; one more try is left within the span.
            </p>
          )}
          {characterId != null && card.state === PLEDGE_STATE.ready && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={handleClose}
                disabled={close.isPending}
                data-testid="close-pledge-button"
              >
                Close the pledge with {card.pledge.closing_rite_name}
              </Button>
              <span className="text-xs text-muted-foreground">
                <b>Rule:</b> closing needs a live scene; no shrine is required. One is started if
                none is running.
              </span>
            </div>
          )}
        </div>
      </Entry>
    </div>
  );
}
