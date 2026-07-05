/**
 * TriggerGiversPage — typeclass-constrained target picker tests (#882).
 *
 * Mocks ../queries (giver CRUD hooks) and the two new ../api search/resolve
 * functions, verifying the raw pk input is gone and EntitySearchField drives
 * `target` via search-and-select instead.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import type { MissionGiver } from '../types';

const FAKE_GIVER: MissionGiver = {
  id: 3,
  name: 'Notice Board',
  giver_kind: 'room_trigger',
  target: 7,
  org: null,
  is_active: true,
  templates: [],
  is_publishable: true,
} as MissionGiver;

const patchMutate = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useGivers: () => ({
      data: { count: 1, next: null, previous: null, results: [FAKE_GIVER] },
      isLoading: false,
    }),
    useCreateGiver: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useDeleteGiver: () => ({ mutate: vi.fn(), isPending: false }),
    useMissionTemplates: () => ({
      data: { count: 0, next: null, previous: null, results: [] },
    }),
    usePatchGiver: () => ({ mutate: patchMutate, isPending: false, isError: false }),
  };
});

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    searchMissionGiverTargets: vi
      .fn()
      .mockResolvedValue([{ id: 9, name: 'Chapel Steps', hint: 'Test District' }]),
    resolveMissionGiverTarget: vi
      .fn()
      .mockResolvedValue({ id: 7, name: 'Notice Board Plaza', hint: 'Test District' }),
  };
});

import { TriggerGiversPage } from '../pages/TriggerGiversPage';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('TriggerGiversPage target picker', () => {
  beforeEach(() => {
    patchMutate.mockClear();
  });

  it('has no raw numeric target-id input', () => {
    render(withProviders(<TriggerGiversPage />));
    expect(screen.queryByPlaceholderText('Room / object pk')).not.toBeInTheDocument();
  });

  it('resolves and displays the existing target name on load', async () => {
    render(withProviders(<TriggerGiversPage />));
    expect(await screen.findByDisplayValue('Notice Board Plaza')).toBeInTheDocument();
  });

  it('searching and selecting a new target saves its id, not a name', async () => {
    const user = userEvent.setup();
    render(withProviders(<TriggerGiversPage />));

    const field = await screen.findByLabelText('Target');
    await user.clear(field);
    await user.type(field, 'Chapel');

    const option = await screen.findByText(/Chapel Steps/);
    await user.click(option);

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(patchMutate).toHaveBeenCalledWith({
      id: 3,
      body: expect.objectContaining({ target: 9 }),
    });
  });
});
