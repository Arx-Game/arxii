/**
 * Reflections (#5124): what a "Reflecting on" row holds and what it sends.
 *
 * A pose or a journal entry can name one thing it reflects on, a kindled deed or the resonance
 * unsettling the writer, and Embrace or Disown it. The row's state is a `ReflectionDraft`; the
 * three optional fields the server takes come from `reflectionFields`.
 */

import type { ReflectionOption } from '@/magic/types';

export type ReflectionChoice = 'EMBRACE' | 'DISOWN';

export const REFLECTION_CHOICES: { value: ReflectionChoice; label: string }[] = [
  { value: 'EMBRACE', label: 'Embrace' },
  { value: 'DISOWN', label: 'Disown' },
];

/**
 * What the writer has picked: the thing reflected on and whether they embrace or disown it.
 * Both are null while the row is idle. A reflection needs both: one without the other is
 * `isReflectionIncomplete`, and nothing posts until it is finished or cleared.
 */
export interface ReflectionDraft {
  option: ReflectionOption | null;
  choice: ReflectionChoice | null;
}

/** The idle row: nothing picked. */
export const NO_REFLECTION: ReflectionDraft = { option: null, choice: null };

/** The fields a pose or journal request carries for a reflection (none when not reflecting). */
export interface ReflectionFields {
  reflect_choice?: ReflectionChoice;
  reflect_grant_id?: number;
  reflect_resonance_id?: number;
}

/** A target or a choice is set but not both. */
export function isReflectionIncomplete(draft: ReflectionDraft): boolean {
  return (draft.option === null) !== (draft.choice === null);
}

/** Both a target and a choice are set. */
export function isReflecting(draft: ReflectionDraft): boolean {
  return draft.option !== null && draft.choice !== null;
}

export const REFLECTION_INCOMPLETE_LINE =
  'Choose what you are reflecting on and Embrace or Disown, or clear them.';

export function reflectionFields(draft: ReflectionDraft): ReflectionFields {
  if (draft.option === null || draft.choice === null) return {};
  return {
    reflect_choice: draft.choice,
    ...(draft.option.kind === 'deed'
      ? { reflect_grant_id: draft.option.id }
      : { reflect_resonance_id: draft.option.id }),
  };
}

/** The same deed or resonance as before, whichever kind it is. */
export function sameOption(a: ReflectionOption, b: ReflectionOption): boolean {
  return a.kind === b.kind && a.id === b.id;
}
