import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchCharacterVitals } from '../vitalsQueries';
import { apiFetch } from '@/evennia_replacements/api';

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));
const mockApiFetch = vi.mocked(apiFetch);

describe('fetchCharacterVitals', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('returns the payload on 200', async () => {
    const payload = {
      health: 75,
      max_health: 100,
      health_percentage: 0.75,
      wound_description: 'Bruised',
      status: 'alive',
      fatigue: {
        physical: { current: 0, capacity: 10, percentage: 0, zone: 'fresh' },
        social: { current: 0, capacity: 10, percentage: 0, zone: 'fresh' },
        mental: { current: 0, capacity: 10, percentage: 0, zone: 'fresh' },
        well_rested: false,
        rested_today: false,
      },
    };
    mockApiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payload),
    } as Response);
    await expect(fetchCharacterVitals(7)).resolves.toEqual(payload);
    expect(mockApiFetch).toHaveBeenCalledWith('/api/vitals/7/');
  });

  it.each([401, 403, 404])('returns null on %i instead of throwing', async (status) => {
    mockApiFetch.mockResolvedValue({ ok: false, status } as Response);
    await expect(fetchCharacterVitals(7)).resolves.toBeNull();
  });

  it('throws on 500', async () => {
    mockApiFetch.mockResolvedValue({ ok: false, status: 500 } as Response);
    await expect(fetchCharacterVitals(7)).rejects.toThrow();
  });
});
