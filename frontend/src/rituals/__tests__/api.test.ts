/**
 * Rituals API Tests
 *
 * Tests for api.ts error handling, specifically performRitual's typed error detail parsing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { performRitual } from '../api';
import type { PerformRitualRequest } from '../types';

// Mock apiFetch
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';

describe('Rituals API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('performRitual', () => {
    it('throws error with typed detail from JSON response', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: { capstone_id: 7 },
      };

      const detailMessage = 'Character does not meet requirements';
      vi.mocked(apiFetch).mockResolvedValue(
        new Response(JSON.stringify({ detail: detailMessage }), {
          status: 400,
          statusText: 'Bad Request',
        })
      );

      try {
        await performRitual(mockRequest);
        expect.fail('Should have thrown error');
      } catch (err) {
        expect(err).toBeInstanceOf(Error);
        expect((err as Error).message).toBe(detailMessage);
      }
    });

    it('throws error with another typed detail example', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 2,
        character_sheet_id: 99,
        kwargs: {},
      };

      const detailMessage = 'Insufficient anima';
      vi.mocked(apiFetch).mockResolvedValue(
        new Response(JSON.stringify({ detail: detailMessage }), {
          status: 403,
          statusText: 'Forbidden',
        })
      );

      try {
        await performRitual(mockRequest);
      } catch (err) {
        expect((err as Error).message).toBe(detailMessage);
      }
    });

    it('falls back to generic message when response is non-JSON', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: {},
      };

      vi.mocked(apiFetch).mockResolvedValue(
        new Response('Internal Server Error', {
          status: 500,
          statusText: 'Internal Server Error',
          headers: { 'Content-Type': 'text/plain' },
        })
      );

      try {
        await performRitual(mockRequest);
      } catch (err) {
        expect((err as Error).message).toBe('Failed to perform ritual');
      }
    });

    it('falls back to generic message when detail field is empty string', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: {},
      };

      vi.mocked(apiFetch).mockResolvedValue(
        new Response(JSON.stringify({ detail: '' }), {
          status: 400,
          statusText: 'Bad Request',
        })
      );

      try {
        await performRitual(mockRequest);
      } catch (err) {
        expect((err as Error).message).toBe('Failed to perform ritual');
      }
    });

    it('falls back to generic message when detail field is missing', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: {},
      };

      vi.mocked(apiFetch).mockResolvedValue(
        new Response(JSON.stringify({ some_other_field: 'value' }), {
          status: 400,
          statusText: 'Bad Request',
        })
      );

      try {
        await performRitual(mockRequest);
      } catch (err) {
        expect((err as Error).message).toBe('Failed to perform ritual');
      }
    });

    it('succeeds with valid response', async () => {
      const mockRequest: PerformRitualRequest = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: { capstone_id: 7 },
      };

      const mockResponse = {
        ritual_id: 1,
        execution_kind: 'SERVICE',
        result: { success: true },
      };

      vi.mocked(apiFetch).mockResolvedValue(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          statusText: 'OK',
        })
      );

      const result = await performRitual(mockRequest);
      expect(result).toEqual(mockResponse);
    });
  });
});
