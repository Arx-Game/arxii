/**
 * "Part of X's Crossing" under a GM narration row (#4101, demo Screen 3).
 *
 * Ruling R11-1: the private suffix uses the FULL displayed subject name, not
 * its first word. The demo's own markup took the first word ("visible only
 * to Rowan"), but `subject_name` is already per-viewer masked on REST (an
 * undiscovered fake-name face reads as its short description, not a name —
 * see `narrated_event_payload`/`get_narrates`), so a masked face's first word
 * can read as a bare article ("a" for "a hooded figure"). This deviates from
 * the demo; flagged for the demo-fidelity reviewer.
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
  const suffix = onlySubject ? ` · visible only to ${narrates.subject_name}` : '';
  return (
    <p data-testid="narrated-event-tag" className="mt-1 text-xs italic text-muted-foreground">
      {`✦ part of ${whose} ${narrates.kind_label}${suffix}`}
    </p>
  );
}
