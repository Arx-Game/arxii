/**
 * Tests for the GroupStoryRequest dispatch helpers (#2119, fixed for #3155).
 *
 * ``DispatchActionView`` returns HTTP 200 even for a business-rule rejection
 * (e.g. requesting a GM for a covenant that already has an open request) —
 * the wire signal is the response body's ``success`` field
 * (``DispatchResultSerializer``), not ``res.ok``. These tests exercise the
 * REAL ``requestGMForCovenant``/``withdrawGroupStoryRequest`` helpers against
 * a mocked ``apiFetch`` returning that exact shape, to catch a regression
 * where only ``res.ok`` was checked (a rejected request would then read as a
 * resolved Promise instead of throwing) — mirrors ``api.treasury.test.ts``.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { requestGMForCovenant, withdrawGroupStoryRequest } from '../api';

function mockDispatchResponse(body: {
  success: boolean | null;
  message?: string | null;
  ok?: boolean;
}) {
  return {
    ok: body.ok ?? true,
    json: () =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: body.success,
        message: body.message ?? null,
        data: null,
      }),
  } as Response;
}

describe('covenants/api group-story-request dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('requestGMForCovenant resolves on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ success: true, message: 'GM request posted.' })
    );

    const result = await requestGMForCovenant(42, 7, 'Seeking a GM!');

    expect(result).toBe('GM request posted.');
  });

  it('requestGMForCovenant throws with the server message on success: false (HTTP 200)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({
        ok: true,
        success: false,
        message: 'This covenant already has an open GM request.',
      })
    );

    await expect(requestGMForCovenant(42, 7, 'Seeking a GM!')).rejects.toThrow(
      'This covenant already has an open GM request.'
    );
  });

  it('withdrawGroupStoryRequest resolves on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ success: true, message: 'GM request withdrawn.' })
    );

    const result = await withdrawGroupStoryRequest(42, 5);

    expect(result).toBe('GM request withdrawn.');
  });

  it('withdrawGroupStoryRequest throws with the server message on success: false (HTTP 200)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({
        ok: true,
        success: false,
        message: 'Only the requester may withdraw this request.',
      })
    );

    await expect(withdrawGroupStoryRequest(42, 5)).rejects.toThrow(
      'Only the requester may withdraw this request.'
    );
  });

  it('withdrawGroupStoryRequest throws a fallback message when the body has no message', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockDispatchResponse({ success: false, message: null }));

    await expect(withdrawGroupStoryRequest(42, 5)).rejects.toThrow(
      'Failed to withdraw the GM request.'
    );
  });
});
