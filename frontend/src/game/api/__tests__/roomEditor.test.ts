/**
 * Tests for the `edit_room` dispatch helper (#1470, fixed for #3155).
 *
 * ``DispatchActionView`` returns HTTP 200 even for a business-rule rejection
 * (e.g. editing a room the actor doesn't own) — the wire signal is the
 * response body's ``success`` field (``DispatchResultSerializer``), not
 * ``res.ok``. This exercises the REAL ``editRoom`` helper against a mocked
 * ``apiFetch`` returning that exact shape, to catch a regression where only
 * ``res.ok`` was checked (a rejected edit would then read as a resolved
 * Promise instead of throwing) — mirrors ``api.treasury.test.ts``.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { editRoom } from '../roomEditor';

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

describe('game/api/roomEditor editRoom', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('resolves with the server message on success: true', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ success: true, message: 'Room updated.' })
    );

    const result = await editRoom(42, { name: 'The Solar' });

    expect(result).toBe('Room updated.');
  });

  it('throws with the server message on success: false (HTTP 200)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDispatchResponse({ ok: true, success: false, message: "You don't own this room." })
    );

    await expect(editRoom(42, { name: 'The Solar' })).rejects.toThrow("You don't own this room.");
  });

  it('throws a fallback message when the body has no message', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockDispatchResponse({ success: false, message: null }));

    await expect(editRoom(42, { name: 'The Solar' })).rejects.toThrow('Failed to update the room.');
  });
});
