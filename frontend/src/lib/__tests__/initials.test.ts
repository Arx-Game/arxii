import { describe, expect, it } from 'vitest';

import { initials } from '../initials';

describe('initials', () => {
  it('takes the first letters of the first two words', () => {
    expect(initials('Captain Vael')).toBe('CV');
    expect(initials('Sergeant Mira of the Watch')).toBe('SM');
  });
  it('uses one letter for one word and ignores extra spaces', () => {
    expect(initials('Mira')).toBe('M');
    expect(initials('  low   gate ')).toBe('LG');
  });
  it('falls back for an empty name', () => {
    expect(initials('')).toBe('?');
  });
});
