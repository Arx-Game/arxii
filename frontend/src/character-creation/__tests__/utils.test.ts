import { describe, expect, it } from 'vitest';

import type { StartingArea } from '../types';
import { getRealmTheme, statusLabel, statusVariant } from '../utils';

function makeArea(realm_theme: string): StartingArea {
  return {
    id: 1,
    name: 'Test Area',
    description: '',
    crest_image: null,
    is_accessible: true,
    realm_theme,
  };
}

describe('getRealmTheme', () => {
  it.each([
    ['arx', 'arx'],
    ['umbros', 'umbros'],
    ['luxen', 'luxen'],
    ['inferna', 'inferna'],
    ['ariwn', 'ariwn'],
    ['aythirmok', 'aythirmok'],
    ['default', 'default'],
  ] as const)('maps realm_theme "%s" to "%s"', (theme, expected) => {
    expect(getRealmTheme(makeArea(theme))).toBe(expected);
  });

  it('returns default for unknown realm_theme values', () => {
    expect(getRealmTheme(makeArea('unknown'))).toBe('default');
    expect(getRealmTheme(makeArea(''))).toBe('default');
    expect(getRealmTheme(makeArea('some-random-theme'))).toBe('default');
  });
});

describe('statusLabel', () => {
  it.each([
    ['submitted', 'Submitted'],
    ['in_review', 'In Review'],
    ['revisions_requested', 'Revisions Requested'],
    ['approved', 'Approved'],
    ['denied', 'Denied'],
    ['withdrawn', 'Withdrawn'],
  ] as const)('maps "%s" to "%s"', (status, expected) => {
    expect(statusLabel(status)).toBe(expected);
  });
});

describe('statusVariant', () => {
  it.each([
    ['submitted', 'default'],
    ['in_review', 'default'],
    ['revisions_requested', 'outline'],
    ['approved', 'secondary'],
    ['denied', 'destructive'],
    ['withdrawn', 'destructive'],
  ] as const)('maps "%s" to "%s"', (status, expected) => {
    expect(statusVariant(status)).toBe(expected);
  });
});
