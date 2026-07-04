/**
 * TreasuredSignoffPrompt tests (#1771) — pre-scene sign-off prompt. Appears
 * only when the viewer has a treasured subject that lacks an active
 * TreasuredSignoff for the given beat (i.e. "requires_signoff"); grants and
 * withdrawals both call the TreasuredSignoff endpoints.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TreasuredSignoffPrompt } from '../components/TreasuredSignoffPrompt';

vi.mock('../queries', () => ({
  useTreasuredSubjects: vi.fn(),
  useTreasuredSignoffs: vi.fn(),
  useGrantTreasuredSignoff: vi.fn(),
  useWithdrawTreasuredSignoff: vi.fn(),
}));

import * as queries from '../queries';

const SUBJECT_UNSIGNED = {
  id: 10,
  owner: 1,
  subject_kind: 'npc_fate' as const,
  subject_label: 'Captain Elara',
  detail: '',
  visibility_mode: 'private' as const,
  visible_to_tenures: [],
  visible_to_groups: [],
  excluded_tenures: [],
  created_at: '2026-01-01T00:00:00Z',
};

const SUBJECT_SIGNED = { ...SUBJECT_UNSIGNED, id: 11, subject_label: 'The old windmill' };

const ACTIVE_SIGNOFF_FOR_11 = {
  id: 99,
  beat: 5,
  player_data: 1,
  treasured_subject: 11,
  granted_at: '2026-01-02T00:00:00Z',
  withdrawn_at: null,
  active: true,
};

function mockMutations() {
  const grantMutate = vi.fn();
  const withdrawMutate = vi.fn();
  vi.mocked(queries.useGrantTreasuredSignoff).mockReturnValue({
    mutate: grantMutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useWithdrawTreasuredSignoff).mockReturnValue({
    mutate: withdrawMutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { grantMutate, withdrawMutate };
}

describe('TreasuredSignoffPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the tenure has no treasured subjects', () => {
    mockMutations();
    vi.mocked(queries.useTreasuredSubjects).mockReturnValue({
      data: { count: 0, results: [] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    vi.mocked(queries.useTreasuredSignoffs).mockReturnValue({
      data: { count: 0, results: [] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const { container } = renderWithProviders(<TreasuredSignoffPrompt beatId={5} tenureId={1} />);

    expect(container.innerHTML).toBe('');
  });

  it('appears when a treasured subject requires signoff (no active grant yet)', async () => {
    mockMutations();
    vi.mocked(queries.useTreasuredSubjects).mockReturnValue({
      data: { count: 1, results: [SUBJECT_UNSIGNED] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    vi.mocked(queries.useTreasuredSignoffs).mockReturnValue({
      data: { count: 0, results: [] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderWithProviders(<TreasuredSignoffPrompt beatId={5} tenureId={1} />);

    await waitFor(() => {
      expect(screen.getByText('Captain Elara')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /sign off/i })).toBeInTheDocument();
  });

  it('clicking "Sign off" grants a signoff for the beat + subject', async () => {
    const { grantMutate } = mockMutations();
    vi.mocked(queries.useTreasuredSubjects).mockReturnValue({
      data: { count: 1, results: [SUBJECT_UNSIGNED] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    vi.mocked(queries.useTreasuredSignoffs).mockReturnValue({
      data: { count: 0, results: [] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderWithProviders(<TreasuredSignoffPrompt beatId={5} tenureId={1} />);

    const button = await screen.findByRole('button', { name: /sign off/i });
    await userEvent.click(button);

    expect(grantMutate).toHaveBeenCalledWith({ beat: 5, treasured_subject: 10 });
  });

  it('shows an active signoff with a withdraw control, and does not prompt for it again', async () => {
    mockMutations();
    vi.mocked(queries.useTreasuredSubjects).mockReturnValue({
      data: { count: 1, results: [SUBJECT_SIGNED] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    vi.mocked(queries.useTreasuredSignoffs).mockReturnValue({
      data: { count: 1, results: [ACTIVE_SIGNOFF_FOR_11] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderWithProviders(<TreasuredSignoffPrompt beatId={5} tenureId={1} />);

    await waitFor(() => {
      expect(screen.getByText('The old windmill')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /sign off/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /withdraw/i })).toBeInTheDocument();
  });

  it('clicking "Withdraw" withdraws the existing signoff', async () => {
    const { withdrawMutate } = mockMutations();
    vi.mocked(queries.useTreasuredSubjects).mockReturnValue({
      data: { count: 1, results: [SUBJECT_SIGNED] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    vi.mocked(queries.useTreasuredSignoffs).mockReturnValue({
      data: { count: 1, results: [ACTIVE_SIGNOFF_FOR_11] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderWithProviders(<TreasuredSignoffPrompt beatId={5} tenureId={1} />);

    const button = await screen.findByRole('button', { name: /withdraw/i });
    await userEvent.click(button);

    expect(withdrawMutate).toHaveBeenCalledWith({ id: 99, beat: 5 });
  });
});
