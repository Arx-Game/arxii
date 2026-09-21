/**
 * The label's printed text (#3957).
 *
 * Public awareness is UNMARKED by ruling — a label that everyone may know reads as the
 * bare type name, and only a marker earns the separator.
 */
import { describe, expect, it } from 'vitest';

import { labelTagClass, labelText } from '../labelText';

describe('labelText', () => {
  it('leaves a public label bare', () => {
    expect(
      labelText({ type_name: 'Lover', awareness: 'public', is_former: false, is_mutual: false })
    ).toBe('Lover');
  });

  it('marks clandestine and private', () => {
    expect(
      labelText({
        type_name: 'Lover',
        awareness: 'clandestine',
        is_former: false,
        is_mutual: false,
      })
    ).toBe('Lover · Clandestine');
    expect(
      labelText({ type_name: 'Enemy', awareness: 'private', is_former: false, is_mutual: false })
    ).toBe('Enemy · Private');
  });

  it('marks former over awareness', () => {
    expect(
      labelText({ type_name: 'Friend', awareness: 'public', is_former: true, is_mutual: false })
    ).toBe('Friend · former');
  });
});

describe('labelTagClass', () => {
  it('is the bare tag for a public label', () => {
    expect(
      labelTagClass({
        type_name: 'Friend',
        awareness: 'public',
        is_former: false,
        is_mutual: false,
      })
    ).toBe('refsheet-tag');
  });

  it('carries the awareness and valence variants', () => {
    expect(
      labelTagClass(
        { type_name: 'Enemy', awareness: 'private', is_former: false, is_mutual: false },
        'hostile'
      )
    ).toBe('refsheet-tag refsheet-tag-private refsheet-tag-hostile');
    expect(
      labelTagClass(
        { type_name: 'Friend', awareness: 'public', is_former: true, is_mutual: false },
        'warm'
      )
    ).toBe('refsheet-tag refsheet-tag-former refsheet-tag-warm');
  });
});
