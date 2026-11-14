import { describe, expect, it } from 'vitest';
import type { PreviewedEffect } from '../types';
import {
  defaultPayerId,
  effectLabel,
  effectValue,
  payerFor,
  pulledResonances,
  showsPayerChoice,
  threadMixInWords,
} from '../burn';

const fury = { id: 1, resonance: 10, resonance_name: 'Fury' };

describe('payerFor', () => {
  it('is the leading resonance until the player picks one', () => {
    expect(payerFor(fury, {})).toBe(10);
    expect(payerFor(fury, { 1: 20 })).toBe(20);
  });
});

describe('pulledResonances', () => {
  it('names each distinct payer once, in thread order', () => {
    const second = { id: 2, resonance: 10, resonance_name: 'Fury' };
    const third = { id: 3, resonance: 30, resonance_name: 'Wonder' };
    expect(pulledResonances([fury, second, third])).toEqual([
      { id: 10, name: 'Fury' },
      { id: 30, name: 'Wonder' },
    ]);
  });

  it('follows the picked payer, naming it from the thread row or the held list', () => {
    const mixed = {
      id: 1,
      resonance: 10,
      resonance_name: 'Fury',
      resonances: [
        { resonance_id: 10, resonance_name: 'Fury' },
        { resonance_id: 20, resonance_name: 'Domination' },
      ],
    };
    expect(pulledResonances([mixed], { 1: 20 })).toEqual([{ id: 20, name: 'Domination' }]);
    expect(pulledResonances([fury], { 1: 40 }, (id) => (id === 40 ? 'Wonder' : undefined))).toEqual(
      [{ id: 40, name: 'Wonder' }]
    );
  });
});

describe('threadMixInWords', () => {
  it('names a single resonance alone', () => {
    expect(threadMixInWords([{ resonance_name: 'Fury', amount: 30, leads: true }])).toBe('Fury');
  });

  it('says the leader is most of it and the rest are some, never numbers', () => {
    expect(
      threadMixInWords([
        { resonance_name: 'Domination', amount: 10, leads: false },
        { resonance_name: 'Fury', amount: 30, leads: true },
      ])
    ).toBe('mostly Fury, some Domination');
  });

  it('calls a sliver a little and skips a row with nothing in it', () => {
    expect(
      threadMixInWords([
        { resonance_name: 'Fury', amount: 95, leads: true },
        { resonance_name: 'Wonder', amount: 3, leads: false },
        { resonance_name: 'Gloom', amount: 0, leads: false },
      ])
    ).toBe('mostly Fury, a little Wonder');
  });

  it('is empty for a thread with no rows', () => {
    expect(threadMixInWords([])).toBe('');
  });
});

describe('showsPayerChoice and defaultPayerId (#5123)', () => {
  const options = (own: boolean, other: boolean) => [
    { resonance_id: 10, affordable: own },
    { resonance_id: 20, affordable: other },
  ];

  it('shows the choice on a thread with several resonance rows', () => {
    const thread = { resonance: 10, resonances: [{}, {}] };
    expect(showsPayerChoice(thread, options(true, true))).toBe(true);
  });

  it('shows no choice on a one-resonance thread whose own resonance can pay', () => {
    expect(showsPayerChoice({ resonance: 10, resonances: [{}] }, options(true, true))).toBe(false);
  });

  it('shows the choice on a one-resonance thread whose own resonance cannot pay', () => {
    expect(showsPayerChoice({ resonance: 10, resonances: [{}] }, options(false, true))).toBe(true);
  });

  it('starts on the leader when it can pay, else the first that can, else the leader', () => {
    expect(defaultPayerId({ resonance: 10 }, options(true, true))).toBe(10);
    expect(defaultPayerId({ resonance: 10 }, options(false, true))).toBe(20);
    expect(defaultPayerId({ resonance: 10 }, options(false, false))).toBe(10);
    expect(defaultPayerId({ resonance: 10 }, [])).toBe(10);
  });
});

describe('effectLabel and effectValue name the actual effect (#5123)', () => {
  const effect = (overrides: Partial<PreviewedEffect>): PreviewedEffect => ({
    kind: 'FLAT_BONUS',
    authored_value: 4,
    level_multiplier: 1,
    scaled_value: 4,
    vital_target: null,
    source_thread_id: 1,
    source_thread_level: 3,
    source_tier: 1,
    narrative_snippet: '',
    inactive: false,
    inactive_reason: null,
    capability_name: null,
    capability_value: null,
    resistance_damage_type_name: null,
    ...overrides,
  });

  it('reads a bonus with a sign', () => {
    expect(effectLabel(effect({}))).toBe('Bonus to this cast');
    expect(effectValue(effect({}))).toBe('+4');
  });

  it('names the capability a perk grants and shows its magnitude', () => {
    const cowed = effect({
      kind: 'CAPABILITY_GRANT',
      authored_value: null,
      scaled_value: null as unknown as number,
      capability_name: 'Cowed',
      capability_value: 2,
    });
    expect(effectLabel(cowed)).toBe('Grants Cowed');
    expect(effectValue(cowed)).toBe('2');
  });

  it('names the damage type a resistance mitigates, or all damage', () => {
    expect(effectLabel(effect({ kind: 'RESISTANCE', resistance_damage_type_name: 'Fire' }))).toBe(
      'Resistance to Fire'
    );
    expect(effectLabel(effect({ kind: 'RESISTANCE' }))).toBe('Resistance to all damage');
  });

  it('gives a perk with no number an empty value, never the word null', () => {
    expect(
      effectValue(effect({ kind: 'NARRATIVE_ONLY', scaled_value: null as unknown as number }))
    ).toBe('');
    expect(
      effectValue(effect({ kind: 'VITAL_BONUS', scaled_value: null as unknown as number }))
    ).toBe('');
  });
});
