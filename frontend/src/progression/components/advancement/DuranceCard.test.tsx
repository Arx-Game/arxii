/**
 * DuranceCard tests (#3045). Mocks `@/progression/queries` (status/convene/join)
 * and `@/magic/queries` (the existing PathIntent seam, #954) — no msw.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { DuranceCard } from './DuranceCard';
import type {
  useConveneDuranceMutation,
  useDuranceStatusQuery,
  useJoinDuranceSessionMutation,
} from '@/progression/queries';
import type { useClearPathIntent, useDeclarePathIntent, usePathIntent } from '@/magic/queries';
import type { DuranceStatus } from '@/progression/types';

vi.mock('@/progression/queries', () => ({
  useDuranceStatusQuery: vi.fn(),
  useConveneDuranceMutation: vi.fn(),
  useJoinDuranceSessionMutation: vi.fn(),
}));

vi.mock('@/magic/queries', () => ({
  usePathIntent: vi.fn(),
  useDeclarePathIntent: vi.fn(),
  useClearPathIntent: vi.fn(),
}));

import * as progressionQueries from '@/progression/queries';
import * as magicQueries from '@/magic/queries';

const notReadyStatus: DuranceStatus = {
  level: 2,
  target_level: 3,
  is_tier_boundary: false,
  unlock_gate: {
    has_class_level: true,
    advancement_authored: true,
    requirements_met: false,
    failed_requirements: ['Requires 50 Legend'],
    purchased: false,
    xp_cost: 100,
    class_level_unlock_id: 42,
    ready: false,
  },
  eligible_paths: [{ id: 9, name: 'Path of Steel' }],
  intent: null,
  site_present: false,
};

const readyStatus: DuranceStatus = {
  ...notReadyStatus,
  unlock_gate: {
    ...notReadyStatus.unlock_gate!,
    requirements_met: true,
    purchased: true,
    xp_cost: null,
    ready: true,
  },
  site_present: true,
};

function setupMocks(options?: {
  status?: DuranceStatus;
  isLoading?: boolean;
  declaredPathId?: number | null;
  conveneOverrides?: Record<string, unknown>;
  joinOverrides?: Record<string, unknown>;
}) {
  const conveneMutate = vi.fn();
  const joinMutate = vi.fn();
  const declareMutate = vi.fn();
  const clearMutate = vi.fn();

  vi.mocked(progressionQueries.useDuranceStatusQuery).mockReturnValue({
    data: options?.status ?? notReadyStatus,
    isLoading: options?.isLoading ?? false,
    error: null,
  } as unknown as ReturnType<typeof useDuranceStatusQuery>);

  vi.mocked(progressionQueries.useConveneDuranceMutation).mockReturnValue({
    mutate: conveneMutate,
    isPending: false,
    ...options?.conveneOverrides,
  } as unknown as ReturnType<typeof useConveneDuranceMutation>);

  vi.mocked(progressionQueries.useJoinDuranceSessionMutation).mockReturnValue({
    mutate: joinMutate,
    isPending: false,
    ...options?.joinOverrides,
  } as unknown as ReturnType<typeof useJoinDuranceSessionMutation>);

  vi.mocked(magicQueries.usePathIntent).mockReturnValue({
    data: {
      intent:
        options?.declaredPathId != null
          ? { id: 1, intended_path: { id: options.declaredPathId }, declared_at: '' }
          : null,
    },
  } as unknown as ReturnType<typeof usePathIntent>);

  vi.mocked(magicQueries.useDeclarePathIntent).mockReturnValue({
    mutate: declareMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDeclarePathIntent>);

  vi.mocked(magicQueries.useClearPathIntent).mockReturnValue({
    mutate: clearMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useClearPathIntent>);

  return { conveneMutate, joinMutate, declareMutate, clearMutate };
}

describe('DuranceCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows level/target and unmet requirements', () => {
    setupMocks();
    renderWithProviders(<DuranceCard characterId={10} />);
    expect(screen.getByText('Level 2, seeking 3')).toBeInTheDocument();
    expect(screen.getByTestId('durance-unlock-gate')).toHaveTextContent('Requires 50 Legend');
  });

  it('shows a "cost unset" marker for the unpurchased zero-cost unlock case', () => {
    setupMocks({
      status: { ...notReadyStatus, unlock_gate: { ...notReadyStatus.unlock_gate!, xp_cost: 0 } },
    });
    renderWithProviders(<DuranceCard characterId={10} />);
    expect(screen.getByTestId('durance-cost-unset')).toBeInTheDocument();
  });

  it('shows the tier-boundary message and no unlock gate at a tier boundary', () => {
    setupMocks({ status: { ...notReadyStatus, is_tier_boundary: true } });
    renderWithProviders(<DuranceCard characterId={10} />);
    expect(screen.getByTestId('durance-tier-boundary')).toBeInTheDocument();
    expect(screen.queryByTestId('durance-unlock-gate')).not.toBeInTheDocument();
  });

  it('shows ready messaging when requirements are met and the unlock is purchased', () => {
    setupMocks({ status: readyStatus });
    renderWithProviders(<DuranceCard characterId={10} />);
    expect(screen.getByTestId('durance-ready')).toHaveTextContent('Ready to advance to level 3');
  });

  it('declaring an eligible path calls declare with characterId + pathId', async () => {
    const { declareMutate } = setupMocks();
    renderWithProviders(<DuranceCard characterId={10} />);

    await userEvent.click(screen.getByTestId('durance-path-9'));

    expect(declareMutate).toHaveBeenCalledWith({ characterId: 10, pathId: 9 });
  });

  it('shows a Clear button and clears with the characterId when a path is declared', async () => {
    const { clearMutate } = setupMocks({ declaredPathId: 9 });
    renderWithProviders(<DuranceCard characterId={10} />);

    await userEvent.click(screen.getByTestId('durance-clear-intent'));

    expect(clearMutate).toHaveBeenCalledWith(10);
  });

  it('the convene button is disabled when no training site is present', () => {
    setupMocks();
    renderWithProviders(<DuranceCard characterId={10} />);
    expect(screen.getByTestId('durance-convene-button')).toBeDisabled();
  });

  it('convening dispatches the convene mutation and reveals the testament form on success', async () => {
    const { conveneMutate } = setupMocks({ status: readyStatus });
    conveneMutate.mockImplementation((_vars, opts) => {
      opts?.onSuccess?.({ session_id: 55 });
    });
    renderWithProviders(<DuranceCard characterId={10} />);

    await userEvent.click(screen.getByTestId('durance-convene-button'));

    expect(conveneMutate).toHaveBeenCalled();
    expect(screen.getByTestId('durance-testament-input')).toBeInTheDocument();
  });

  it('joining sends testament + session id to the join mutation', async () => {
    const { conveneMutate, joinMutate } = setupMocks({ status: readyStatus });
    conveneMutate.mockImplementation((_vars, opts) => {
      opts?.onSuccess?.({ session_id: 55 });
    });
    renderWithProviders(<DuranceCard characterId={10} />);

    await userEvent.click(screen.getByTestId('durance-convene-button'));
    await userEvent.type(screen.getByTestId('durance-testament-input'), 'I stand ready.');
    await userEvent.click(screen.getByTestId('durance-join-button'));

    expect(joinMutate).toHaveBeenCalledWith(
      { sessionId: 55, participantKwargs: { testament: 'I stand ready.' } },
      expect.anything()
    );
  });
});
