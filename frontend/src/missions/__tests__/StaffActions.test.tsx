/**
 * E6 — StaffActionsCard + FlavorRewriteCard interaction tests.
 *
 * Mocks the queries module so the components render against fixed
 * data. Verifies access-tier flip wiring, copy/assign open-form
 * toggles, and the flagged-content list aggregates the three
 * nested-resource queries with the needs_rewrite=true filter.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import type { MissionTemplate } from '../types';

const FAKE_TEMPLATE: MissionTemplate = {
  id: 11,
  slug: 'foo',
  name: 'Foo Mission',
  summary: 'lore',
  level_band_min: 1,
  level_band_max: 5,
  risk_tier: 1,
  cooldown: '0',
  arc_scope: 'global',
  access_tier: 'staff_only',
} as MissionTemplate;

const patchMutate = vi.fn();
const copyMutateAsync = vi.fn().mockResolvedValue({ ...FAKE_TEMPLATE, slug: 'bar' });
const assignMutateAsync = vi.fn().mockResolvedValue({ id: 99 });

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    usePatchMissionTemplate: () => ({ mutate: patchMutate, isPending: false }),
    useCopyTemplate: () => ({
      mutateAsync: copyMutateAsync,
      isPending: false,
      error: null,
    }),
    useAssignMission: () => ({
      mutateAsync: assignMutateAsync,
      isPending: false,
      error: null,
    }),
    useMissionNodes: () => ({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [{ id: 1, template: 11, key: 'broken-node' }],
      },
      isLoading: false,
    }),
    useMissionOptions: () => ({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    }),
    useMissionRoutes: () => ({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    }),
  };
});

import { FlavorRewriteCard } from '../components/FlavorRewriteCard';
import { StaffActionsCard } from '../components/StaffActionsCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StaffActionsCard', () => {
  beforeEach(() => {
    patchMutate.mockClear();
    copyMutateAsync.mockClear();
    assignMutateAsync.mockClear();
  });

  it('renders Publish when current tier is staff_only', () => {
    render(withProviders(<StaffActionsCard template={FAKE_TEMPLATE} />));
    expect(screen.getByTestId('access-tier-flip')).toHaveTextContent('Publish');
  });

  it('flips access tier when Publish is clicked', async () => {
    const user = userEvent.setup();
    render(withProviders(<StaffActionsCard template={FAKE_TEMPLATE} />));
    await user.click(screen.getByTestId('access-tier-flip'));
    expect(patchMutate).toHaveBeenCalledWith({
      slug: 'foo',
      body: { access_tier: 'open' },
    });
  });

  it('opens the copy form and POSTs new_slug/new_name on submit', async () => {
    const user = userEvent.setup();
    render(withProviders(<StaffActionsCard template={FAKE_TEMPLATE} />));
    await user.click(screen.getByRole('button', { name: /copy…/i }));
    await user.type(screen.getByLabelText('New slug'), 'foo-v2');
    await user.type(screen.getByLabelText('New name'), 'Foo Mission v2');
    await user.click(screen.getByRole('button', { name: /^copy$/i }));
    expect(copyMutateAsync).toHaveBeenCalledWith({
      slug: 'foo',
      new_slug: 'foo-v2',
      new_name: 'Foo Mission v2',
    });
  });

  it('opens the assign form and POSTs the character pk', async () => {
    const user = userEvent.setup();
    render(withProviders(<StaffActionsCard template={FAKE_TEMPLATE} />));
    await user.click(screen.getByRole('button', { name: /assign…/i }));
    await user.type(screen.getByLabelText('Character ObjectDB pk'), '42');
    await user.click(screen.getByRole('button', { name: /^assign$/i }));
    expect(assignMutateAsync).toHaveBeenCalledWith({ slug: 'foo', character: 42 });
  });
});

describe('FlavorRewriteCard', () => {
  it('shows the rewrite count badge with total flagged children', () => {
    render(withProviders(<FlavorRewriteCard template={FAKE_TEMPLATE} />));
    expect(screen.getByTestId('rewrite-count')).toHaveTextContent('1');
    expect(screen.getByText('broken-node')).toBeInTheDocument();
  });
});
