import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  createJournalEntry,
  editJournalEntry,
  getJournalSettings,
  listJournalEntries,
  listMyJournalEntries,
  patchJournalSettings,
  respondToJournal,
} from '../api';

describe('journals api (#3941)', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  });

  it('serialises the new list filters', async () => {
    await listJournalEntries(5, {
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
    await patchJournalSettings(5, { retort_consent: 'anyone' });
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/journals/entries/disposition/');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ retort_consent: 'anyone' });
  });
  // The view resolves the acting character from `X-Character-ID` alone (#5124): without it
  // every journal post answers "No character found.".
  it('posts an entry as the acting character', async () => {
    await createJournalEntry(5, { title: 'Dawn', body: 'It rose.', is_public: false, tags: [] });
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/journals/entries/');
    expect(new Headers(init.headers).get('X-Character-ID')).toBe('5');
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
  });

  it("reads the viewer's own entries as the acting character", async () => {
    await listMyJournalEntries(5, { page: 2 });
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/journals/entries/mine/?page=2');
    expect(new Headers(init.headers).get('X-Character-ID')).toBe('5');
  });

  it('sends the character on responses, edits and settings reads, and on the feed', async () => {
    await respondToJournal(5, 9, { response_type: 'praise', title: 't', body: 'b' });
    await editJournalEntry(5, 9, { title: 'New' });
    await getJournalSettings(5);
    await listJournalEntries(5);
    for (const call of apiFetch.mock.calls as [string, RequestInit][]) {
      expect(new Headers(call[1].headers).get('X-Character-ID')).toBe('5');
    }
  });

  it('sends no header before a character is chosen', async () => {
    await listJournalEntries(null);
    const [, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).has('X-Character-ID')).toBe(false);
  });
});
