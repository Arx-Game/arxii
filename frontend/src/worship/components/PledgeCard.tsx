/**
 * PledgeCard (#4333) — a character's pledge on their sheet, in three labelled parts: the
 * pledge's staff-authored text, the favor target with progress and time left, and the
 * system-generated list of what has earned favor toward it, each credit with its calculation
 * at the character's earning rate. Ready to close, it offers the closing rite (a live scene is
 * started if none runs; no shrine is needed). Read by the owner and staff only.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Entry, Subheading, Tag } from '@/character_sheets/components/sheet/primitives';
import { useInventory } from '@/inventory/hooks/useInventory';
import { useClosePledge } from '../queries';
import { timeLeft } from '../pledgeText';
import {
  PACT_COMMITMENT_KIND,
  PLEDGE_STATE,
  type PactOfferSummary,
  type PledgeCard as PledgeCardData,
} from '../types';

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

  const [giveOpen, setGiveOpen] = useState(false);
  const [chosen, setChosen] = useState<number[]>([]);
  const { data: carried } = useInventory(giveOpen ? (characterId ?? undefined) : undefined);

  function toggle(id: number) {
    setChosen((current) =>
      current.includes(id) ? current.filter((row) => row !== id) : [...current, id]
    );
  }

  const offer = card.pledge.pact_offer;

  function handleClose(acceptPact: boolean) {
    close.mutate(acceptPact ? { itemIds: chosen, acceptPact: true } : { itemIds: chosen }, {
      onSuccess: (result) => {
        if (result.success === false) {
          toast.error(result.message);
          return;
        }
        toast.success(result.message);
        setChosen([]);
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
          {card.requests.length > 0 && (
            <div className="space-y-1" data-testid="pledge-requests">
              <Tag>{being} asks for · staff-authored</Tag>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-xs text-muted-foreground">
                      <th className="py-0.5 pr-2 font-normal">Asked for</th>
                      <th className="py-0.5 pr-2 font-normal">Hint</th>
                      <th className="py-0.5 pr-2 font-normal">Given</th>
                      <th className="py-0.5 font-normal">Points each</th>
                    </tr>
                  </thead>
                  <tbody>
                    {card.requests.map((request) => (
                      <tr
                        key={request.id}
                        className="border-t border-dotted align-top"
                        data-testid="pledge-request"
                      >
                        <td className="py-1 pr-2">
                          {request.asked_for}
                          {request.where === 'closing rite' && (
                            <span className="block text-xs text-muted-foreground">
                              at the closing rite
                            </span>
                          )}
                        </td>
                        <td className="py-1 pr-2">{request.hint}</td>
                        <td className="py-1 pr-2 tabular-nums">
                          {request.given} of {request.quantity}
                        </td>
                        <td className="py-1 tabular-nums">{request.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground">
                Give a requested item up at the shrine and its points ease that item&apos;s own
                sacrifice roll, which then cannot come out as a Critical Failure. Given up during
                the pledge&apos;s rite, the points ease the rite&apos;s roll instead.
              </p>
            </div>
          )}
          {card.retry_available && (
            <p className="text-xs text-muted-foreground">
              Your first closing rite failed; one more try is left within the span.
            </p>
          )}
          {live && offer && <PactOffer offer={offer} />}
          {characterId != null && card.state === PLEDGE_STATE.ready && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant={offer ? 'outline' : 'default'}
                  className="h-auto min-h-9 max-w-full whitespace-normal text-left"
                  onClick={() => handleClose(false)}
                  disabled={close.isPending}
                  data-testid="close-pledge-button"
                >
                  {offer
                    ? 'Perform the closing rite'
                    : `Close the pledge with ${card.pledge.closing_rite_name}`}
                </Button>
                {offer && (
                  <Button
                    size="sm"
                    className="h-auto min-h-9 max-w-full whitespace-normal text-left"
                    onClick={() => handleClose(true)}
                    disabled={close.isPending}
                    data-testid="close-accept-pact-button"
                  >
                    Perform the closing rite and accept the pact
                  </Button>
                )}
                <span className="text-xs text-muted-foreground">
                  <b>Rule:</b> closing needs a live scene; no shrine is required. One is started if
                  none is running.
                </span>
              </div>
              {offer && (
                <p className="text-xs text-muted-foreground" data-testid="pact-accept-note">
                  The pact is signed only if you chose to accept and the rite resolves the pledge at
                  Success or better. Closing without accepting leaves no pact and nothing waiting;
                  the pledge pays its reward and answer either way.
                </p>
              )}
              <details
                onToggle={(event) => setGiveOpen((event.currentTarget as HTMLDetailsElement).open)}
                data-testid="close-give-items"
              >
                <summary className="cursor-pointer text-xs text-muted-foreground">
                  Give items up during the rite
                </summary>
                <p className="mt-1 text-xs text-muted-foreground">
                  What an item means to you eases the rite&apos;s roll, and an item the pledge asked
                  for eases it too. Items given up leave play; their design is kept.
                </p>
                <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto">
                  {(carried ?? []).map((item) => (
                    <li key={item.id}>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={chosen.includes(item.id)}
                          onChange={() => toggle(item.id)}
                        />
                        <span>{item.display_name}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </div>
      </Entry>
    </div>
  );
}

function weeks(count: number): string {
  return `${count} game week${count === 1 ? '' : 's'}`;
}

/** The pact a pledge offers at its close: the staff-authored offer, then the system summary
 * built from the offer's rows and its condition's stages, best to worst. */
function PactOffer({ offer }: { offer: PactOfferSummary }) {
  const being = offer.being_name;
  const favor = offer.commitments.filter((row) => row.kind === PACT_COMMITMENT_KIND.favorEarned);
  return (
    <div className="space-y-2" data-testid="pact-offer">
      <p>
        <b>Offered at the close:</b> a pact with {being}.
      </p>
      <p className="italic">{offer.offer_text}</p>
      <p className="text-xs text-muted-foreground">
        System summary, built from the offer&apos;s rows:
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <tbody>
            <tr className="border-t border-dotted align-top">
              <th className="py-1 pr-2 font-semibold">Being</th>
              <td className="py-1">{being}</td>
            </tr>
            {favor.map((row, index) => (
              <tr
                key={`favor-${index}`}
                className="border-t border-dotted align-top"
                data-testid="pact-commitment"
              >
                <th className="py-1 pr-2 font-semibold">You commit to</th>
                <td className="py-1">
                  Earn <b>{row.amount} favor</b> with {being} every{' '}
                  <b>{weeks(offer.period_weeks)}</b>. Favor comes from deeds it values, sacrifices
                  at its shrine and its rites. Nothing is spent.
                </td>
              </tr>
            ))}
            {offer.promises.map((promise, index) => (
              <tr
                key={`promise-${index}`}
                className="border-t border-dotted align-top"
                data-testid="pact-promise"
              >
                <th className="py-1 pr-2 font-semibold">Promise (not checked by the game)</th>
                <td className="py-1">{promise}</td>
              </tr>
            ))}
            <tr className="border-t border-dotted align-top">
              <th className="py-1 pr-2 font-semibold">What you gain</th>
              <td className="py-1">
                {being} becomes your patron: its bond ultimate can be among your choices at Audere
                (the peak moment in a fight where ultimates can be used), and you can choose {being}{' '}
                on a technique that brings a being into a fight. Plus your current stage&apos;s
                effects, below.
              </td>
            </tr>
            <tr className="border-t border-dotted align-top">
              <th className="py-1 pr-2 font-semibold">If you fall short</th>
              <td className="py-1">
                The stages below; every change of stage rolls its resist check first.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <ol className="flex flex-col gap-1 sm:flex-row" data-testid="pact-stages">
        {offer.stages.map((stage, index) => (
          <li
            key={stage.name}
            className={`flex-1 rounded-md border p-1.5 text-xs ${
              index === 0 ? 'border-2 border-amber-600 bg-amber-50 dark:bg-amber-950/40' : ''
            }`}
            data-testid="pact-stage"
          >
            <b>
              {index + 1}. {stage.name}
            </b>
            {[...offer.condition_effects, ...stage.effects].map((line, lineIndex) => (
              <span key={lineIndex} className="block">
                {line}
              </span>
            ))}
            {stage.is_last && (
              <span className="block">The pact ends, if its resist check fails</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
