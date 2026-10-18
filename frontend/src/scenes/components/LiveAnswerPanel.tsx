/**
 * LiveAnswerPanel (#4333 slice 5, walkthrough D): a rite performed in the GM's
 * scene, waiting on the GM.
 *
 * Lists the being's answers at or below the rolled tier and its miracles. The
 * GM sends one answer, or one miracle, or sends nothing. The edit control (the
 * answer's main text) shows only for a GM level that may adapt answers; nobody
 * edits an answer's clue, cost or follow-up. A miracle that cannot be performed
 * is greyed with its reason.
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { useDismissLivePrompt, useLivePrompt, useSendLiveAnswer } from '../liveAnswerQueries';

const MIRACLE = 'miracle';

export function LiveAnswerPanel({
  promptId,
  sceneId,
  onDone,
}: {
  promptId: number;
  sceneId: string;
  onDone: () => void;
}) {
  const { data: panel, isLoading, error } = useLivePrompt(promptId, true);
  const send = useSendLiveAnswer(sceneId);
  const dismiss = useDismissLivePrompt(sceneId);
  const [choice, setChoice] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading the rite…</p>;
  if (error || !panel) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error?.message ?? 'The rite could not be loaded.'}
      </p>
    );
  }

  const selected = choice ?? (panel.answers.length ? `answer-${panel.answers[0].id}` : null);
  const selectedAnswer = panel.answers.find((row) => selected === `answer-${row.id}`);
  const selectedMiracle = panel.miracles.find(
    (row) => selected === `${MIRACLE}-${row.id}` && !row.reason
  );
  const blocked = panel.limit_reason !== '';
  const ready = !blocked && (selectedAnswer !== undefined || selectedMiracle !== undefined);

  function submit() {
    const body = selectedMiracle
      ? { miracle: selectedMiracle.id }
      : {
          answer: selectedAnswer?.id,
          text: editing && selectedAnswer && text.trim() !== selectedAnswer.answer_text ? text : '',
        };
    send.mutate({ promptId, body }, { onSuccess: onDone });
  }

  function pick(value: string, answerText = '') {
    setChoice(value);
    setEditing(false);
    setText(answerText);
  }

  return (
    <section
      aria-label={`${panel.being_name} answers ${panel.subject_name}`}
      className="space-y-3 rounded-lg border bg-background p-4"
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Rolled:</span>
        <Badge>{panel.outcome_tier_name}</Badge>
        <span className="text-muted-foreground">
          · Showing {panel.being_name}&apos;s answers at {panel.outcome_tier_name} and below
          {blocked
            ? ''
            : ` · ${panel.being_name} has not answered ${panel.subject_name} live this game week`}
        </span>
      </div>
      {blocked && (
        <p role="status" className="text-sm font-medium">
          {panel.limit_reason} Nothing more can be sent this week.
        </p>
      )}
      {panel.answers.length === 0 && (
        <p className="text-sm text-muted-foreground">No answers written at this roll or below.</p>
      )}
      {panel.answers.map((option) => {
        const value = `answer-${option.id}`;
        const on = selected === value;
        return (
          <div
            key={option.id}
            className={cn(
              'space-y-2 rounded-md border p-3',
              on && 'border-primary ring-1 ring-primary'
            )}
          >
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name={`live-choice-${promptId}`}
                value={value}
                checked={on}
                disabled={blocked}
                onChange={() => pick(value, option.answer_text)}
                className="mt-1"
              />
              <span className="flex-1 space-y-1">
                <span className="flex items-center justify-between gap-2">
                  <b>{option.outcome_tier_name}</b>
                  <span className="text-xs text-muted-foreground">
                    used {option.used_count} {option.used_count === 1 ? 'time' : 'times'}
                  </span>
                </span>
                <span className="block">{option.answer_text || option.delay_text}</span>
                {option.onlooker_line && (
                  <span className="block text-xs text-muted-foreground">
                    onlooker_line: {option.onlooker_line}
                  </span>
                )}
              </span>
            </label>
            {on && panel.may_adapt && (
              <div className="pl-6">
                {editing ? (
                  <Textarea
                    aria-label="Edit the answer's text"
                    className="min-h-[80px]"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setEditing(true)}
                  >
                    Edit the text
                  </Button>
                )}
              </div>
            )}
          </div>
        );
      })}
      {!panel.may_adapt && panel.answers.length > 0 && (
        <p className="text-xs text-muted-foreground">
          <b>Rule:</b> an edit control appears here only for a GM level with &quot;may adapt
          answers&quot;; this GM&apos;s level has none.
        </p>
      )}
      {panel.miracles.map((miracle) => {
        const value = `${MIRACLE}-${miracle.id}`;
        const off = miracle.reason !== '';
        return (
          <label
            key={miracle.id}
            className={cn(
              'flex items-start gap-2 rounded-md border p-3 text-sm',
              off && 'opacity-55',
              selected === value && 'border-primary ring-1 ring-primary'
            )}
          >
            <input
              type="radio"
              name={`live-choice-${promptId}`}
              value={value}
              checked={selected === value}
              disabled={off || blocked}
              onChange={() => pick(value)}
              className="mt-1"
            />
            <span className="flex-1 space-y-1">
              <b>Miracle: {miracle.name}</b>
              <span className="block text-xs text-muted-foreground">
                {off
                  ? `Shown greyed: ${miracle.reason}`
                  : 'An allowed miracle is sent from this panel and counts as this week’s live answer.'}
              </span>
            </span>
          </label>
        );
      })}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          type="button"
          variant="secondary"
          disabled={dismiss.isPending || send.isPending}
          onClick={() => dismiss.mutate(promptId, { onSuccess: onDone })}
        >
          Send nothing
        </Button>
        <Button type="button" disabled={!ready || send.isPending} onClick={submit}>
          {selectedMiracle ? 'Perform this miracle' : 'Send this answer'}
        </Button>
      </div>
      {(send.error || dismiss.error) && (
        <p role="alert" className="text-sm text-destructive">
          {(send.error ?? dismiss.error)?.message}
        </p>
      )}
    </section>
  );
}
