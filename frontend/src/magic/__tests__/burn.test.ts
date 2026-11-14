import { describe, expect, it } from 'vitest';
import { payerFor, pulledResonances, threadMixInWords } from '../burn';

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
