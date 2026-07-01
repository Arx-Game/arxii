import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import {
  fetchCategories,
  fetchPreference,
  updatePreference,
  createPreference,
  fetchCategoryRules,
  upsertCategoryRule,
  deleteCategoryRule,
  fetchWhitelist,
  addWhitelist,
  removeWhitelist,
  fetchBlacklist,
  addBlacklist,
  removeBlacklist,
} from '../api';

function mockOkResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) } as Response;
}

function mockEmptyOk() {
  return { ok: true } as Response;
}

function mockErrorResponse() {
  return { ok: false } as Response;
}

describe('consent/api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Categories
  // -------------------------------------------------------------------------

  describe('fetchCategories', () => {
    it('calls /api/consent/categories/', async () => {
      const data = { count: 0, results: [] };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await fetchCategories();

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/categories/');
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchCategories()).rejects.toThrow('Failed to load consent categories');
    });
  });

  // -------------------------------------------------------------------------
  // Preferences
  // -------------------------------------------------------------------------

  describe('fetchPreference', () => {
    it('calls for-tenure endpoint with tenureId', async () => {
      const data = { id: 1, tenure: 42, allow_social_actions: true };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await fetchPreference(42);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/preferences/for-tenure/42/');
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchPreference(42)).rejects.toThrow('Failed to load consent preference');
    });
  });

  describe('updatePreference', () => {
    it('sends PATCH to /api/consent/preferences/{id}/', async () => {
      const data = { id: 1, tenure: 42, allow_social_actions: false };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await updatePreference(1, { allow_social_actions: false });

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/preferences/1/', {
        method: 'PATCH',
        body: JSON.stringify({ allow_social_actions: false }),
      });
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(updatePreference(1, {})).rejects.toThrow('Failed to update consent preference');
    });
  });

  describe('createPreference', () => {
    it('sends POST to /api/consent/preferences/', async () => {
      const data = { id: 2, tenure: 7, allow_social_actions: true };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await createPreference({ tenure: 7 });

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/preferences/', {
        method: 'POST',
        body: JSON.stringify({ tenure: 7 }),
      });
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(createPreference({ tenure: 7 })).rejects.toThrow(
        'Failed to create consent preference'
      );
    });
  });

  // -------------------------------------------------------------------------
  // Category rules
  // -------------------------------------------------------------------------

  describe('fetchCategoryRules', () => {
    it('calls /api/consent/category-rules/ with preference filter', async () => {
      const data = { count: 0, results: [] };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await fetchCategoryRules(5);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/category-rules/?preference=5');
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchCategoryRules(5)).rejects.toThrow('Failed to load consent category rules');
    });
  });

  describe('upsertCategoryRule', () => {
    it('sends POST to /api/consent/category-rules/', async () => {
      const data = { id: 10, preference: 5, category: 2, mode: 'everyone' };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await upsertCategoryRule({ preference: 5, category: 2, mode: 'everyone' });

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/category-rules/', {
        method: 'POST',
        body: JSON.stringify({ preference: 5, category: 2, mode: 'everyone' }),
      });
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(upsertCategoryRule({ preference: 5, category: 2 })).rejects.toThrow(
        'Failed to save consent category rule'
      );
    });
  });

  describe('deleteCategoryRule', () => {
    it('sends DELETE to /api/consent/category-rules/{id}/', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockEmptyOk());

      await deleteCategoryRule(10);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/category-rules/10/', {
        method: 'DELETE',
      });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(deleteCategoryRule(10)).rejects.toThrow(
        'Failed to delete consent category rule'
      );
    });
  });

  // -------------------------------------------------------------------------
  // Whitelist
  // -------------------------------------------------------------------------

  describe('fetchWhitelist', () => {
    it('calls /api/consent/whitelist/ with owner_tenure and category filters', async () => {
      const data = { count: 0, results: [] };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await fetchWhitelist(42, 3);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/whitelist/?owner_tenure=42&category=3');
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchWhitelist(42, 3)).rejects.toThrow('Failed to load consent whitelist');
    });
  });

  describe('addWhitelist', () => {
    it('sends POST to /api/consent/whitelist/', async () => {
      const data = {
        id: 1,
        owner_tenure: 42,
        allowed_tenure: 7,
        category: 3,
        added_at: '2026-01-01T00:00:00Z',
      };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await addWhitelist({ owner_tenure: 42, allowed_tenure: 7, category: 3 });

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/whitelist/', {
        method: 'POST',
        body: JSON.stringify({ owner_tenure: 42, allowed_tenure: 7, category: 3 }),
      });
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(
        addWhitelist({ owner_tenure: 42, allowed_tenure: 7, category: 3 })
      ).rejects.toThrow('Failed to add whitelist entry');
    });
  });

  describe('removeWhitelist', () => {
    it('sends DELETE to /api/consent/whitelist/{id}/', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockEmptyOk());

      await removeWhitelist(1);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/whitelist/1/', { method: 'DELETE' });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(removeWhitelist(1)).rejects.toThrow('Failed to remove whitelist entry');
    });
  });

  // -------------------------------------------------------------------------
  // Blacklist (#1698)
  // -------------------------------------------------------------------------

  describe('fetchBlacklist', () => {
    it('calls /api/consent/blacklist/ with owner_tenure and category filters', async () => {
      const data = { count: 0, results: [] };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await fetchBlacklist(42, 3);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/blacklist/?owner_tenure=42&category=3');
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(fetchBlacklist(42, 3)).rejects.toThrow('Failed to load consent blacklist');
    });
  });

  describe('addBlacklist', () => {
    it('sends POST to /api/consent/blacklist/', async () => {
      const data = {
        id: 1,
        owner_tenure: 42,
        blocked_tenure: 7,
        category: 3,
        added_at: '2026-01-01T00:00:00Z',
      };
      vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

      const result = await addBlacklist({ owner_tenure: 42, blocked_tenure: 7, category: 3 });

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/blacklist/', {
        method: 'POST',
        body: JSON.stringify({ owner_tenure: 42, blocked_tenure: 7, category: 3 }),
      });
      expect(result).toEqual(data);
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(
        addBlacklist({ owner_tenure: 42, blocked_tenure: 7, category: 3 })
      ).rejects.toThrow('Failed to add blacklist entry');
    });
  });

  describe('removeBlacklist', () => {
    it('sends DELETE to /api/consent/blacklist/{id}/', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockEmptyOk());

      await removeBlacklist(1);

      expect(apiFetch).toHaveBeenCalledWith('/api/consent/blacklist/1/', { method: 'DELETE' });
    });

    it('throws on error response', async () => {
      vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

      await expect(removeBlacklist(1)).rejects.toThrow('Failed to remove blacklist entry');
    });
  });
});
