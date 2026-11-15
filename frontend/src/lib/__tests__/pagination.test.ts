import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchAllPages } from '../pagination';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

vi.mock('@/lib/utils', () => ({
  getCookie: vi.fn().mockReturnValue('mock-csrf-token'),
}));

function page(results: number[], next: string | null) {
  return { ok: true, json: vi.fn().mockResolvedValue({ results, next }) };
}

describe('fetchAllPages (#5140)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('follows a next link built on another host, on this page origin', async () => {
    // The dev proxy hands the API its own host, so DRF's next names :4001, not the page.
    mockFetch
      .mockResolvedValueOnce(page([1, 2], 'http://localhost:4001/api/roster/mail/?page=2'))
      .mockResolvedValueOnce(page([3], null));

    const all = await fetchAllPages<number>('/api/roster/mail/', 'Could not load');

    expect(all).toEqual([1, 2, 3]);
    expect(mockFetch.mock.calls[1][0]).toBe(`${window.location.origin}/api/roster/mail/?page=2`);
  });

  it('follows a next link on this origin unchanged', async () => {
    mockFetch
      .mockResolvedValueOnce(page([1], `${window.location.origin}/api/items/?page=2`))
      .mockResolvedValueOnce(page([2], null));

    expect(await fetchAllPages<number>('/api/items/', 'Could not load')).toEqual([1, 2]);
    expect(mockFetch.mock.calls[1][0]).toBe(`${window.location.origin}/api/items/?page=2`);
  });
});
