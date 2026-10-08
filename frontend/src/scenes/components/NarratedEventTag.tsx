/**
 * "Part of X's Crossing" under a GM narration row (#4101, demo Screen 3).
 *
 * Ruling R11-1: the private suffix uses the FULL displayed subject name, not
 * its first word. The demo's own markup took the first word ("visible only
 * to Rowan"), but `subject_name` is already per-viewer masked on REST (an
 * undiscovered fake-name face reads as its short description, not a name —
 * see `narrated_event_payload`/`get_narrates`), so a masked face's first word
 * can read as a bare article ("a" for "a hooded figure"). This deviates from
 * the demo; flagged for the demo-fidelity reviewer. The suffix itself is
 * "· <name> only" since #4193: the exception is marked with a word, never a
 * "visible only to" caption.
 *
 * Demo-fidelity fix round 2 (F1b): the demo's `.log-tag` is small, uppercase
 * and letter-spaced (never italic) -- matches here via `uppercase
 * tracking-wide`, dropping the earlier italic treatment. The caller places
 * this tag INSIDE the room line's left-rule box (PoseUnit.tsx's narration
 * branch moves `border-l-2`/padding onto the shared wrapper, not just the
 * content `<p>`) so the tag sits under the line within the same rule, as in
 * the demo, rather than flush below it. The private block already wraps both
 * the quote and this tag in its own rule/tint box, so it needed no PoseUnit
 * change -- only this shared styling.
 */
import type { NarratedEvent } from '../types';

export function NarratedEventTag({
  narrates,
  receiverPersonaIds,
}: {
  narrates: NarratedEvent | null | undefined;
  receiverPersonaIds: number[];
}) {
  if (!narrates) return null;
  const whose = narrates.subject_name ? `${narrates.subject_name}'s` : 'a';
  const onlySubject =
    Boolean(narrates.subject_name) &&
    narrates.subject_persona_id != null &&
    receiverPersonaIds.length === 1 &&
    receiverPersonaIds[0] === narrates.subject_persona_id;
  const suffix = onlySubject ? ` · ${narrates.subject_name} only` : '';
  return (
    <p
      data-testid="narrated-event-tag"
      className="mt-1 text-xs uppercase tracking-wide text-muted-foreground"
    >
      {`✦ part of ${whose} ${narrates.kind_label}${suffix}`}
    </p>
  );
}
