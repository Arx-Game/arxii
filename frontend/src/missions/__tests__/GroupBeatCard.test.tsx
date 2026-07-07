/**
 * #2049 — GroupBeatCard component tests.
 *
 * Phase rendering (pick/vote/expired), ballot submission, and the resolved
 * view. Mirrors the StoryTray.test.tsx mocking pattern (vi.mock queries).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import type { GroupBeatResult, ResolvedBeat } from '../types';

const PICK_BEAT: GroupBeatResult = {
  group_beat: {
    instance_id: 7,
    node_key: 'entry',
    flavor_text: 'PLACEHOLDER the crossroads.',
    conflict_mode: 'group_vote',
    phase: 'pick',
    options: [
      {
        option_id: 31,
        approach_id: null,
        label: 'PLACEHOLDER take the path',
        kind: 'branch',
        check_type_name: null,
        base_risk: 0,
      },
    ],
    ballots: [
      { character_id: 1, character_name: 'Hero', picked_option_id: null, voted_option_id: null },
      { character_id: 2, character_name: 'Companion', picked_option_id: 31, voted_option_id: null },
    ],
    expires_at: null,
  },
  resolved: null,
};

const VOTE_BEAT: GroupBeatResult = {
  group_beat: {
    ...PICK_BEAT.group_beat!,
    phase: 'vote',
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    ballots: [
      { character_id: 1, character_name: 'Hero', picked_option_id: 31, voted_option_id: null },
      { character_id: 2, character_name: 'Companion', picked_option_id: 31, voted_option_id: null },
    ],
  },
  resolved: null,
};

const RESOLVED: ResolvedBeat = {
  instance_id: 7,
  outcome_name: null,
  story_text: 'PLACEHOLDER the party commits.',
  is_terminal: false,
  next_beat: null,
  epilogue: '',
};

const useGroupBeatMock = vi.fn();
const submitPickMock = vi.fn();
const castVoteMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useGroupBeat: (...args: unknown[]) => useGroupBeatMock(...args),
    useSubmitGroupPick: () => ({ mutate: submitPickMock, isPending: false, error: null }),
    useCastGroupVote: () => ({ mutate: castVoteMock, isPending: false, error: null }),
  };
});

import { GroupBeatCard } from '../components/GroupBeatCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('GroupBeatCard', () => {
  beforeEach(() => {
    submitPickMock.mockClear();
    castVoteMock.mockClear();
  });

  it('renders the pick phase with options and participant status', () => {
    useGroupBeatMock.mockReturnValue({ data: PICK_BEAT, isLoading: false });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    expect(screen.getByTestId('group-beat-phase')).toHaveTextContent('picking');
    expect(screen.getByText('PLACEHOLDER the crossroads.')).toBeInTheDocument();
    expect(screen.getByText('PLACEHOLDER take the path')).toBeInTheDocument();
    // Hero hasn't picked (…), Companion has (✓).
    expect(screen.getByText(/Hero/)).toHaveTextContent('…');
    expect(screen.getByText(/Companion/)).toHaveTextContent('✓');
  });

  it('submits a pick when an option is clicked in pick phase', async () => {
    useGroupBeatMock.mockReturnValue({ data: PICK_BEAT, isLoading: false });
    const user = userEvent.setup();
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    await user.click(screen.getByRole('button', { name: /take the path/i }));
    expect(submitPickMock).toHaveBeenCalledWith(
      { instanceId: 7, option_id: 31, approach_id: null },
      expect.anything()
    );
    expect(castVoteMock).not.toHaveBeenCalled();
  });

  it('submits a vote when an option is clicked in vote phase', async () => {
    useGroupBeatMock.mockReturnValue({ data: VOTE_BEAT, isLoading: false });
    const user = userEvent.setup();
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    expect(screen.getByTestId('group-beat-phase')).toHaveTextContent('voting');
    await user.click(screen.getByRole('button', { name: /take the path/i }));
    expect(castVoteMock).toHaveBeenCalledWith({ instanceId: 7, option_id: 31 }, expect.anything());
    expect(submitPickMock).not.toHaveBeenCalled();
  });

  it('shows the resolved view when the beat is resolved', () => {
    useGroupBeatMock.mockReturnValue({
      data: { group_beat: null, resolved: RESOLVED },
      isLoading: false,
    });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    expect(screen.getByTestId('group-beat-result')).toHaveTextContent(
      'PLACEHOLDER the party commits.'
    );
  });

  it('shows the concluded state when there is no beat and no resolution', () => {
    useGroupBeatMock.mockReturnValue({
      data: { group_beat: null, resolved: null },
      isLoading: false,
    });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    expect(screen.getByTestId('group-beat-concluded')).toBeInTheDocument();
  });

  it('renders the invite picker for contract holders', () => {
    useGroupBeatMock.mockReturnValue({ data: PICK_BEAT, isLoading: false });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" isContractHolder />));
    expect(screen.getByTestId('invite-picker')).toBeInTheDocument();
  });

  it('hides the invite picker for non-holders', () => {
    useGroupBeatMock.mockReturnValue({ data: PICK_BEAT, isLoading: false });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Tavern" />));
    expect(screen.queryByTestId('invite-picker')).not.toBeInTheDocument();
  });
});
