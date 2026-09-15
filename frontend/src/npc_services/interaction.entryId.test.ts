/**
 * #3479 Task 5: the NPC interaction client sends the tab's browsing
 * identity as `entry_id` in the request BODY (unlike missions' query param;
 * the npc-services serializers take it as a body field). Null/undefined
 * omits the field so the server falls back to the durable selection.
 */
import { vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

import { endInteraction, resolveOffer, startInteraction } from './interaction';

function sentBody(callIndex = 0): Record<string, unknown> {
  const init = apiFetch.mock.calls[callIndex][1] as { body: string };
  return JSON.parse(init.body) as Record<string, unknown>;
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
});

describe('interaction client entry_id threading (#3479)', () => {
  it('startInteraction includes entry_id in the body when given', async () => {
    await startInteraction(12, 5);
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/npc-services/interactions/start/',
      expect.anything()
    );
    expect(sentBody()).toEqual({ role_id: 12, entry_id: 5 });
  });

  it('startInteraction omits entry_id entirely when null', async () => {
    await startInteraction(12, null);
    expect(sentBody()).toEqual({ role_id: 12 });
  });

  it('resolveOffer includes entry_id when given, omits when absent', async () => {
    await resolveOffer(44, 5);
    expect(sentBody(0)).toEqual({ offer_id: 44, entry_id: 5 });
    await resolveOffer(44);
    expect(sentBody(1)).toEqual({ offer_id: 44 });
  });

  it('endInteraction sends an entry_id-only body when given, empty when absent', async () => {
    await endInteraction(5);
    expect(sentBody(0)).toEqual({ entry_id: 5 });
    await endInteraction();
    expect(sentBody(1)).toEqual({});
  });
});
