/**
 * GMPromptRow — one row of the GM prompt queue (#4101; was the #2183
 * DramaticMomentSuggestionChip). Narration kinds open the composer; a
 * dramatic moment confirms (mints the tag) in place.
 *
 * Controller amendment R6-2: a NARRATED prompt stays in the queue. Its row
 * reads "Narrated" with **Open** (send more lines) and **Done** (dismisses,
 * closing the prompt) instead of **Dismiss**.
 *
 * Row text ruling: a narration row reads "{kind_label}: {subject_name}"
 * followed by "Narrate it?" (pending) or "Narrated." (already sent).
 *
 * Ruling R14-2 (demo-fidelity fix round, F3): the ruled text already carries
 * the kind, so a narration row drops the separate kind-chip badge -- showing
 * both read as a doubled "Crossing Crossing: Rowan Ashcombe". A dramatic
 * moment's body never repeats its kind_label, so its chip stays.
 *
 * Demo-fidelity fix round 2 (F4b): a narration row gets its own tint and
 * border (the `primary` token the F1 private narration block already uses),
 * separate from the Dramatic Moment row's plain `border-border`/`bg-card` --
 * the demo distinguishes `.prompt-chip.kind-crossing` from the plain
 * Dramatic Moment chip the same way. Theme tokens only, never the demo's
 * literal amber.
 *
 * #4101 final review (F2): a refused confirm/dismiss shows the server's
 * message under the row (role="alert"), and the queue refetches so a row
 * another GM already closed drops out instead of failing silently.
 */
import { Check, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  useConfirmGMPrompt,
  useDismissGMPrompt,
  useHoldGMPrompt,
  useOverrideGMPrompt,
} from '../gmPromptQueries';
import type { GMPrompt } from '../types';
import { LiveAnswerPanel } from './LiveAnswerPanel';

/** The row's body text, split so the demo's bold "Narrate it?" / "Confirm?" / "Narrated." can be emphasized (F4) without duplicating the sentence for test matching. */
function promptBody(prompt: GMPrompt): { lead: string; emphasis: string } {
  if (prompt.kind === 'dramatic_moment') {
    return { lead: `${prompt.subject_name}'s ${prompt.moment_type_label}. `, emphasis: 'Confirm?' };
  }
  if (prompt.status === 'narrated') {
    return { lead: `${prompt.kind_label}: ${prompt.subject_name}. `, emphasis: 'Narrated.' };
  }
  return { lead: `${prompt.kind_label}: ${prompt.subject_name}. `, emphasis: 'Narrate it?' };
}

/** A standoff cause proposal (#4354): the GM confirms the attack, holds one action, or overrides with a reason. */
function StandoffCausePromptRow({ prompt, sceneId }: { prompt: GMPrompt; sceneId: string }) {
  const confirm = useConfirmGMPrompt(sceneId);
  const hold = useHoldGMPrompt(sceneId);
  const override = useOverrideGMPrompt(sceneId);
  const [reason, setReason] = useState('');
  const busy = confirm.isPending || hold.isPending || override.isPending;
  const failure = confirm.error ?? hold.error ?? override.error;
  return (
    <div
      data-testid="gm-prompt-row"
      className="flex flex-col gap-2 rounded-md border border-violet-500/50 bg-violet-500/10 p-3 text-sm"
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary" className="text-xs">
          {prompt.kind_label}
        </Badge>
        <span>GM prompt</span>
      </div>
      <div className="font-semibold">{prompt.standoff_group_name}: cause fires</div>
      <div className="text-xs text-muted-foreground">
        Cause: {prompt.standoff_cause_label}. Reason: {prompt.standoff_reason}
        {prompt.standoff_force ? ` ${prompt.standoff_force}` : ''}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="destructive"
          disabled={busy}
          onClick={() => confirm.mutate(prompt.id)}
        >
          Confirm: they attack
        </Button>
        <Button type="button" size="sm" disabled={busy} onClick={() => hold.mutate(prompt.id)}>
          Hold for one action
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy || reason.trim() === ''}
          onClick={() => override.mutate({ promptId: prompt.id, reason: reason.trim() })}
        >
          Override
        </Button>
      </div>
      <Input
        aria-label="Reason (required to override)"
        placeholder="Reason (required to override)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <span className="text-xs text-muted-foreground">
        Players can keep acting while you decide. The cause is tested again after each action.
      </span>
      {failure && (
        <p role="alert" className="text-xs text-destructive">
          {failure.message}
        </p>
      )}
    </div>
  );
}

/**
 * A stewarded being's closed pledge (#4333): the steward answers it from the table
 * page's Beings tab; dismissing here sends an authored answer instead. A rite
 * performed in the scene (slice 5) opens its answer panel in the queue; dismissing
 * it sends nothing.
 */
function BeingAnswerPromptRow({ prompt, sceneId }: { prompt: GMPrompt; sceneId: string }) {
  const dismiss = useDismissGMPrompt(sceneId);
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <div
        data-testid="gm-prompt-row"
        className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/10 p-2 text-sm"
      >
        <span>
          &#10022; {prompt.kind_label}: <b>{prompt.being_answer_summary}</b> Answer it?
        </span>
        <span className="ml-auto flex gap-1">
          {prompt.being_answer_table != null && (
            <Button asChild size="sm">
              <Link to={`/tables/${prompt.being_answer_table}?tab=beings`}>Open</Link>
            </Button>
          )}
          {prompt.being_answer_live && (
            <Button type="button" size="sm" onClick={() => setOpen((on) => !on)}>
              {open ? 'Close' : 'Open'}
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={dismiss.isPending}
            onClick={() => dismiss.mutate(prompt.id)}
          >
            <X className="h-3 w-3" /> Dismiss
          </Button>
        </span>
        {dismiss.error && (
          <p role="alert" className="w-full text-xs text-destructive">
            {dismiss.error.message}
          </p>
        )}
      </div>
      {prompt.being_answer_live && open && (
        <LiveAnswerPanel promptId={prompt.id} sceneId={sceneId} onDone={() => setOpen(false)} />
      )}
    </div>
  );
}

export function GMPromptRow(props: {
  prompt: GMPrompt;
  sceneId: string;
  onOpen: (prompt: GMPrompt) => void;
}) {
  if (props.prompt.kind === 'standoff_cause') {
    return <StandoffCausePromptRow prompt={props.prompt} sceneId={props.sceneId} />;
  }
  if (props.prompt.kind === 'being_answer') {
    return <BeingAnswerPromptRow prompt={props.prompt} sceneId={props.sceneId} />;
  }
  return <NarrationOrMomentRow {...props} />;
}

function NarrationOrMomentRow({
  prompt,
  sceneId,
  onOpen,
}: {
  prompt: GMPrompt;
  sceneId: string;
  onOpen: (prompt: GMPrompt) => void;
}) {
  const confirm = useConfirmGMPrompt(sceneId);
  const dismiss = useDismissGMPrompt(sceneId);
  const busy = confirm.isPending || dismiss.isPending;
  const isMoment = prompt.kind === 'dramatic_moment';
  const isNarrated = !isMoment && prompt.status === 'narrated';

  const body = promptBody(prompt);
  const failure = confirm.error ?? dismiss.error;

  return (
    <div className="space-y-1">
      <div
        data-testid="gm-prompt-row"
        className={cn(
          'flex items-center gap-2 rounded-full border py-1.5 pl-3 pr-1.5 text-sm',
          isMoment ? 'border-border bg-card' : 'border-primary/40 bg-primary/10'
        )}
      >
        <span aria-hidden>✦</span>
        {isMoment && (
          <Badge variant="secondary" className="text-xs">
            {prompt.kind_label}
          </Badge>
        )}
        <span className="flex-1">
          {body.lead}
          <strong className="font-semibold">{body.emphasis}</strong>
        </span>
        {isMoment && (
          <Button
            type="button"
            size="sm"
            aria-label={`Confirm ${prompt.kind_label}`}
            disabled={busy}
            onClick={() => confirm.mutate(prompt.id)}
          >
            <Check className="h-3 w-3" /> Confirm
          </Button>
        )}
        {!isMoment && (
          <Button
            type="button"
            size="sm"
            aria-label={`Open ${prompt.kind_label}`}
            disabled={busy}
            onClick={() => onOpen(prompt)}
          >
            Open
          </Button>
        )}
        {isNarrated ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            aria-label={`Done ${prompt.kind_label}`}
            disabled={busy}
            onClick={() => dismiss.mutate(prompt.id)}
          >
            <Check className="h-3 w-3" /> Done
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            aria-label={`Dismiss ${prompt.kind_label}`}
            disabled={busy}
            onClick={() => dismiss.mutate(prompt.id)}
          >
            <X className="h-3 w-3" /> Dismiss
          </Button>
        )}
      </div>
      {failure && (
        <p role="alert" className="px-3 text-xs text-destructive">
          {failure.message}
        </p>
      )}
    </div>
  );
}
