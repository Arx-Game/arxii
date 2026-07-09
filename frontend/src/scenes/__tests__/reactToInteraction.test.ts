import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { reactToInteraction } from '../queries';

function mockOkResponse() {
  return { ok: true, status: 200, json: () => Promise.resolve({}) } as Response;
}

function mockDetailErrorResponse(detail: string[]) {
  return { ok: false, status: 400, json: () => Promise.resolve({ detail }) } as Response;
}

describe('reactToInteraction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('POSTs to /api/reaction-windows/react-to-interaction/ with the exact kudos body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse());

    await reactToInteraction({
      persona_id: 7,
      interaction_id: 99,
      kind: 'kudos',
      choice: 'kudos',
    });

    expect(apiFetch).toHaveBeenCalledWith('/api/reaction-windows/react-to-interaction/', {
      method: 'POST',
      body: JSON.stringify({
        persona_id: 7,
        interaction_id: 99,
        kind: 'kudos',
        choice: 'kudos',
      }),
    });
  });

  it('throws with the first message from a 400 detail array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      mockDetailErrorResponse(['Already gave kudos on this pose.'])
    );

    await expect(
      reactToInteraction({ persona_id: 7, interaction_id: 99, kind: 'kudos', choice: 'kudos' })
    ).rejects.toThrow('Already gave kudos on this pose.');
  });
});
