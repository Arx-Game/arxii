import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import {
  createPoseEndorsement,
  deletePoseEndorsement,
  createSceneEntryEndorsement,
} from '../queries';

function mockOkResponse(data: unknown) {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}

function mockNoContentResponse() {
  return { ok: true, status: 204 } as Response;
}

function mockErrorResponse(status = 400) {
  return { ok: false, status } as Response;
}

describe('endorsement API functions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('createPoseEndorsement', () => {
    it('POSTs to /api/magic/pose-endorsements/ with interaction + resonance body', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse({ id: 1, resonance_id: 5 }));

      const result = await createPoseEndorsement({ interaction: 42, resonance: 5 });

      expect(apiFetch).toHaveBeenCalledWith('/api/magic/pose-endorsements/', {
        method: 'POST',
        body: JSON.stringify({ interaction: 42, resonance: 5 }),
      });
      expect(result).toEqual({ id: 1, resonance_id: 5 });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(createPoseEndorsement({ interaction: 42, resonance: 5 })).rejects.toThrow(
        'Failed to endorse pose'
      );
    });
  });

  describe('deletePoseEndorsement', () => {
    it('DELETEs /api/magic/pose-endorsements/<id>/', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockNoContentResponse());

      await deletePoseEndorsement(7);

      expect(apiFetch).toHaveBeenCalledWith('/api/magic/pose-endorsements/7/', {
        method: 'DELETE',
      });
    });

    it('does not throw on 204', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockNoContentResponse());

      await expect(deletePoseEndorsement(7)).resolves.not.toThrow();
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse(403));

      await expect(deletePoseEndorsement(7)).rejects.toThrow('Failed to retract endorsement');
    });
  });

  describe('createSceneEntryEndorsement', () => {
    it('POSTs to /api/magic/scene-entry-endorsements/ with endorsee_sheet + scene + resonance', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse({ id: 3 }));

      const result = await createSceneEntryEndorsement({
        endorsee_sheet: 10,
        scene: 99,
        resonance: 5,
      });

      expect(apiFetch).toHaveBeenCalledWith('/api/magic/scene-entry-endorsements/', {
        method: 'POST',
        body: JSON.stringify({ endorsee_sheet: 10, scene: 99, resonance: 5 }),
      });
      expect(result).toEqual({ id: 3 });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(
        createSceneEntryEndorsement({ endorsee_sheet: 10, scene: 99, resonance: 5 })
      ).rejects.toThrow('Failed to endorse entry');
    });
  });
});
