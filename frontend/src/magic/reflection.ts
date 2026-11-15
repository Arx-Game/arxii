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

/** What the writer has picked: the thing reflected on and whether they embrace or disown it. */
export interface ReflectionDraft {
  option: ReflectionOption;
  choice: ReflectionChoice;
}

/** The fields a pose or journal request carries for a reflection (none when not reflecting). */
export interface ReflectionFields {
  reflect_choice?: ReflectionChoice;
  reflect_grant_id?: number;
  reflect_resonance_id?: number;
}

export function reflectionFields(draft: ReflectionDraft | null): ReflectionFields {
  if (draft === null) return {};
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
