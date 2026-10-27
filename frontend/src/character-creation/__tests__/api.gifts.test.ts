/**
 * Tests for getGifts (#4669): GiftViewSet is paginated, so the body is
 * {count, next, previous, results} and the function must hand back the array.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { getGifts } from '../api';

function mockOkResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) } as Response;
}

describe('character-creation/api getGifts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('requests one page of 100 gifts from the magic gifts endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockOkResponse({ count: 0, next: null, previous: null, results: [] })
    );

    await getGifts();

    expect(apiFetch).toHaveBeenCalledWith('/api/magic/gifts/?page_size=100');
  });

  it('returns the results array from the paginated body, not the envelope', async () => {
    const gifts = [
      { id: 1, name: 'Fire' },
      { id: 2, name: 'Water' },
    ];
    vi.mocked(apiFetch).mockResolvedValue(
      mockOkResponse({ count: 2, next: null, previous: null, results: gifts })
    );

    const result = await getGifts();

    expect(result).toEqual(gifts);
    expect(Array.isArray(result)).toBe(true);
  });
});
