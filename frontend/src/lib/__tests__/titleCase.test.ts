import { describe, expect, it } from 'vitest';

import { titleCase } from '../titleCase';

describe('titleCase', () => {
  it('capitalises each word', () => {
    expect(titleCase('agility')).toBe('Agility');
    expect(titleCase('melee combat')).toBe('Melee Combat');
  });
  it('leaves an already-cased name alone', () => {
    expect(titleCase('Mortal Resolve')).toBe('Mortal Resolve');
  });
});
