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
 */
import { Check, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useConfirmGMPrompt, useDismissGMPrompt } from '../gmPromptQueries';
import type { GMPrompt } from '../types';

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

export function GMPromptRow({
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

  return (
    <div
      data-testid="gm-prompt-row"
      className="flex items-center gap-2 rounded-full border border-border bg-card py-1.5 pl-3 pr-1.5 text-sm"
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
  );
}
