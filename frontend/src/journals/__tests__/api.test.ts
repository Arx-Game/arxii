import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { listJournalEntries, patchJournalSettings } from '../api';

describe('journals api (#3941)', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  });

  it('serialises the new list filters', async () => {
    await listJournalEntries({
      writer: 'ilsa',
      about: 7,
      kind: 'introductions',
      post_mortem: 1,
      since: '2026-09-16T08:00:00Z',
      mark_visit: 1,
    });
    const url = apiFetch.mock.calls[0][0] as string;
    expect(url).toContain('writer=ilsa');
    expect(url).toContain('about=7');
    expect(url).toContain('kind=introductions');
    expect(url).toContain('post_mortem=1');
    expect(url).toContain(`since=${encodeURIComponent('2026-09-16T08:00:00Z')}`);
    expect(url).toContain('mark_visit=1');
  });

  it('patches settings with only the given keys', async () => {
    await patchJournalSettings({ retort_consent: 'anyone' });
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/journals/entries/disposition/');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ retort_consent: 'anyone' });
  });
});
