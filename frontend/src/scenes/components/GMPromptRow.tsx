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
 */
import { Check, X } from 'lucide-react';
import { useConfirmGMPrompt, useDismissGMPrompt } from '../gmPromptQueries';
import type { GMPrompt } from '../types';

function promptBody(prompt: GMPrompt): string {
  if (prompt.kind === 'dramatic_moment') {
    return `${prompt.subject_name}'s ${prompt.moment_type_label}. Confirm?`;
  }
  if (prompt.status === 'narrated') {
    return `${prompt.kind_label}: ${prompt.subject_name}. Narrated.`;
  }
  return `${prompt.kind_label}: ${prompt.subject_name}. Narrate it?`;
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

  return (
    <div data-testid="gm-prompt-row" className="flex items-center gap-2 py-1 text-sm">
      <span aria-hidden className="text-amber-500">
        ✦
      </span>
      <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
        {prompt.kind_label}
      </span>
      <span className="flex-1">{promptBody(prompt)}</span>
      {isMoment && (
        <button
          type="button"
          aria-label={`Confirm ${prompt.kind_label}`}
          disabled={busy}
          onClick={() => confirm.mutate(prompt.id)}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 hover:bg-amber-500/20"
        >
          <Check className="h-3 w-3" /> Confirm
        </button>
      )}
      {!isMoment && (
        <button
          type="button"
          aria-label={`Open ${prompt.kind_label}`}
          disabled={busy}
          onClick={() => onOpen(prompt)}
          className="rounded px-2 py-0.5 hover:bg-amber-500/20"
        >
          Open
        </button>
      )}
      {isNarrated ? (
        <button
          type="button"
          aria-label={`Done ${prompt.kind_label}`}
          disabled={busy}
          onClick={() => dismiss.mutate(prompt.id)}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-muted-foreground hover:bg-muted"
        >
          <Check className="h-3 w-3" /> Done
        </button>
      ) : (
        <button
          type="button"
          aria-label={`Dismiss ${prompt.kind_label}`}
          disabled={busy}
          onClick={() => dismiss.mutate(prompt.id)}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-muted-foreground hover:bg-muted"
        >
          <X className="h-3 w-3" /> Dismiss
        </button>
      )}
    </div>
  );
}
