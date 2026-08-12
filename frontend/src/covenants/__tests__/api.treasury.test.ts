/**
 * Tests for the covenant treasury dispatch helpers (#2992).
 *
 * ``DispatchActionView`` returns HTTP 200 even for a business-rule rejection
 * (e.g. a rank-unauthorized withdrawal) — the wire signal is the response
 * body's ``success`` field (``DispatchResultSerializer``), not ``res.ok``.
 * These tests exercise the REAL ``depositCovenantFunds``/``withdrawCovenantFunds``
 * helpers against a mocked ``apiFetch`` returning that exact shape, to catch a
 * regression where only ``res.ok`` was checked (a rejected withdrawal would
 * then read as a resolved Promise instead of throwing).
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { depositCovenantFunds, withdrawCovenantFunds } from '../api';

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

describe('covenants/api treasury dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('depositCovenantFunds resolves on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({
        success: true,
        message: "You add your coin to the covenant's coffers.",
      })
    );

    const result = await depositCovenantFunds(42, 7, 50);

    expect(result).toBe("You add your coin to the covenant's coffers.");
  });

  it('depositCovenantFunds throws with the server message on success: false', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({
        success: false,
        message: 'Only an active covenant member may use the covenant treasury.',
      })
    );

    await expect(depositCovenantFunds(42, 7, 50)).rejects.toThrow(
      'Only an active covenant member may use the covenant treasury.'
    );
  });

  it('withdrawCovenantFunds resolves on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ success: true, message: "You draw coin from the covenant's coffers." })
    );

    const result = await withdrawCovenantFunds(42, 7, 25);

    expect(result).toBe("You draw coin from the covenant's coffers.");
  });

  it('withdrawCovenantFunds throws with the server message on success: false (HTTP 200)', async () => {
    // The regression case: HTTP 200, but a rank-unauthorized rejection.
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({
        ok: true,
        success: false,
        message: 'Your rank does not carry the authority to spend from the covenant treasury.',
      })
    );

    await expect(withdrawCovenantFunds(42, 7, 25)).rejects.toThrow(
      'Your rank does not carry the authority to spend from the covenant treasury.'
    );
  });

  it('withdrawCovenantFunds throws a fallback message when the body has no message', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockDispatchResponse({ success: false, message: null }));

    await expect(withdrawCovenantFunds(42, 7, 25)).rejects.toThrow(
      'Failed to withdraw covenant funds.'
    );
  });
});
