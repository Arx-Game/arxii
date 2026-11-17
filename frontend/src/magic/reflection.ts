/**
 * Reflections (#5124): what a "Reflecting on" row holds and what it sends.
 *
 * A pose or a journal entry can name one thing it reflects on, a kindled deed, the resonance
 * unsettling the writer or the Mire a Sineater carries for a Sinner, and make a choice about
 * it. The row's state is a `ReflectionDraft`; the optional fields the server takes come from
 * `reflectionFields`.
 */

import type { ReflectionOption } from '@/magic/types';

/**
 * What a reflection decides. Embrace and Disown apply to a deed or the unsettling resonance;
 * Absolve, Condemn and Succumb apply to a burden, the Mire a Sineater carries for a Sinner.
 */
export type ReflectionChoice = 'EMBRACE' | 'DISOWN' | 'ABSOLVE' | 'CONDEMN' | 'SUCCUMB';

interface ChoiceOption {
  value: ReflectionChoice;
  label: string;
}

const DEED_CHOICES: ChoiceOption[] = [
  { value: 'EMBRACE', label: 'Embrace' },
  { value: 'DISOWN', label: 'Disown' },
];

const BURDEN_CHOICES: ChoiceOption[] = [
  { value: 'ABSOLVE', label: 'Absolve' },
  { value: 'CONDEMN', label: 'Condemn' },
  { value: 'SUCCUMB', label: 'Succumb' },
];

/**
 * The choices a reflection offers, by what it reflects on: a burden takes the three that
 * settle the Mire, anything else Embrace or Disown, and nothing picked yet shows the pair.
 * The pose composer and the journal editor both read this, so they cannot disagree.
 */
export function choicesFor(option: ReflectionOption | null): ChoiceOption[] {
  return option?.kind === 'burden' ? BURDEN_CHOICES : DEED_CHOICES;
}

/** A choice is one the picked thing takes. */
export function isChoiceFor(option: ReflectionOption, choice: ReflectionChoice): boolean {
  return choicesFor(option).some((offered) => offered.value === choice);
}

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
  reflect_tether_id?: number;
}

/** A target or a choice is set but not both. */
export function isReflectionIncomplete(draft: ReflectionDraft): boolean {
  return (draft.option === null) !== (draft.choice === null);
}

/** Both a target and a choice are set. */
export function isReflecting(draft: ReflectionDraft): boolean {
  return draft.option !== null && draft.choice !== null;
}

/** What the row says while a pick is half made, in words that fit what is picked. */
export function reflectionIncompleteLine(draft: ReflectionDraft): string {
  const names = choicesFor(draft.option).map((choice) => choice.label);
  const last = names[names.length - 1];
  const list =
    names.length > 2 ? `${names.slice(0, -1).join(', ')} or ${last}` : names.join(' or ');
  return draft.option === null
    ? `Choose what you are reflecting on and ${list}, or clear them.`
    : `Choose ${list}, or clear them.`;
}

/** The request field that names the reflected-on thing, by its kind. */
function targetField(option: ReflectionOption): ReflectionFields {
  switch (option.kind) {
    case 'deed':
      return { reflect_grant_id: option.id };
    case 'burden':
      return { reflect_tether_id: option.id };
    case 'resonance':
      return { reflect_resonance_id: option.id };
  }
}

export function reflectionFields(draft: ReflectionDraft): ReflectionFields {
  if (draft.option === null || draft.choice === null) return {};
  return { reflect_choice: draft.choice, ...targetField(draft.option) };
}

/**
 * The draft after the writer picks `option` (or taps it again to clear it). A choice the new
 * pick does not take is dropped, so Embrace never travels with a burden.
 */
export function pickOption(draft: ReflectionDraft, option: ReflectionOption): ReflectionDraft {
  if (draft.option !== null && sameOption(draft.option, option)) {
    return { ...draft, option: null };
  }
  const choice = draft.choice !== null && isChoiceFor(option, draft.choice) ? draft.choice : null;
  return { option, choice };
}

/** The same deed, burden or resonance as before, whichever kind it is. */
export function sameOption(a: ReflectionOption, b: ReflectionOption): boolean {
  return a.kind === b.kind && a.id === b.id;
}
