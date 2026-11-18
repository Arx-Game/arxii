import { describe, expect, it } from 'vitest';

import type { StartingArea } from '../types';
import {
  capitalize,
  countNoun,
  formatHeight,
  getRealmTheme,
  statusLabel,
  statusVariant,
} from '../utils';

function makeArea(realm_theme: string): StartingArea {
  return {
    id: 1,
    name: 'Test Area',
    description: '',
    crest_image: null,
    realm_theme,
    realm_slug: realm_theme,
    realm_name: realm_theme,
    realm_formal_name: '',
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

describe('formatHeight', () => {
  it.each([
    [68, `5'8"`],
    [60, `5'0"`],
  ])('renders %i inches as %s', (inches, expected) => {
    expect(formatHeight(inches)).toBe(expected);
  });
});

describe('countNoun', () => {
  it('keeps the noun singular for one and makes it plural otherwise', () => {
    expect(countNoun(1, 'pick')).toBe('1 pick');
    expect(countNoun(2, 'pick')).toBe('2 picks');
    expect(countNoun(0, 'kind')).toBe('0 kinds');
  });
});

describe('capitalize', () => {
  it('raises the first letter and leaves the rest', () => {
    expect(capitalize('willpower')).toBe('Willpower');
    expect(capitalize('Melee Combat')).toBe('Melee Combat');
    expect(capitalize('')).toBe('');
  });
});
