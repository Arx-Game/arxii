/** Graph authoring fetch wrappers: a 409 surfaces the server's plain message. */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/evennia_replacements/api';

import { copyNode, deleteMissionNode, getGraphCheck, listMissionRoutes } from '../api';

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

  it('listMissionRoutes reads every page of a mission, not just the first', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ next: '/api/missions/routes/?page=2', results: [{ id: 1 }] }))
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ next: null, results: [{ id: 2 }] })));
    const page = await listMissionRoutes({ template: 3 });
    expect(page.results.map((r) => r.id)).toEqual([1, 2]);
    expect(page.next).toBeNull();
  });

  it('copyNode throws the server detail when the key is taken', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'Another node in this mission already uses that key.' }),
        { status: 400 }
      )
    );
    await expect(copyNode(4, { new_key: 'gate' })).rejects.toThrow(
      'Another node in this mission already uses that key.'
    );
  });
});
