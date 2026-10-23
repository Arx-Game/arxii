/** Graph authoring fetch wrappers: a 409 surfaces the server's plain message. */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/evennia_replacements/api';

import { deleteMissionNode, getGraphCheck } from '../api';

describe('graph authoring api', () => {
  it('deleteMissionNode throws the 409 detail as the error message', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'A mission run has recorded this node.' }), {
        status: 409,
      })
    );
    await expect(deleteMissionNode(4)).rejects.toThrow('A mission run has recorded this node.');
  });

  it('getGraphCheck unwraps the problems list', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify({ problems: [] }), { status: 200 })
    );
    await expect(getGraphCheck(3)).resolves.toEqual([]);
  });
});
