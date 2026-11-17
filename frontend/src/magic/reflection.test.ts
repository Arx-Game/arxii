/**
 * Reflection helpers (#5177): the choices follow the kind of thing reflected on, and the same
 * `reflectionFields` feeds the pose composer and the journal editor, so a burden sends
 * `reflect_tether_id` from both.
 */

import { describe, expect, it } from 'vitest';
import {
  choicesFor,
  pickOption,
  reflectionFields,
  reflectionIncompleteLine,
  type ReflectionDraft,
} from '@/magic/reflection';
import type { ReflectionOption } from '@/magic/types';

const deed: ReflectionOption = { kind: 'deed', id: 3, label: 'A deed', replaces_waiting: false };
const resonance: ReflectionOption = {
  kind: 'resonance',
  id: 4,
  label: 'Your Domination',
  replaces_waiting: false,
};
const burden: ReflectionOption = {
  kind: 'burden',
  id: 5,
  label: 'The Mire you carry for Ysmay',
  replaces_waiting: false,
};

describe('reflection choices', () => {
  it('offers Embrace and Disown for a deed, a resonance or nothing picked, and three for a burden', () => {
    const values = (option: ReflectionOption | null) =>
      choicesFor(option).map((choice) => choice.value);
    expect(values(null)).toEqual(['EMBRACE', 'DISOWN']);
    expect(values(deed)).toEqual(['EMBRACE', 'DISOWN']);
    expect(values(resonance)).toEqual(['EMBRACE', 'DISOWN']);
    expect(values(burden)).toEqual(['ABSOLVE', 'CONDEMN', 'SUCCUMB']);
  });

  it('names the target field that fits each kind', () => {
    const draft = (option: ReflectionOption, choice: ReflectionDraft['choice']) => ({
      option,
      choice,
    });
    expect(reflectionFields(draft(deed, 'EMBRACE'))).toEqual({
      reflect_choice: 'EMBRACE',
      reflect_grant_id: 3,
    });
    expect(reflectionFields(draft(resonance, 'DISOWN'))).toEqual({
      reflect_choice: 'DISOWN',
      reflect_resonance_id: 4,
    });
    expect(reflectionFields(draft(burden, 'CONDEMN'))).toEqual({
      reflect_choice: 'CONDEMN',
      reflect_tether_id: 5,
    });
  });

  it('keeps a choice across picks that take it and drops it across picks that do not', () => {
    expect(pickOption({ option: deed, choice: 'EMBRACE' }, resonance)).toEqual({
      option: resonance,
      choice: 'EMBRACE',
    });
    expect(pickOption({ option: deed, choice: 'EMBRACE' }, burden)).toEqual({
      option: burden,
      choice: null,
    });
    expect(pickOption({ option: burden, choice: 'SUCCUMB' }, deed).choice).toBeNull();
  });

  it('says which choices are missing in words that fit the pick', () => {
    expect(reflectionIncompleteLine({ option: burden, choice: null })).toBe(
      'Choose Absolve, Condemn or Succumb, or clear them.'
    );
    expect(reflectionIncompleteLine({ option: deed, choice: null })).toBe(
      'Choose Embrace or Disown, or clear them.'
    );
    expect(reflectionIncompleteLine({ option: null, choice: 'EMBRACE' })).toBe(
      'Choose what you are reflecting on and Embrace or Disown, or clear them.'
    );
  });
});
