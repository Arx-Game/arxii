import { act, renderHook, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';

vi.mock('../queries', () => ({
  reactToInteraction: vi.fn(),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 7,
        active_persona_id: 7,
      },
    ],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

import { useKudos } from './useKudos';
import { reactToInteraction } from '../queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return createElement(QueryClientProvider, { client }, children);
}

describe('useKudos (#2031, menu item since #4128)', () => {
  it('POSTs the exact kudos body via reactToInteraction', async () => {
    vi.mocked(reactToInteraction).mockResolvedValue(undefined);
    const { result } = renderHook(() => useKudos('1', 99), { wrapper });

    act(() => result.current.give());

    await waitFor(() => {
      expect(reactToInteraction).toHaveBeenCalledWith({
        persona_id: 7,
        interaction_id: 99,
        kind: 'kudos',
        choice: 'kudos',
      });
    });
  });

  it('cannot give without a resolved persona', () => {
    vi.mocked(useMyRosterEntriesQuery).mockReturnValueOnce({ data: [] } as never);
    const { result } = renderHook(() => useKudos('1', 99), { wrapper });
    expect(result.current.canGive).toBe(false);
  });
});
