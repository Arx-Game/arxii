/**
 * Tests for getDraftOffers (#3675): distinctions are offered by CG chapter,
 * not surfaced through a standalone Distinctions stage.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { getDraftOffers } from '../api';
import type { OffersResponse } from '../types';

function mockOkResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) } as Response;
}

function mockErrorResponse() {
  return { ok: false } as Response;
}

describe('character-creation/api getDraftOffers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls /drafts/{id}/offers/?chapter=glimpse', async () => {
    const data: OffersResponse = { offers: [], closed: [] };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const result = await getDraftOffers(7, 'glimpse');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/character-creation/drafts/7/offers/?chapter=glimpse'
    );
    expect(result).toEqual(data);
  });

  it('hits a different chapter query for tradition_step', async () => {
    const data: OffersResponse = { offers: [], closed: [] };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    await getDraftOffers(7, 'tradition_step');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/character-creation/drafts/7/offers/?chapter=tradition_step'
    );
  });

  it('returns the offers/closed payload from the server', async () => {
    const data: OffersResponse = {
      offers: [
        {
          offer_id: 1,
          distinction_id: 42,
          name: 'Silver Tongue',
          player_line: 'You always know the right thing to say.',
          chapter: 'glimpse',
          arrives_as: 'choice',
          opener_label: 'Wonder',
          cost_per_rank: 5,
          max_rank: 3,
          is_locked: false,
          lock_reason: '',
        },
      ],
      closed: [
        { distinction_id: 99, name: 'Kept Close', reason: 'This tradition has no living masters.' },
      ],
    };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const result = await getDraftOffers(7, 'glimpse');

    expect(result).toEqual(data);
  });

  it('throws on error response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

    await expect(getDraftOffers(7, 'glimpse')).rejects.toThrow('Failed to load chapter offers');
  });
});
