import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import {
  fetchAvailableActions,
  createActionRequest,
  fetchPendingRequests,
  respondToRequest,
  fetchPlaces,
  joinPlace,
  leavePlace,
} from './actionQueries';

function mockOkResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) } as Response;
}

function mockErrorResponse() {
  return { ok: false } as Response;
}

describe('actionQueries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchAvailableActions', () => {
    it('returns empty stub response (no backend endpoint yet)', async () => {
      const result = await fetchAvailableActions('42');

      // No API call — this is a placeholder until backend implements the endpoint
      expect(apiFetch).not.toHaveBeenCalled();
      expect(result).toEqual({
        self_actions: [],
        targeted_actions: [],
        technique_actions: [],
      });
    });
  });

  describe('createActionRequest', () => {
    it('sends POST to /api/action-requests/ with correct body shape', async () => {
      const responseData = { status: 'pending', request_id: 5 };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(responseData));

      const body = { action_key: 'intimidate', target_persona_id: 3 };
      const result = await createActionRequest('42', body);

      expect(apiFetch).toHaveBeenCalledWith('/api/action-requests/', {
        method: 'POST',
        body: JSON.stringify({
          scene: 42,
          action_key: 'intimidate',
          target_persona: 3,
        }),
      });
      expect(result).toEqual(responseData);
    });

    it('omits target_persona when target_persona_id is undefined', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse({ status: 'pending' }));

      await createActionRequest('42', { action_key: 'perform' });

      expect(apiFetch).toHaveBeenCalledWith('/api/action-requests/', {
        method: 'POST',
        body: JSON.stringify({
          scene: 42,
          action_key: 'perform',
        }),
      });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(createActionRequest('42', { action_key: 'x' })).rejects.toThrow(
        'Failed to perform action'
      );
    });
  });

  describe('fetchPendingRequests', () => {
    it('calls correct URL with scene and status filters', async () => {
      const mockData = { results: [] };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(mockData));

      const result = await fetchPendingRequests('42');

      expect(apiFetch).toHaveBeenCalledWith('/api/action-requests/?scene=42&status=pending');
      expect(result).toEqual(mockData);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchPendingRequests('42')).rejects.toThrow('Failed to load pending requests');
    });
  });

  describe('respondToRequest', () => {
    it('sends POST with decision=accept for accept: true', async () => {
      const responseData = { status: 'resolved' };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(responseData));

      const result = await respondToRequest('42', 7, {
        accept: true,
        difficulty: 'standard',
      });

      expect(apiFetch).toHaveBeenCalledWith('/api/action-requests/7/respond/', {
        method: 'POST',
        body: JSON.stringify({ decision: 'accept' }),
      });
      expect(result).toEqual(responseData);
    });

    it('sends decision=deny for accept: false', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse({ status: 'resolved' }));

      await respondToRequest('42', 7, { accept: false });

      expect(apiFetch).toHaveBeenCalledWith('/api/action-requests/7/respond/', {
        method: 'POST',
        body: JSON.stringify({ decision: 'deny' }),
      });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(respondToRequest('42', 7, { accept: true })).rejects.toThrow(
        'Failed to respond to action request'
      );
    });
  });

  describe('fetchPlaces', () => {
    it('calls correct URL with room filter', async () => {
      const mockData = {
        results: [{ id: 1, name: 'Tavern', description: 'A cozy tavern' }],
      };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(mockData));

      const result = await fetchPlaces('42');

      expect(apiFetch).toHaveBeenCalledWith('/api/places/?room=42');
      expect(result).toEqual(mockData);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchPlaces('42')).rejects.toThrow('Failed to load places');
    });
  });

  describe('joinPlace', () => {
    it('sends POST to correct URL', async () => {
      vi.mocked(apiFetch).mockResolvedValue({ ok: true } as Response);

      await joinPlace('42', 5);

      expect(apiFetch).toHaveBeenCalledWith('/api/places/5/join/', {
        method: 'POST',
      });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(joinPlace('42', 5)).rejects.toThrow('Failed to join place');
    });
  });

  describe('leavePlace', () => {
    it('sends POST to correct URL', async () => {
      vi.mocked(apiFetch).mockResolvedValue({ ok: true } as Response);

      await leavePlace('42', 5);

      expect(apiFetch).toHaveBeenCalledWith('/api/places/5/leave/', {
        method: 'POST',
      });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(leavePlace('42', 5)).rejects.toThrow('Failed to leave place');
    });
  });
});
