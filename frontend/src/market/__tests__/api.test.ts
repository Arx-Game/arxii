/**
 * Tests for the market REGISTRY dispatch helper (#2066, fixed for #3155).
 *
 * ``DispatchActionView`` returns HTTP 200 even for a business-rule rejection
 * (e.g. insufficient funds) — the wire signal is the response body's
 * ``success`` field (``DispatchResultSerializer``), not ``res.ok``. This
 * exercises the REAL ``dispatchMarketAction`` helper against a mocked
 * ``apiFetch`` returning that exact shape, to catch a regression where only
 * ``res.ok`` was checked (a rejected purchase would then read as a resolved
 * Promise instead of throwing) — mirrors ``api.treasury.test.ts``.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { dispatchMarketAction } from '../api';

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

describe('market/api dispatchMarketAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('resolves with the server message on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ success: true, message: 'Purchase complete.' })
    );

    const result = await dispatchMarketAction(42, 'market_buy_stock', { listing_id: 1 });

    expect(result).toBe('Purchase complete.');
  });

  it('throws with the server message on success: false (HTTP 200)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ ok: true, success: false, message: 'You cannot afford that.' })
    );

    await expect(dispatchMarketAction(42, 'market_buy_stock', { listing_id: 1 })).rejects.toThrow(
      'You cannot afford that.'
    );
  });

  it('throws a fallback message when the body has no message', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockDispatchResponse({ success: false, message: null }));

    await expect(dispatchMarketAction(42, 'market_buy_stock', { listing_id: 1 })).rejects.toThrow(
      'The action failed.'
    );
  });
});
