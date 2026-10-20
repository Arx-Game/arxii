/**
 * StewardAnswerPanel (#4333 slice 4): a closed pledge to a being this table
 * stewards, waiting on the table's GM.
 *
 * The GM picks one of the being's answers at or below the rolled tier, or (on
 * Success and Critical Success only) writes their own text and may attach one
 * clue the being's answers already link. Dismissing, or leaving it past the
 * window, sends an authored answer: the answer is never dropped.
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useDismissStewardPrompt, useSendStewardAnswer } from '../beingsQueries';
import { timeLeft } from '../stewardTime';
import type { StewardPrompt } from '../types';

const FREE_TEXT = 'free';

/** The queue pill: "Being answer: Wisket answers Tobiah Fenwright (Success). Answer it?" */
export function StewardPromptPill({
  prompt,
  onOpen,
  onDismissed,
}: {
  prompt: StewardPrompt;
  onOpen: () => void;
  onDismissed: (detail: string) => void;
}) {
  const dismiss = useDismissStewardPrompt();
  return (
    <div className="space-y-1">
      <div
        data-testid="steward-prompt-pill"
        className="flex flex-wrap items-center gap-2 rounded-full border border-primary/40 bg-primary/10 py-1 pl-3 pr-1 text-sm"
      >
        <span>
          &#10022; Being answer:{' '}
          <b>
            {prompt.being_name} answers {prompt.subject_name} ({prompt.outcome_tier_name}).
          </b>{' '}
          Answer it?
        </span>
        <span className="ml-auto flex gap-1">
          <Button type="button" size="sm" onClick={onOpen}>
            Open
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={dismiss.isPending}
            onClick={() =>
              dismiss.mutate(prompt.id, { onSuccess: (data) => onDismissed(data.detail) })
            }
          >
            &#10005; Dismiss
          </Button>
        </span>
      </div>
      {dismiss.error && (
        <p role="alert" className="text-xs text-destructive">
          {dismiss.error.message}
        </p>
      )}
    </div>
  );
}

/** The highest authored answer, else free text where the tier allows it. */
function initialChoice(prompt: StewardPrompt): string {
  if (prompt.options.length) return String(prompt.options[0].id);
  return prompt.may_write_free_text ? FREE_TEXT : '';
}

export function StewardAnswerPanel({
  prompt,
  onSent,
}: {
  prompt: StewardPrompt;
  onSent: (detail: string) => void;
}) {
  const send = useSendStewardAnswer();
  const [choice, setChoice] = useState<string>(() => initialChoice(prompt));
  const [text, setText] = useState('');
  const [clue, setClue] = useState('');
  const writing = choice === FREE_TEXT;
  const ready = writing ? text.trim() !== '' : choice !== '';

  function submit() {
    const body = writing
      ? { text: text.trim(), clue: clue ? Number(clue) : null }
      : { answer: Number(choice), text: '' };
    send.mutate({ promptId: prompt.id, body }, { onSuccess: (data) => onSent(data.detail) });
  }

  return (
    <section
      aria-label={`${prompt.being_name} answers ${prompt.subject_name}`}
      className="space-y-3 rounded-lg border bg-background p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          {prompt.being_name} answers {prompt.subject_name}
        </h3>
        <span className="text-xs text-muted-foreground">
          <b>Rule:</b> dismissing or ignoring this prompt sends an authored answer after the window
          ({timeLeft(prompt.window_ends_at)} left); the answer is never dropped.
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Pledge:</span>
        <span>{prompt.pledge_name}</span>
        <span className="text-muted-foreground">· Tier:</span>
        <Badge>{prompt.outcome_tier_name}</Badge>
      </div>
      {prompt.sacrificed.length > 0 && (
        <div className="space-y-2" data-testid="steward-sacrificed">
          <p className="text-sm text-muted-foreground">Sacrificed toward this pledge:</p>
          {prompt.sacrificed.map((item, index) => (
            <div key={index} className="rounded-md border p-2 text-sm">
              <p className="font-medium">
                {item.offered_by_name} sacrifices {item.item_name}.
                {item.facet_name && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    {item.facet_name}, favored
                  </span>
                )}
              </p>
              {item.signals.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No meaning points: given up, no roll, no favor.
                </p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="text-left text-muted-foreground">
                    <tr>
                      <th>Signal</th>
                      <th>Detail</th>
                      <th>Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.signals.map((signal, signalIndex) => (
                      <tr key={signalIndex}>
                        <td>{signal.kind_name}</td>
                        <td>{signal.detail}</td>
                        <td className="tabular-nums">{signal.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {item.signals.length > 0 && (
                <p className="text-xs text-muted-foreground" data-testid="sacrifice-odds-note">
                  {item.points} points
                  {item.effective_points !== item.points
                    ? `, ${item.facet_name} favored = ${item.effective_points} points`
                    : ''}
                  {item.counted && item.difficulty_points != null
                    ? `, eased ${item.ease_points}, difficulty ${item.difficulty_points}.`
                    : '.'}
                  {item.counted && item.odds
                    ? ` For a ${item.odds.reference_rank_name} roller: ${item.odds.lines
                        .map((line) => `${line.percent}% ${line.outcome_name}`)
                        .join(', ')}.`
                    : ''}
                  {item.counted
                    ? ` This roll: ${item.outcome_name || 'none'}.`
                    : " Past the week's limit: given up for nothing."}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      {prompt.prayer_text && (
        <p className="text-sm">
          <span className="text-muted-foreground">Prayer:</span> {prompt.prayer_text}
        </p>
      )}
      <fieldset className="space-y-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">
          {prompt.being_name}&apos;s answers at {prompt.outcome_tier_name} and below
        </legend>
        {prompt.options.length === 0 && (
          <p className="text-sm text-muted-foreground">No answers written at this tier or below.</p>
        )}
        {prompt.options.map((option) => (
          <label key={option.id} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name={`steward-choice-${prompt.id}`}
              value={String(option.id)}
              checked={choice === String(option.id)}
              onChange={() => setChoice(String(option.id))}
              className="mt-1"
            />
            <Badge variant="outline">{option.outcome_tier_name}</Badge>
            <span>{option.answer_text || option.delay_text}</span>
          </label>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name={`steward-choice-${prompt.id}`}
            value={FREE_TEXT}
            checked={writing}
            disabled={!prompt.may_write_free_text}
            onChange={() => setChoice(FREE_TEXT)}
          />
          <b>Write free text</b>
          <Badge variant="outline">steward only · success tiers only</Badge>
        </label>
      </fieldset>
      {writing && (
        <Textarea
          aria-label="Your answer"
          className="min-h-[80px]"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        {writing && (
          <select
            aria-label={`Attach a clue from ${prompt.being_name}'s catalogue`}
            className="h-9 min-w-[220px] flex-1 rounded-md border border-input bg-transparent px-3 text-sm"
            value={clue}
            onChange={(e) => setClue(e.target.value)}
          >
            <option value="">
              {prompt.catalogue_clues.length
                ? `Attach a clue from ${prompt.being_name}'s catalogue (optional)`
                : 'No clues linked from this being’s answers'}
            </option>
            {prompt.catalogue_clues.map((row) => (
              <option key={row.id} value={String(row.id)}>
                {row.name}
              </option>
            ))}
          </select>
        )}
        <Button type="button" disabled={!ready || send.isPending} onClick={submit}>
          Send as {prompt.being_name}
        </Button>
      </div>
      {send.error && (
        <p role="alert" className="text-sm text-destructive">
          {send.error.message}
        </p>
      )}
    </section>
  );
}
