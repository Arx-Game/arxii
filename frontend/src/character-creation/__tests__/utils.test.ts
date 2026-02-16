import { describe, expect, it } from 'vitest';

import { getRealmTheme, statusLabel, statusVariant } from '../utils';

describe('getRealmTheme', () => {
  it.each([
    ['arx', 'arx'],
    ['umbral empire', 'umbros'],
    ['luxen dominion', 'luxen'],
    ['grand principality of inferna', 'inferna'],
    ['inferna', 'inferna'],
    ['ariwn', 'ariwn'],
    ['aythirmok', 'aythirmok'],
  ] as const)('maps "%s" to "%s"', (areaName, expected) => {
    expect(getRealmTheme(areaName)).toBe(expected);
  });

  it('is case-insensitive', () => {
    expect(getRealmTheme('ARX')).toBe('arx');
    expect(getRealmTheme('Umbral Empire')).toBe('umbros');
    expect(getRealmTheme('LUXEN DOMINION')).toBe('luxen');
  });

  it('returns default for unknown area names', () => {
    expect(getRealmTheme('unknown city')).toBe('default');
    expect(getRealmTheme('')).toBe('default');
    expect(getRealmTheme('some random place')).toBe('default');
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
